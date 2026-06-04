"""
agent.py — Email Classifier Agent
==================================
Architecture:
  Thread 1 — EmailSimulator
    Drip-feeds mock emails from /app/dataset/data.json into
    /app/data/inbox.json one at a time, every 5-15 seconds.
    Picks up newly added emails automatically.

  Thread 2 — AgentPoller  (event-driven + safety poll)
    Wakes up IMMEDIATELY whenever the inbox file changes
    (using file mtime watching), classifies every unseen email
    through the 3-node LangGraph pipeline, then goes back to sleep.
    Also wakes every 30 s as a safety net in case the mtime watch misses.

    Pipeline:  START → fetch_email → classify_email → store_result → END

Persistence:
  /app/data/inbox.json          — live inbox queue
  /app/data/processed_ids.json  — IDs already classified (never re-process)
  /app/data/important_emails.json — HIGH/MEDIUM/LOW sections written here
  /app/data/dismissed.json      — dismissed email IDs, persisted to disk
"""

import os
import json
import time
import random
import threading
from dotenv import load_dotenv
from typing import TypedDict, Dict, Any, Optional

from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, START, END

# ── Bootstrap ──────────────────────────────────────────────────────────────────
os.makedirs("/app/data", exist_ok=True)
os.makedirs("/app/dataset", exist_ok=True)

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────────
DATASET_FILE          = "/app/dataset/data.json"
INBOX_FILE            = "/app/data/inbox.json"
PROCESSED_IDS_FILE    = "/app/data/processed_ids.json"
IMPORTANT_EMAILS_FILE = "/app/data/important_emails.json"
DISMISSED_FILE        = "/app/data/dismissed.json"

SIM_MIN_DELAY  = 5    # seconds between simulated email arrivals
SIM_MAX_DELAY  = 15
SAFETY_POLL    = 30   # seconds — agent re-checks inbox even with no file change

# ── Event: fires when inbox file changes ───────────────────────────────────────
inbox_changed = threading.Event()


# ── JSON helpers ───────────────────────────────────────────────────────────────
def load_json(path: str, default):
    if not os.path.exists(path):
        return default
    with open(path, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default


def save_json(path: str, data) -> None:
    """Atomic write so dashboard never reads a half-written file."""
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=4)
    os.replace(tmp, path)


# ══════════════════════════════════════════════════════════════════════════════
# EMAIL SIMULATOR THREAD
# Delivers one email every 5-15 s from dataset into inbox.
# Loops back to start if all emails are delivered; picks up new ones instantly.
# ══════════════════════════════════════════════════════════════════════════════
class EmailSimulator(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="EmailSimulator")

    def run(self):
        print("[simulator] started — delivering 1 email every 5–15 s")
        while True:
            dataset = load_json(DATASET_FILE, [])
            if not dataset:
                print("[simulator] dataset empty or missing, waiting 10 s...")
                time.sleep(10)
                continue

            inbox         = load_json(INBOX_FILE, [])
            processed_ids = load_json(PROCESSED_IDS_FILE, [])
            inbox_ids     = {e.get("id") for e in inbox}
            blocked_ids   = inbox_ids | set(processed_ids)

            pending = [e for e in dataset if e.get("id") not in blocked_ids]

            if not pending:
                print("[simulator] all dataset emails delivered (all processed), waiting for new ones...")
                time.sleep(15)
                continue

            email = pending[0]
            inbox.append(email)
            save_json(INBOX_FILE, inbox)

            # Signal the agent thread immediately
            inbox_changed.set()

            print(f"[simulator] ✉  delivered id={email.get('id')}  "
                  f"subject='{email.get('subject', '')[:50]}'")

            delay = random.randint(SIM_MIN_DELAY, SIM_MAX_DELAY)
            print(f"[simulator]    next delivery in {delay} s")
            time.sleep(delay)


# ══════════════════════════════════════════════════════════════════════════════
# LANGGRAPH PIPELINE  —  3 nodes
#   START → fetch_email → classify_email → store_result → END
# ══════════════════════════════════════════════════════════════════════════════

class AgentState(TypedDict):
    email:          Dict[str, Any]
    classification: Optional[Dict[str, Any]]
    error:          Optional[str]


# Node 1 — validate fields
def fetch_email_node(state: AgentState) -> AgentState:
    email = state["email"]
    print(f"  [fetch]    id={email.get('id')}  subject='{email.get('subject','')[:50]}'")
    missing = [k for k in ("id","sender","subject","body") if not email.get(k)]
    if missing:
        print(f"  [fetch]    WARN missing {missing}")
        return {**state, "error": f"Missing fields: {missing}", "classification": None}
    return {**state, "error": None}


