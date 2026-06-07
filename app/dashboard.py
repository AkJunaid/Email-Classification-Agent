import streamlit as st
import json
import os

try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTOREFRESH = True
except ImportError:
    HAS_AUTOREFRESH = False

IMPORTANT_EMAILS_FILE = "/app/data/important_emails.json"
DISMISSED_FILE        = "/app/data/dismissed.json"


st.set_page_config(
    page_title="Email Classifier Dashboard",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
html, body, [data-testid="stAppViewContainer"] {
    background: #ffffff;
    color: #000000;
    font-family: Arial, Helvetica, sans-serif;
}

#MainMenu, footer, [data-testid="stToolbar"] { display: none !important; }

.dash-header {
    background: #000000;
    padding: 15px 20px;
    margin-bottom: 15px;
}
.dash-header h1 {
    font-size: 22px;
    font-weight: bold;
    margin: 0;
    color: #ffffff;
}
.dash-header p {
    font-size: 12px;
    color: #aaaaaa;
    margin: 5px 0 0;
}

.scard {
    border: 1px solid #cccccc;
    padding: 10px;
    text-align: center;
    background: #ffffff;
}
.scard .n { font-size: 28px; font-weight: bold; }
.scard .l { font-size: 11px; color: #666666; margin-top: 3px; }

.scard.sactive .n { color: #000000; }
.scard.sh .n { color: #000000; font-weight: bold; }
.scard.sm .n { color: #555555; }
.scard.sl .n { color: #999999; }

.ecard {
    border: 1px solid #cccccc;
    padding: 12px 15px;
    margin-bottom: 10px;
    background: #ffffff;
}
.ecard.read {
    background: #f5f5f5;
    border-color: #dddddd;
}
.ecard-h { border-left: 4px solid #000000; }
.ecard-m { border-left: 4px solid #666666; }
.ecard-l { border-left: 4px solid #cccccc; }
.ecard.read { border-left: 4px solid #dddddd; }

.ecard-title {
    font-size: 15px;
    font-weight: bold;
    color: #000000;
    margin-bottom: 6px;
}
.ecard-meta {
    font-size: 12px;
    color: #333333;
    border-bottom: 1px solid #eeeeee;
    padding-bottom: 6px;
    margin-bottom: 6px;
}
.ecard-body {
    font-size: 13px;
    color: #333333;
    padding: 6px 0;
    border-bottom: 1px solid #eeeeee;
    margin-bottom: 6px;
}
.ecard-reason {
    font-size: 12px;
    font-style: italic;
    border-left: 3px solid #000000;
    padding: 6px 10px;
    color: #333333;
}
.ecard.read .ecard-reason {
    border-left-color: #aaaaaa;
}

.badge {
    display: inline-block;
    padding: 1px 6px;
    font-size: 11px;
    font-weight: bold;
    margin-left: 3px;
}
.bH  { background: #e0e0e0; color: #000000; border: 1px solid #000000; font-weight: bold; }
.bM  { background: #f0f0f0; color: #333333; border: 1px solid #999999; }
.bL  { background: #f8f8f8; color: #666666; border: 1px solid #cccccc; }
.bC  { background: #f0f0f0; color: #555555; border: 1px solid #cccccc; }
.bI  { background: #ffffff; color: #000000; border: 1px solid #000000; }

.time-badge {
    font-size: 11px;
    color: #888888;
}

div.stButton > button {
    font-size: 12px !important;
    padding: 3px 10px !important;
    background: #ffffff !important;
    color: #000000 !important;
    border: 1px solid #000000 !important;
}
div.stButton > button:hover {
    background: #000000 !important;
    color: #ffffff !important;
}

.empty {
    text-align: center;
    padding: 40px 20px;
    border: 1px dashed #cccccc;
    color: #999999;
    font-size: 13px;
    background: #fafafa;
}

.stTabs [data-baseweb="tab-list"] {
    gap: 0px;
    background: #f0f0f0;
    border: 1px solid #cccccc;
    padding: 0px;
    margin-bottom: 12px;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 0px !important;
    padding: 8px 16px !important;
    font-size: 13px !important;
    color: #333333 !important;
    border-right: 1px solid #cccccc !important;
}
.stTabs [aria-selected="true"] {
    background: #ffffff !important;
    color: #000000 !important;
    font-weight: bold !important;
}

.section-header {
    font-size: 12px;
    font-weight: bold;
    padding: 6px 10px;
    margin: 12px 0 8px;
    border: 1px solid;
}
.section-header.sh {
    color: #000000;
    background: #e8e8e8;
    border-color: #000000;
}
.section-header.sm {
    color: #333333;
    background: #f0f0f0;
    border-color: #999999;
}
.section-header.sl {
    color: #666666;
    background: #f8f8f8;
    border-color: #cccccc;
}

.read-filter-btn div.stButton > button {
    border-radius: 0px !important;
    padding: 6px 12px !important;
    font-size: 12px !important;
    background: #ffffff !important;
    border: 1px solid #cccccc !important;
    color: #333333 !important;
}
.read-filter-btn div.stButton > button:hover {
    background: #f0f0f0 !important;
}

.unread-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #000000;
    margin-right: 5px;
}
</style>
""", unsafe_allow_html=True)


if HAS_AUTOREFRESH:
    st_autorefresh(interval=10_000, key="ar")
else:
    st.markdown('<meta http-equiv="refresh" content="10">', unsafe_allow_html=True)


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=4)
    os.replace(tmp, path)


def load_store():
    s = load_json(IMPORTANT_EMAILS_FILE, {})
    for p in ("HIGH", "MEDIUM", "LOW"):
        s.setdefault(p, [])
    return s


def load_read_ids():
    d = load_json(DISMISSED_FILE, {})
    for p in ("HIGH", "MEDIUM", "LOW"):
        d.setdefault(p, [])
    return d


def save_read_ids(d):
    save_json(DISMISSED_FILE, d)


def mark_as_read(email_id, priority):
    d = load_read_ids()
    p = priority.upper()
    if email_id not in d[p]:
        d[p].append(email_id)
    save_read_ids(d)


def render_card(email, tab_key, is_read=False):
    email_id    = email.get("id", "unknown")
    priority    = (email.get("priority") or "LOW").upper()
    category    = (email.get("category") or "OTHER").upper().replace("_", " ")

    priority_cls = {"HIGH": "ecard-h", "MEDIUM": "ecard-m", "LOW": "ecard-l"}.get(priority, "ecard-l")
    badge_cls    = {"HIGH": "bH", "MEDIUM": "bM", "LOW": "bL"}.get(priority, "bL")
    card_cls     = f"ecard {priority_cls} read" if is_read else f"ecard {priority_cls}"

    left, right = st.columns([0.11, 0.89])
    with left:
        if not is_read:
            if st.button("Mark as Read", key=f"read_{tab_key}_{email_id}", use_container_width=True):
                mark_as_read(email_id, priority)
                st.rerun()

    with right:
        important_val = email.get('important', False)
        important_badge = f'<span class="badge {"bI" if important_val else "bNI"}">Important: {"True" if important_val else "False"}</span>'
        st.markdown(f"""
        <div class="{card_cls}">
            <div class="ecard-title">
                {'' if is_read else '<span class="unread-dot"></span>'}{email.get('subject','No Subject')}
            </div>
            <div class="ecard-meta">
                <strong>From:</strong> {email.get('sender','Unknown')}
                <span class="time-badge"> | {email.get('time_received','—')}</span>
                &nbsp;&nbsp;
                {important_badge}
                &nbsp;
                <strong>Priority:</strong><span class="badge {badge_cls}">{priority}</span>
                &nbsp;
                <strong>Category:</strong><span class="badge bC">{category}</span>
            </div>
            <div class="ecard-body">
                {email.get('body','')}
            </div>
            <div class="ecard-reason">
                <strong>AI:</strong> {email.get('reason','No reason provided')}
            </div>
        </div>
        """, unsafe_allow_html=True)


store     = load_store()
read_data = load_read_ids()

high_emails   = store["HIGH"]
medium_emails = store["MEDIUM"]
low_emails    = store["LOW"]


active_high   = [e for e in high_emails   if e.get("id") not in read_data["HIGH"]]
active_medium = [e for e in medium_emails if e.get("id") not in read_data["MEDIUM"]]
active_low    = [e for e in low_emails    if e.get("id") not in read_data["LOW"]]
all_active    = active_high + active_medium + active_low


read_high   = [e for e in high_emails   if e.get("id") in read_data["HIGH"]]
read_medium = [e for e in medium_emails if e.get("id") in read_data["MEDIUM"]]
read_low    = [e for e in low_emails    if e.get("id") in read_data["LOW"]]
total_read  = len(read_high) + len(read_medium) + len(read_low)


st.markdown("""
<div class="dash-header">
    <h1>Email Classifier Dashboard</h1>
    <p>AI-classified important emails - live updates - emails arrive every 5-15 s</p>
</div>
""", unsafe_allow_html=True)


st.markdown(
    '<div style="font-size:11px;font-weight:bold;color:#000000;margin-bottom:5px;">Active (Unread)</div>',
    unsafe_allow_html=True,
)
c1, c2, c3, c4 = st.columns(4)
for col, num, lbl, cls in [
    (c1, len(all_active),    "Active",        "sactive"),
    (c2, len(active_high),   "High Priority", "sh"),
    (c3, len(active_medium), "Medium Priority", "sm"),
    (c4, len(active_low),    "Low Priority",  "sl"),
]:
    col.markdown(f"""
    <div class="scard {cls}">
        <div class="n">{num}</div>
        <div class="l">{lbl}</div>
    </div>""", unsafe_allow_html=True)


if "read_filter" not in st.session_state:
    st.session_state.read_filter = "ALL"

st.markdown(
    '<div style="font-size:11px;font-weight:bold;color:#888888;margin-top:12px;margin-bottom:5px;">Read</div>',
    unsafe_allow_html=True,
)


st.markdown('<div class="read-filter-btn">', unsafe_allow_html=True)
fc1, fc2, fc3, fc4 = st.columns(4)
filters = [
    ("ALL",    f"All ({total_read})"),
    ("HIGH",   f"High ({len(read_high)})"),
    ("MEDIUM", f"Medium ({len(read_medium)})"),
    ("LOW",    f"Low ({len(read_low)})"),
]
for col, (f_val, f_label) in zip([fc1, fc2, fc3, fc4], filters):
    with col:
        if st.button(f_label, key=f"rf_{f_val}", use_container_width=True,
                     type="primary" if st.session_state.read_filter == f_val else "secondary"):
            st.session_state.read_filter = f_val
            st.rerun()
st.markdown('</div>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)


tab_active, tab_read = st.tabs([
    f"Active ({len(all_active)})",
    f"Read ({total_read})",
])


with tab_active:
    if not all_active:
        st.markdown(
            '<div class="empty">No new emails yet - emails arrive every 5-15 s and are classified automatically.</div>',
            unsafe_allow_html=True,
        )
    else:

        for email in active_high:
            render_card(email, "active")
        for email in active_medium:
            render_card(email, "active")
        for email in active_low:
            render_card(email, "active")


with tab_read:
    filter_ = st.session_state.read_filter

    if total_read == 0:
        st.markdown(
            '<div class="empty">No read emails yet. Mark emails as read from the Active tab.</div>',
            unsafe_allow_html=True,
        )
    else:
        if filter_ == "ALL" or filter_ == "HIGH":
            if read_high:
                st.markdown('<div class="section-header sh">High Priority</div>', unsafe_allow_html=True)
                for email in read_high:
                    render_card(email, f"read_{filter_}", is_read=True)

        if filter_ == "ALL" or filter_ == "MEDIUM":
            if read_medium:
                st.markdown('<div class="section-header sm">Medium Priority</div>', unsafe_allow_html=True)
                for email in read_medium:
                    render_card(email, f"read_{filter_}", is_read=True)

        if filter_ == "ALL" or filter_ == "LOW":
            if read_low:
                st.markdown('<div class="section-header sl">Low Priority</div>', unsafe_allow_html=True)
                for email in read_low:
                    render_card(email, f"read_{filter_}", is_read=True)
