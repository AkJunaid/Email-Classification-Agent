# Email Classifier Agent

An intelligent email classification system that automatically identifies and prioritizes important emails using AI (Groq LLM via LangGraph). Comes with a live Streamlit dashboard for triaging classified emails.

---

## Setup

### Prerequisites

- **Docker** & **Docker Compose** (recommended)
- A **Groq API key** — 

### 1. Environment variables

Create a `.env` file in the project root:

```env
GROQ_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 2. Run with Docker Compose

```bash
docker compose up --build
```

Once running, open the dashboard at **[http://localhost:8501](http://localhost:8501)**.


To stop:
```bash
docker compose down
```

To view the agent's real-time logs:
```bash
docker compose logs -f email-agent
```

### 3. Run without Docker

Make sure you have a `.env` file or export the variable as shown below:

```bash
cd app
pip install -r requirements.txt
export GROQ_API_KEY="gsk_..."
python agent.py &        # starts simulator + classifier
streamlit run dashboard.py --server.port=8501
```

### Project structure

```
├── app/
│   ├── agent.py          # AI classifier + email simulator (Python)
│   ├── dashboard.py      # Streamlit dashboard
│   ├── Dockerfile        # Container definition
│   └── requirements.txt  # Python dependencies
├── dataset/
│   └── data.json         # 30 mock emails used as the data source
├── data/                 # Runtime state (persisted across restarts)
│   ├── inbox.json              # Live inbox queue
│   ├── processed_ids.json      # IDs already classified (duplicate prevention)
│   ├── important_emails.json   # Classified important emails (by priority)
│   └── dismissed.json          # Marked-as-read email IDs (by priority)
├── docker-compose.yml    # Runs both agent and dashboard
├── .env                  # GROQ_API_KEY goes here
└── README.md
```

---

## How the AI Works

The system runs **two concurrent threads** inside `agent.py`:

### Thread 1 — Email Simulator

Drip-feeds mock emails from `dataset/data.json` into `data/inbox.json`, one at a time, every 5–15 seconds. It checks both the inbox and `data/processed_ids.json` to prevent re-delivering emails that have already been classified. When all emails are delivered it waits — if new ones are added to the dataset, it picks them up automatically on the next loop.

### Thread 2 — Agent Poller (LangGraph pipeline)

Uses a `threading.Event` to wake up **immediately** whenever the simulator writes to the inbox file **and** every 30 seconds as a safety net. This dual mechanism ensures no email is missed even if the file-watch signal is dropped. It processes every unseen email through a **3-node LangGraph pipeline**:

```
START → fetch_email → classify_email → store_result → END
```

| Node | What it does |
|---|---|
| **fetch_email** | Validates required fields (`id`, `sender`, `subject`, `body`). |
| **classify_email** | Calls **Groq's Llama 3.1 8B** (`llama-3.1-8b-instant`) with a structured prompt. The LLM returns a JSON object with: `important` (boolean), `priority` (HIGH / MEDIUM / LOW), `category`, and `reason`. |
| **store_result** | Persists the result into `data/important_emails.json`, organized by priority bucket (`HIGH` / `MEDIUM` / `LOW`). Non-important emails are silently ignored. On classification errors, the email is marked as processed to prevent infinite retries but not added to the dashboard. |

#### Data integrity

All JSON files are written using **atomic writes** — data is written to a temporary file (`.tmp`) then atomically renamed via `os.replace()`. This guarantees the Streamlit dashboard never reads a half-written file.

### Classification criteria

The LLM is instructed to mark an email as **IMPORTANT** if it involves:

- Client complaint or urgent customer request
- Payment failure or billing issue
- Server down / outage / infrastructure alert
- Security alert or suspicious account activity
- Abnormally high or unexpected invoice
- System anomaly or critical system warning

And **NOT IMPORTANT** for:

- Routine reminders or meeting notifications
- Marketing emails, newsletters, or promotions
- Standard automated notifications with no action needed

### Categories assigned

`PAYMENT_ISSUE`, `SERVER_DOWN`, `SECURITY_ALERT`, `CLIENT_COMPLAINT`, `HIGH_INVOICE`, `SERVER_ANOMALY`, `SPAM`, `NEWSLETTER`, `REMINDER`, `OTHER`

### Priority levels

- **HIGH** — requires immediate action (e.g., security alerts, outages, payment failures)
- **MEDIUM** — requires attention but not urgent (e.g., interview invites, password reset requests)
- **LOW** — informational, low-urgency items

### Duplicate Prevention

- Every classified email is recorded in `data/processed_ids.json` immediately after processing
- The **simulator** checks `processed_ids.json` before delivering any email — already-processed emails are never re-added to the inbox
- The **agent poller** filters out processed IDs before invoking the pipeline, so even if an email somehow reappears in the inbox, it won't be re-classified
- On classification errors, the email is still marked as processed to prevent infinite retry loops

---

## How the Dashboard Works

The dashboard is a **Streamlit** web app (`dashboard.py`) that reads `data/important_emails.json` and `data/dismissed.json` to display classified emails. It runs with a wide layout, collapsed sidebar, and a custom CSS theme (blue header, red/blue/gray priority colors, white backgrounds).

### Layout

- **Header** — title, subtitle, and live-update indicator
- **Stats row (Active)** — counts for total active, high, medium, low priority unread emails
- **Stats row (Read)** — same counts for read emails, with clickable filter pills (All / High / Medium / Low)
- **Two tabs**: **Active** (unread emails) and **Read** (previously marked as read)

### Active tab

Emails are displayed as **cards** grouped by priority (HIGH → MEDIUM → LOW), newest first. Each card shows:

- **Subject** with a blue unread indicator dot
- **Sender & timestamp**
- **Important badge** (green "Important: True" label on every classified important email)
- **Priority badge** (color-coded: red / blue / gray)
- **Category badge**
- **Email body**
- **AI classification reason** (in an indented italic block)
- **"Mark as Read" button** — moves the email to the Read tab

### Read tab

Same card layout, but with a muted background. Supports filtering by priority using the filter pills above the tabs. No restore functionality (marked-as-read is permanent).

### Auto-refresh

The dashboard refreshes every **10 seconds** via `streamlit-autorefresh` (falls back to a `<meta http-equiv="refresh">` tag if the package is missing), so new emails appear automatically as they are classified.

### Persistence

- **Unread/read state** is stored in `data/dismissed.json` — persists across page refreshes and container restarts
- **Classified emails** are stored in `data/important_emails.json` — survives restarts
- **Processed IDs** are stored in `data/processed_ids.json` — prevents duplicate processing across restarts

---

## Limitations

**Groq API used** - Used only Groq Api using llama-3.1-8b-instant

- **Mock dataset only** — the included dataset contains 30 pre-written mock emails. To use real emails, you would need to replace or extend `dataset/data.json` (or wire `agent.py` to an actual email source like IMAP).
- **No email fetching from real providers** — the system does not connect to Gmail, Outlook, or any SMTP/IMAP server. It only reads from the local JSON dataset.
- **Priority buckets are fixed** — all important emails fall into HIGH / MEDIUM / LOW. There is no custom priority tagging or user-configurable rules.