# Node 2 — classify with Groq LLM
def classify_email_node(state: AgentState) -> AgentState:
    if state.get("error"):
        return state

    email = state["email"]
    print(f"  [classify] id={email.get('id')}")

    prompt = f"""You are an expert AI Email Classifier. Read this email and decide if it is important.

Sender : {email.get('sender', '')}
Subject: {email.get('subject', '')}
Body   : {email.get('body', '')}

Mark as IMPORTANT (important: true) if:
  - Client complaint or urgent customer request
  - Payment failure or billing issue
  - Server down / outage / infrastructure alert
  - Security alert or suspicious account activity
  - Abnormally high or unexpected invoice
  - System anomaly or critical system warning

Mark as NOT IMPORTANT (important: false) if:
  - Routine reminders or meeting notifications
  - Marketing emails, newsletters, or promotions
  - Standard automated notifications with no action needed

Reply with ONLY a raw JSON object, no markdown:
{{
  "important": true or false,
  "priority": "HIGH", "MEDIUM", or "LOW",
  "category": "one of: PAYMENT_ISSUE, SERVER_DOWN, SECURITY_ALERT, CLIENT_COMPLAINT, HIGH_INVOICE, SERVER_ANOMALY, SPAM, NEWSLETTER, REMINDER, OTHER",
  "reason": "one clear sentence explaining the decision"
}}"""

    llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0)
    try:
        response = llm.invoke(prompt)
        text = response.content.strip()
        for fence in ("```json", "```"):
            if text.startswith(fence):
                text = text[len(fence):]
        if text.endswith("```"):
            text = text[:-3]

        result = json.loads(text.strip())
        result["important"] = bool(result.get("important", False))
        result["priority"]  = str(result.get("priority", "LOW")).upper()
        result["category"]  = str(result.get("category", "OTHER")).upper()
        result["reason"]    = str(result.get("reason", ""))

        print(f"  [classify] important={result['important']}  "
              f"priority={result['priority']}  category={result['category']}")
        return {**state, "classification": result, "error": None}

    except Exception as e:
        print(f"  [classify] ERROR {e}")
        return {**state, "classification": None, "error": str(e)}


# Node 3 — persist result into priority-sectioned JSON
def store_result_node(state: AgentState) -> AgentState:
    email          = state["email"]
    classification = state.get("classification")
    error          = state.get("error")

    processed_ids = load_json(PROCESSED_IDS_FILE, [])

    # Always mark as processed (even on error) to avoid infinite retry
    if email.get("id") not in processed_ids:
        processed_ids.append(email.get("id"))
        save_json(PROCESSED_IDS_FILE, processed_ids)

    if error or not classification:
        print(f"  [store]    id={email.get('id')} skipped (error/no result)")
        return state

    if not classification.get("important"):
        print(f"  [store]    id={email.get('id')} → not important, ignored")
        return state

    # Build the stored record — every field the dashboard needs
    priority = classification["priority"]   # HIGH | MEDIUM | LOW
    record = {
        "id":            email.get("id"),
        "subject":       email.get("subject", ""),
        "sender":        email.get("sender", ""),
        "body":          email.get("body", ""),
        "time_received": time.strftime("%Y-%m-%d %H:%M:%S"),
        "important":     True,
        "priority":      priority,
        "category":      classification.get("category", "OTHER"),
        "reason":        classification.get("reason", ""),
    }

    # Load the priority-sectioned store
    # Structure: { "HIGH": [...], "MEDIUM": [...], "LOW": [...] }
    store = load_json(IMPORTANT_EMAILS_FILE, {"HIGH": [], "MEDIUM": [], "LOW": []})

    # Ensure all three keys exist (in case file was manually edited)
    for p in ("HIGH", "MEDIUM", "LOW"):
        store.setdefault(p, [])

    # Insert newest-first within the right priority bucket
    store[priority].insert(0, record)
    save_json(IMPORTANT_EMAILS_FILE, store)

    print(f"  [store]    id={email.get('id')} → IMPORTANT [{priority}] saved to dashboard")
    return state


# ── Compile LangGraph graph ────────────────────────────────────────────────────
workflow = StateGraph(AgentState)
workflow.add_node("fetch_email",    fetch_email_node)
workflow.add_node("classify_email", classify_email_node)
workflow.add_node("store_result",   store_result_node)
workflow.add_edge(START,            "fetch_email")
workflow.add_edge("fetch_email",    "classify_email")
workflow.add_edge("classify_email", "store_result")
workflow.add_edge("store_result",   END)
agent_app = workflow.compile()


# ══════════════════════════════════════════════════════════════════════════════
# AGENT POLLER THREAD
# Event-driven: wakes immediately when inbox_changed is set by the simulator.
# Also wakes every SAFETY_POLL seconds as a fallback.
# ══════════════════════════════════════════════════════════════════════════════
def poll_once():
    inbox         = load_json(INBOX_FILE, [])
    processed_ids = load_json(PROCESSED_IDS_FILE, [])
    new_emails    = [e for e in inbox if e.get("id") not in processed_ids]

    if not new_emails:
        return

    print(f"\n[agent] {len(new_emails)} new email(s) — running LangGraph pipeline")
    for email in new_emails:
        agent_app.invoke({"email": email, "classification": None, "error": None})


def run_agent_poller():
    print(f"[agent] started — event-driven + {SAFETY_POLL}s safety poll")
    while True:
        # Wait for either a simulator signal OR the safety timeout
        triggered = inbox_changed.wait(timeout=SAFETY_POLL)
        inbox_changed.clear()
        if triggered:
            print("[agent] inbox_changed event received — polling now")
        poll_once()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    print("=" * 58)
    print("  Email Classifier Agent")
    print(f"  Dataset : {DATASET_FILE}")
    print(f"  Inbox   : {INBOX_FILE}")
    print(f"  Simulate: every {SIM_MIN_DELAY}–{SIM_MAX_DELAY} s")
    print(f"  Poll    : event-driven (+ {SAFETY_POLL}s safety net)")
    print("=" * 58)

    # Ensure the important_emails store has the right shape on first run
    if not os.path.exists(IMPORTANT_EMAILS_FILE):
        save_json(IMPORTANT_EMAILS_FILE, {"HIGH": [], "MEDIUM": [], "LOW": []})

    EmailSimulator().start()
    run_agent_poller()   # blocks main thread


if __name__ == "__main__":
    main()