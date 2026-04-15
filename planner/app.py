"""
SARA Project Planner  —  Professional Edition
----------------------------------------------
Run:  streamlit run planner/app.py
DB:   planner/tasks.json  (auto-saved on every change)
"""

import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# ───────────────────────────────────────────────────────────────────────────
#  PAGE CONFIG
# ───────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SARA Planner",
    page_icon="▸",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_PATH = Path(__file__).parent / "tasks.json"

# ───────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ───────────────────────────────────────────────────────────────────────────
STATUS = {
    "todo":        {"label": "To Do",       "color": "#6c6c99", "bg": "rgba(108,108,153,0.14)", "icon": "○", "order": 0},
    "in_progress": {"label": "In Progress", "color": "#f0b429", "bg": "rgba(240,180,41,0.14)",  "icon": "◑", "order": 1},
    "blocked":     {"label": "Blocked",     "color": "#ef4444", "bg": "rgba(239,68,68,0.14)",   "icon": "⊘", "order": 2},
    "done":        {"label": "Done",        "color": "#10b981", "bg": "rgba(16,185,129,0.14)",  "icon": "✓", "order": 3},
}
PRIORITY = {
    "critical": {"label": "Critical", "color": "#ef4444", "order": 0},
    "high":     {"label": "High",     "color": "#f0b429", "order": 1},
    "medium":   {"label": "Medium",   "color": "#06b6d4", "order": 2},
    "low":      {"label": "Low",      "color": "#6c6c99", "order": 3},
}
PHASE_COLOR = {
    "Phase 1 — Pipeline Running":  "#f0b429",
    "Phase 2 — Parser Fields":     "#10b981",
    "Phase 3 — Analytics Scripts": "#7c3aed",
    "Phase 4 — Report Generation": "#06b6d4",
    "Phase 5 — External Data":     "#ff6b35",
    "Phase 6 — Monthly Workflow":  "#ef4444",
}
PHASE_SHORT = {p: p.split("—")[-1].strip() for p in PHASE_COLOR}

# ───────────────────────────────────────────────────────────────────────────
#  THEME  (injected once at top)
# ───────────────────────────────────────────────────────────────────────────
st.markdown("""<style>
/* ═══ RESET & BASE ══════════════════════════════════════════════════════ */
*{box-sizing:border-box;}
html,body,.stApp,.main,.block-container{
  background:#06060f !important;
  color:#e8e8f2 !important;
  font-family:'Inter',system-ui,sans-serif;
}
.block-container{padding:1.5rem 2rem 4rem !important; max-width:1300px;}

/* ═══ SIDEBAR ════════════════════════════════════════════════════════════ */
section[data-testid="stSidebar"]{
  background:#0a0a18 !important;
  border-right:1px solid rgba(255,255,255,0.10) !important;
  padding-top:0 !important;
}
section[data-testid="stSidebar"] *{color:#d0d0e8 !important;}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3{color:#eeeef8 !important; font-weight:700 !important;}
section[data-testid="stSidebar"] hr{border-color:rgba(255,255,255,0.10) !important;}
section[data-testid="stSidebar"] label p{
  color:#8888a8 !important; font-size:.72rem !important;
  font-weight:700 !important; letter-spacing:.07em !important; text-transform:uppercase !important;
}

/* ═══ HEADINGS ═══════════════════════════════════════════════════════════ */
h1,h2,h3,h4,.stMarkdown h1,.stMarkdown h2,.stMarkdown h3{color:#eeeef8 !important;}
.stMarkdown p,.stMarkdown li{color:#c0c0d8 !important;}
p{color:#c0c0d8;}

/* ═══ METRICS ════════════════════════════════════════════════════════════ */
div[data-testid="metric-container"]{
  background:#0e0e20 !important;
  border:1px solid rgba(255,255,255,0.12) !important;
  border-radius:14px !important;
  padding:1.1rem 1.3rem !important;
  transition:border-color .2s;
}
div[data-testid="metric-container"]:hover{border-color:rgba(255,255,255,0.22) !important;}
div[data-testid="metric-container"] label{
  color:#8888a8 !important; font-size:.7rem !important;
  font-weight:700 !important; letter-spacing:.08em !important; text-transform:uppercase !important;
}
[data-testid="stMetricValue"]{color:#eeeef8 !important; font-size:2rem !important; font-weight:800 !important;}
[data-testid="stMetricDelta"]{font-size:.78rem !important;}

/* ═══ PROGRESS ═══════════════════════════════════════════════════════════ */
div[data-testid="stProgress"]>div{
  background:rgba(255,255,255,0.07) !important;
  border-radius:99px !important; height:5px !important;
}
div[data-testid="stProgress"]>div>div{
  border-radius:99px !important;
  background:linear-gradient(90deg,#f0b429,#ff6b35) !important;
}

/* ═══ EXPANDER (task cards) ══════════════════════════════════════════════ */
div[data-testid="stExpander"]{
  background:#0e0e20 !important;
  border:1px solid rgba(255,255,255,0.11) !important;
  border-radius:12px !important;
  margin-bottom:.35rem !important;
  overflow:hidden !important;
  transition:border-color .15s, box-shadow .15s;
}
div[data-testid="stExpander"]:hover{
  border-color:rgba(255,255,255,0.22) !important;
  box-shadow:0 4px 24px rgba(0,0,0,.35) !important;
}
div[data-testid="stExpander"] summary{
  background:#0e0e20 !important;
  padding:.75rem 1.1rem !important;
  font-size:.875rem !important; font-weight:600 !important;
}
div[data-testid="stExpander"] summary:hover{background:#12122a !important;}
div[data-testid="stExpander"] summary p{color:#e8e8f2 !important; font-weight:600 !important;}
div[data-testid="stExpander"] summary svg{color:#6c6c99 !important;}
div[data-testid="stExpander"]>div:last-child{
  background:#0b0b1c !important;
  border-top:1px solid rgba(255,255,255,0.08) !important;
  padding:1.1rem 1.2rem 1.2rem !important;
}

/* ═══ INPUTS ═════════════════════════════════════════════════════════════ */
div[data-baseweb="select"]>div{
  background:#111125 !important;
  border:1px solid rgba(255,255,255,0.16) !important;
  border-radius:9px !important; color:#e8e8f2 !important;
}
div[data-baseweb="select"] span,div[data-baseweb="select"] div{color:#e8e8f2 !important;}
div[data-baseweb="select"]>div:focus-within{border-color:rgba(240,180,41,.5) !important;}
textarea,input[type="text"]{
  background:#111125 !important;
  border:1px solid rgba(255,255,255,0.16) !important;
  border-radius:9px !important; color:#e8e8f2 !important;
  font-size:.85rem !important;
}
textarea::placeholder,input::placeholder{color:#6c6c99 !important;}
textarea:focus,input:focus{
  border-color:rgba(240,180,41,.45) !important;
  box-shadow:0 0 0 3px rgba(240,180,41,.08) !important;
}

/* ═══ DROPDOWN POPOVER ═══════════════════════════════════════════════════ */
div[data-baseweb="popover"]>div,div[data-baseweb="menu"]{
  background:#14142a !important;
  border:1px solid rgba(255,255,255,0.16) !important;
  border-radius:10px !important;
}
[role="option"],[role="option"] *{color:#e8e8f2 !important; background:transparent !important;}
[role="option"]:hover,li:hover{background:rgba(255,255,255,0.06) !important; color:#eeeef8 !important;}
[role="option"][aria-selected="true"],[role="option"][aria-selected="true"] *{
  background:rgba(240,180,41,0.13) !important; color:#f0b429 !important;
}
[data-highlighted="true"],[data-highlighted="true"] *{
  background:rgba(255,255,255,0.06) !important; color:#eeeef8 !important;
}

/* ═══ BUTTONS ════════════════════════════════════════════════════════════ */
button[kind="primary"],div[data-testid="stButton"]>button[kind="primary"]{
  background:linear-gradient(135deg,#f0b429,#ff6b35) !important;
  color:#06060f !important; border:none !important;
  border-radius:9px !important; font-weight:700 !important;
  font-size:.82rem !important; letter-spacing:.02em !important;
  transition:opacity .15s !important;
}
button[kind="secondary"],div[data-testid="stButton"]>button[kind="secondary"],
div[data-testid="stDownloadButton"]>button{
  background:#14142a !important; color:#d0d0e8 !important;
  border:1px solid rgba(255,255,255,0.16) !important;
  border-radius:9px !important; font-weight:600 !important; font-size:.82rem !important;
}
button:hover{opacity:.88 !important;}

/* ═══ ALERTS ═════════════════════════════════════════════════════════════ */
div[data-testid="stAlert"]{
  background:#111125 !important; border-radius:10px !important;
  border:1px solid rgba(255,255,255,0.12) !important;
}
div[data-testid="stAlert"] p{color:#e8e8f2 !important;}

/* ═══ DIVIDER ════════════════════════════════════════════════════════════ */
hr{border-color:rgba(255,255,255,0.10) !important; margin:.6rem 0 !important;}

/* ═══ CAPTION ════════════════════════════════════════════════════════════ */
.stCaption,[data-testid="stCaptionContainer"]{color:#6c6c99 !important;}

/* ═══ CUSTOM COMPONENTS ══════════════════════════════════════════════════ */
.top-bar{
  display:flex; align-items:center; justify-content:space-between;
  padding:.9rem 0 1rem; border-bottom:1px solid rgba(255,255,255,0.10);
  margin-bottom:1.4rem;
}
.top-bar-title{font-size:1.2rem; font-weight:800; letter-spacing:-.02em; color:#eeeef8;}
.top-bar-title span{color:#f0b429;}
.top-bar-meta{font-size:.75rem; color:#8888a8;}

.kpi-row{display:grid; grid-template-columns:repeat(5,1fr); gap:.9rem; margin-bottom:1.4rem;}
.kpi{
  background:#0e0e20; border:1px solid rgba(255,255,255,0.11);
  border-radius:14px; padding:1.1rem 1.3rem;
  transition:border-color .2s;
}
.kpi:hover{border-color:rgba(255,255,255,0.22);}
.kpi-val{font-size:2.1rem; font-weight:800; line-height:1; color:#eeeef8; letter-spacing:-.03em;}
.kpi-label{font-size:.68rem; font-weight:700; letter-spacing:.09em; text-transform:uppercase; color:#8888a8; margin-top:.35rem;}
.kpi-sub{font-size:.72rem; color:#6c6c99; margin-top:.2rem;}

.phase-strip{
  display:grid; grid-template-columns:repeat(6,1fr);
  gap:.6rem; margin-bottom:1.6rem;
}
.phase-tile{
  background:#0e0e20; border:1px solid rgba(255,255,255,0.10);
  border-radius:11px; padding:.8rem .9rem; cursor:default;
  transition:border-color .2s;
}
.phase-tile:hover{border-color:rgba(255,255,255,0.2);}
.phase-tile-name{font-size:.65rem; font-weight:800; letter-spacing:.09em; text-transform:uppercase; margin-bottom:.4rem;}
.phase-tile-pct{font-size:1.4rem; font-weight:800; line-height:1; color:#eeeef8;}
.phase-tile-sub{font-size:.68rem; color:#8888a8; margin-top:.25rem;}
.phase-tile-bar{height:3px; border-radius:99px; background:rgba(255,255,255,0.08); margin-top:.6rem;}
.phase-tile-fill{height:100%; border-radius:99px;}

.section-divider{
  display:flex; align-items:center; gap:.75rem;
  margin:1.6rem 0 .75rem; padding-bottom:.55rem;
  border-bottom:1px solid rgba(255,255,255,0.10);
}
.section-divider-label{
  font-size:.68rem; font-weight:800; letter-spacing:.12em;
  text-transform:uppercase; color:#8888a8; white-space:nowrap;
}
.section-divider-count{
  font-size:.68rem; color:#6c6c99;
  background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.09);
  border-radius:99px; padding:.1rem .55rem; white-space:nowrap;
}

.badge{
  display:inline-flex; align-items:center; gap:.3rem;
  padding:.18rem .6rem; border-radius:99px;
  font-size:.66rem; font-weight:800; letter-spacing:.06em; text-transform:uppercase;
  border:1px solid transparent;
}
.task-row-meta{
  display:flex; flex-wrap:wrap; gap:.4rem; align-items:center; margin:.6rem 0 .9rem;
}
.task-desc{font-size:.82rem; color:#9898b8; line-height:1.65; margin:.2rem 0 .8rem;}
.task-cmd{
  background:#06060f; border:1px solid rgba(255,255,255,0.10);
  border-radius:8px; padding:.55rem .85rem; font-family:ui-monospace,monospace;
  font-size:.76rem; color:#c0d0f8; line-height:1.5; margin-bottom:.9rem;
  overflow-x:auto;
}
.sub-label{
  font-size:.66rem; font-weight:800; letter-spacing:.09em;
  text-transform:uppercase; color:#8888a8; margin-bottom:.35rem;
}

.filter-bar{
  display:flex; gap:.5rem; flex-wrap:wrap; align-items:center;
  background:#0e0e20; border:1px solid rgba(255,255,255,0.10);
  border-radius:11px; padding:.65rem .9rem; margin-bottom:1.1rem;
}
.filter-chip{
  font-size:.7rem; font-weight:700; padding:.2rem .65rem;
  border-radius:99px; background:rgba(240,180,41,0.12);
  color:#f0b429; border:1px solid rgba(240,180,41,0.25);
}
.showing-txt{font-size:.78rem; color:#8888a8; flex:1;}
.showing-txt strong{color:#e8e8f2;}

.add-form{
  background:#0e0e20; border:1px solid rgba(255,255,255,0.12);
  border-radius:14px; padding:1.5rem 1.5rem 1.2rem; margin-top:.5rem;
}

.footer{
  text-align:center; font-size:.72rem; color:#6c6c99;
  border-top:1px solid rgba(255,255,255,0.08);
  padding-top:1.2rem; margin-top:2rem;
}
.footer code{
  background:#111125; border:1px solid rgba(255,255,255,0.12);
  border-radius:5px; padding:.1rem .4rem; color:#c0c0d8;
}
</style>""", unsafe_allow_html=True)


# ───────────────────────────────────────────────────────────────────────────
#  DATA LAYER
# ───────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=0)
def _load_raw() -> dict:
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def load_tasks() -> list[dict]:
    return _load_raw()["tasks"]

def save_tasks(tasks: list[dict]) -> None:
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump({"tasks": tasks}, f, indent=2, ensure_ascii=False)
    st.cache_data.clear()

def get_idx(tasks: list[dict], tid: str) -> int:
    for i, t in enumerate(tasks):
        if t["id"] == tid:
            return i
    return -1


# ───────────────────────────────────────────────────────────────────────────
#  HELPERS
# ───────────────────────────────────────────────────────────────────────────
def badge(text: str, color: str, bg: str = "", border: str = "") -> str:
    _bg  = bg     or f"rgba({_hex2rgb(color)},0.13)"
    _brd = border or f"rgba({_hex2rgb(color)},0.35)"
    return (f"<span class='badge' style='color:{color};background:{_bg};"
            f"border-color:{_brd};'>{text}</span>")

def _hex2rgb(h: str) -> str:
    h = h.lstrip("#")
    r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
    return f"{r},{g},{b}"

def status_badge(key: str) -> str:
    s = STATUS[key]
    return badge(f"{s['icon']} {s['label']}", s["color"])

def priority_badge(key: str) -> str:
    p = PRIORITY[key]
    return badge(f"◆ {p['label']}", p["color"])

def phase_badge(phase: str) -> str:
    c = PHASE_COLOR.get(phase, "#6c6c99")
    short = PHASE_SHORT.get(phase, phase)
    return badge(short, c)

def is_command(text: str) -> bool:
    """Detect if description looks like a terminal command."""
    starters = ("python", "pip", "sudo", "curl", "systemctl", "apt",
                 "cd ", "ls ", "cat ", "grep ", "docker", "git ", "aws")
    return any(text.strip().lower().startswith(s) for s in starters)


# ───────────────────────────────────────────────────────────────────────────
#  SIDEBAR
# ───────────────────────────────────────────────────────────────────────────
def render_sidebar(tasks: list[dict]) -> dict:
    sb = st.sidebar

    # Logo / title
    sb.markdown(
        "<div style='padding:1.2rem 1rem .6rem;border-bottom:1px solid rgba(255,255,255,0.09);margin-bottom:.8rem;'>"
        "<div style='font-size:1.15rem;font-weight:800;color:#eeeef8;letter-spacing:-.02em;'>▸ SARA <span style=\"color:#f0b429;\">Planner</span></div>"
        "<div style='font-size:.7rem;color:#6c6c99;margin-top:.2rem;'>Market Intelligence Build Tracker</div>"
        "</div>",
        unsafe_allow_html=True
    )

    # Overall mini progress
    done_n = sum(1 for t in tasks if t["status"] == "done")
    total  = len(tasks)
    pct    = int(done_n / total * 100) if total else 0
    sb.markdown(
        f"<div style='padding:.5rem 0 .2rem;'>"
        f"<div style='display:flex;justify-content:space-between;font-size:.72rem;color:#8888a8;margin-bottom:.35rem;'>"
        f"<span>Overall progress</span><strong style='color:#f0b429;'>{pct}%</strong></div>",
        unsafe_allow_html=True
    )
    sb.progress(done_n / total if total else 0)
    sb.markdown(
        f"<div style='font-size:.68rem;color:#6c6c99;margin-top:.2rem;margin-bottom:.8rem;'>{done_n} of {total} tasks complete</div>",
        unsafe_allow_html=True
    )
    sb.divider()

    # ── Filters ──
    sb.markdown("<div style='font-size:.68rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:#6c6c99;margin-bottom:.5rem;'>Filters</div>", unsafe_allow_html=True)

    phases   = sorted(set(t["phase"]   for t in tasks))
    sections = sorted(set(t["section"] for t in tasks))

    sel_phase    = sb.selectbox("Phase",    ["All Phases"] + phases,                                          key="fp")
    sel_status   = sb.selectbox("Status",   ["All"] + [v["label"] for v in STATUS.values()],                  key="fs")
    sel_priority = sb.selectbox("Priority", ["All"] + [v["label"] for v in PRIORITY.values()],                key="fpr")
    sel_section  = sb.selectbox("Section",  ["All Sections"] + sections,                                      key="fse")

    sb.divider()
    search = sb.text_input("Search", placeholder="keyword in title / description...", key="sq")

    sb.divider()
    # ── Bulk actions ──
    sb.markdown("<div style='font-size:.68rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:#6c6c99;margin-bottom:.5rem;'>Bulk Actions</div>", unsafe_allow_html=True)

    col1, col2 = sb.columns(2)
    with col1:
        if st.button("✓ All Done", use_container_width=True, key="bulk_done"):
            for t in tasks: t["status"] = "done"
            save_tasks(tasks); st.rerun()
    with col2:
        if st.button("↺ Reset", use_container_width=True, key="bulk_reset"):
            for t in tasks: t["status"] = "todo"; t["notes"] = ""
            save_tasks(tasks); st.rerun()

    # Mark filtered in_progress
    if st.button("◑ Mark Filtered → In Progress", use_container_width=True, key="bulk_inprog"):
        st.session_state["_bulk_inprog"] = True
        st.rerun()

    sb.divider()
    # ── Export ──
    sb.markdown("<div style='font-size:.68rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:#6c6c99;margin-bottom:.5rem;'>Export</div>", unsafe_allow_html=True)
    df  = pd.DataFrame(tasks)
    csv = df.to_csv(index=False)
    sb.download_button("⬇ Export CSV", data=csv,
                       file_name=f"sara_tasks_{datetime.now().strftime('%Y%m%d')}.csv",
                       mime="text/csv", use_container_width=True, key="dl_csv")

    sb.markdown(
        f"<div style='margin-top:.8rem;font-size:.68rem;color:#6c6c99;'>"
        f"Saved {datetime.fromtimestamp(os.path.getmtime(DB_PATH)).strftime('%d %b %Y %H:%M')}"
        f"</div>",
        unsafe_allow_html=True
    )

    return {
        "phase": sel_phase, "status": sel_status,
        "priority": sel_priority, "section": sel_section,
        "search": search.strip().lower(),
    }


# ───────────────────────────────────────────────────────────────────────────
#  FILTER
# ───────────────────────────────────────────────────────────────────────────
def apply_filters(tasks: list[dict], f: dict) -> list[dict]:
    out = tasks
    if f["phase"]    != "All Phases":   out = [t for t in out if t["phase"]    == f["phase"]]
    if f["status"]   != "All":
        k = next(k for k, v in STATUS.items()   if v["label"] == f["status"])
        out = [t for t in out if t["status"] == k]
    if f["priority"] != "All":
        k = next(k for k, v in PRIORITY.items() if v["label"] == f["priority"])
        out = [t for t in out if t["priority"] == k]
    if f["section"]  != "All Sections": out = [t for t in out if t["section"]  == f["section"]]
    if f["search"]:
        q = f["search"]
        out = [t for t in out if q in t["title"].lower()
               or q in t["description"].lower()
               or q in t.get("notes","").lower()]
    return out


# ───────────────────────────────────────────────────────────────────────────
#  DASHBOARD (top cards + phase strip)
# ───────────────────────────────────────────────────────────────────────────
def render_dashboard(tasks: list[dict]) -> None:
    total   = len(tasks)
    done    = sum(1 for t in tasks if t["status"] == "done")
    inprog  = sum(1 for t in tasks if t["status"] == "in_progress")
    blocked = sum(1 for t in tasks if t["status"] == "blocked")
    todo    = sum(1 for t in tasks if t["status"] == "todo")
    pct     = int(done / total * 100) if total else 0

    # ── Top bar ──
    st.markdown(
        f"<div class='top-bar'>"
        f"  <div class='top-bar-title'>▸ SARA <span>Market Intelligence</span> — Build Tracker</div>"
        f"  <div class='top-bar-meta'>{datetime.now().strftime('%d %B %Y')}</div>"
        f"</div>",
        unsafe_allow_html=True
    )

    # ── KPI row ──
    c1,c2,c3,c4,c5 = st.columns(5)
    def _kpi(col, val, label, sub="", color="#eeeef8"):
        col.markdown(
            f"<div class='kpi'>"
            f"  <div class='kpi-val' style='color:{color};'>{val}</div>"
            f"  <div class='kpi-label'>{label}</div>"
            f"  <div class='kpi-sub'>{sub}</div>"
            f"</div>",
            unsafe_allow_html=True
        )
    _kpi(c1, f"{pct}%",   "Complete",     f"{done} of {total} tasks", "#f0b429")
    _kpi(c2, done,        "Done",          "Tasks finished",           "#10b981")
    _kpi(c3, inprog,      "In Progress",   "Currently active",         "#f0b429")
    _kpi(c4, blocked,     "Blocked",       "Need attention",           "#ef4444" if blocked else "#6c6c99")
    _kpi(c5, todo,        "To Do",         "Not yet started",          "#6c6c99")

    # ── Overall progress bar ──
    st.markdown("<div style='margin:.5rem 0 1.2rem;'>", unsafe_allow_html=True)
    st.progress(done / total if total else 0)
    st.markdown("</div>", unsafe_allow_html=True)

    # ── Phase strip ──
    phases = list(PHASE_COLOR.keys())
    cols   = st.columns(len(phases))
    for i, phase in enumerate(phases):
        ph_tasks = [t for t in tasks if t["phase"] == phase]
        ph_done  = sum(1 for t in ph_tasks if t["status"] == "done")
        ph_total = len(ph_tasks)
        ph_pct   = int(ph_done / ph_total * 100) if ph_total else 0
        color    = PHASE_COLOR[phase]
        short    = PHASE_SHORT[phase]
        with cols[i]:
            st.markdown(
                f"<div class='phase-tile'>"
                f"  <div class='phase-tile-name' style='color:{color};'>{short}</div>"
                f"  <div class='phase-tile-pct'>{ph_pct}%</div>"
                f"  <div class='phase-tile-sub'>{ph_done}/{ph_total} done</div>"
                f"  <div class='phase-tile-bar'>"
                f"    <div class='phase-tile-fill' style='width:{ph_pct}%;background:{color};'></div>"
                f"  </div>"
                f"</div>",
                unsafe_allow_html=True
            )

    st.markdown("<div style='height:.4rem;'></div>", unsafe_allow_html=True)


# ───────────────────────────────────────────────────────────────────────────
#  TASK CARD
# ───────────────────────────────────────────────────────────────────────────
def render_task(task: dict, tasks: list[dict]) -> None:
    sc = STATUS[task["status"]]
    pc = PRIORITY[task["priority"]]

    # Left-border color by status
    border_left = f"border-left:3px solid {sc['color']} !important;"

    # Expander label — icon + title only (clean)
    with st.expander(f"{sc['icon']}  {task['title']}", expanded=False):

        # ── Meta badges ──
        st.markdown(
            f"<div class='task-row-meta'>"
            + status_badge(task["status"])
            + priority_badge(task["priority"])
            + phase_badge(task["phase"])
            + f"<span style='font-size:.66rem;color:#6c6c99;margin-left:auto;'>{task['id']}</span>"
            + f"</div>",
            unsafe_allow_html=True
        )

        # ── Description / command ──
        desc = task["description"]
        if is_command(desc):
            # Render as code block
            st.markdown(f"<div class='task-cmd'>$ {desc}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='task-desc'>{desc}</div>", unsafe_allow_html=True)

        # ── Notes (read-only preview if exists) ──
        existing_notes = task.get("notes", "")
        if existing_notes:
            st.markdown(
                f"<div style='background:rgba(240,180,41,0.07);border:1px solid rgba(240,180,41,0.2);"
                f"border-radius:8px;padding:.55rem .8rem;font-size:.78rem;color:#c8c060;"
                f"margin-bottom:.75rem;'>"
                f"📝 {existing_notes}</div>",
                unsafe_allow_html=True
            )

        # ── Controls row ──
        c_status, c_notes, c_save = st.columns([1.6, 2.8, 1])

        with c_status:
            st.markdown("<div class='sub-label'>Status</div>", unsafe_allow_html=True)
            status_map   = {v["label"]: k for k, v in STATUS.items()}
            new_sl       = st.selectbox(
                "s", list(status_map.keys()),
                index=list(status_map.keys()).index(sc["label"]),
                key=f"s_{task['id']}", label_visibility="collapsed"
            )
            new_status = status_map[new_sl]

        with c_notes:
            st.markdown("<div class='sub-label'>Notes / Blockers</div>", unsafe_allow_html=True)
            new_notes = st.text_area(
                "n", value=existing_notes, height=72,
                placeholder="Add notes, links, or blockers…",
                key=f"n_{task['id']}", label_visibility="collapsed"
            )

        with c_save:
            st.markdown("<div class='sub-label'>&nbsp;</div>", unsafe_allow_html=True)
            if st.button("Save", key=f"sv_{task['id']}", type="primary", use_container_width=True):
                idx = get_idx(tasks, task["id"])
                if idx >= 0:
                    tasks[idx]["status"] = new_status
                    tasks[idx]["notes"]  = new_notes
                    save_tasks(tasks)
                    st.rerun()


# ───────────────────────────────────────────────────────────────────────────
#  ADD TASK
# ───────────────────────────────────────────────────────────────────────────
def render_add_task(tasks: list[dict]) -> None:
    with st.expander("➕  Add Custom Task", expanded=False):
        st.markdown("<div class='add-form'>", unsafe_allow_html=True)
        phases   = sorted(set(t["phase"]   for t in tasks))
        sections = sorted(set(t["section"] for t in tasks))

        c1, c2, c3 = st.columns(3)
        with c1:
            new_phase    = st.selectbox("Phase",    phases,                      key="np")
            new_title    = st.text_input("Title",   placeholder="Short task title", key="nt")
        with c2:
            new_section  = st.selectbox("Section",  sections,                    key="nse")
            new_priority = st.selectbox("Priority", list(PRIORITY.keys()),        key="npr")
        with c3:
            new_desc = st.text_area("Description / Command", height=115,
                                    placeholder="What needs to be done? Paste a command or description.",
                                    key="nd")

        if st.button("Add Task", type="primary", key="btn_add"):
            if new_title.strip():
                new_id = f"CUSTOM-{sum(1 for t in tasks if 'CUSTOM' in t['id'])+1:03d}"
                tasks.append({"id": new_id, "phase": new_phase, "section": new_section,
                               "title": new_title.strip(), "description": new_desc.strip(),
                               "status": "todo", "priority": new_priority, "notes": ""})
                save_tasks(tasks)
                st.success(f"Task added: {new_title}")
                st.rerun()
            else:
                st.error("Title is required.")
        st.markdown("</div>", unsafe_allow_html=True)


# ───────────────────────────────────────────────────────────────────────────
#  MAIN
# ───────────────────────────────────────────────────────────────────────────
def main() -> None:
    tasks   = load_tasks()
    filters = render_sidebar(tasks)

    # Bulk in_progress action
    if st.session_state.pop("_bulk_inprog", False):
        filtered_ids = {t["id"] for t in apply_filters(tasks, filters)}
        for t in tasks:
            if t["id"] in filtered_ids:
                t["status"] = "in_progress"
        save_tasks(tasks)
        st.rerun()

    render_dashboard(tasks)

    filtered = apply_filters(tasks, filters)

    # ── Filter summary bar ──
    chips = []
    if filters["phase"]    != "All Phases":   chips.append(PHASE_SHORT.get(filters["phase"], filters["phase"]))
    if filters["status"]   != "All":          chips.append(filters["status"])
    if filters["priority"] != "All":          chips.append(filters["priority"])
    if filters["section"]  != "All Sections": chips.append(filters["section"].split(".",1)[-1].strip())
    if filters["search"]:                     chips.append(f'"{filters["search"]}"')

    chip_html = "".join(f"<span class='filter-chip'>{c}</span>" for c in chips)
    st.markdown(
        f"<div class='filter-bar'>"
        f"  <span class='showing-txt'>Showing <strong>{len(filtered)}</strong> of {len(tasks)} tasks</span>"
        f"  {chip_html}"
        f"</div>",
        unsafe_allow_html=True
    )

    if not filtered:
        st.info("No tasks match the current filters.")
        render_add_task(tasks)
        return

    # ── Group: Phase → Section → Tasks ──
    phases = sorted(set(t["phase"] for t in filtered))

    for phase in phases:
        color       = PHASE_COLOR.get(phase, "#6c6c99")
        phase_tasks = [t for t in filtered if t["phase"] == phase]
        ph_done     = sum(1 for t in phase_tasks if t["status"] == "done")
        ph_pct      = int(ph_done / len(phase_tasks) * 100) if phase_tasks else 0

        # Phase header row
        st.markdown(
            f"<div style='display:flex;align-items:center;justify-content:space-between;"
            f"margin:2rem 0 .4rem;'>"
            f"  <span class='badge' style='color:{color};background:{color}1a;"
            f"border-color:{color}44;font-size:.72rem;padding:.28rem .9rem;'>{phase}</span>"
            f"  <span style='font-size:.78rem;color:#8888a8;'>{ph_done}/{len(phase_tasks)} done"
            f" &nbsp;·&nbsp; <strong style='color:{color};'>{ph_pct}%</strong></span>"
            f"</div>",
            unsafe_allow_html=True
        )
        st.progress(ph_done / len(phase_tasks) if phase_tasks else 0)

        sections = sorted(set(t["section"] for t in phase_tasks))
        for section in sections:
            sec_tasks = [t for t in phase_tasks if t["section"] == section]
            sec_done  = sum(1 for t in sec_tasks if t["status"] == "done")

            # Sort: blocked first, then in_progress, then todo, then done
            sec_tasks = sorted(sec_tasks, key=lambda t: STATUS[t["status"]]["order"])

            st.markdown(
                f"<div class='section-divider'>"
                f"  <span class='section-divider-label'>{section}</span>"
                f"  <span class='section-divider-count'>{sec_done}/{len(sec_tasks)}</span>"
                f"</div>",
                unsafe_allow_html=True
            )

            for task in sec_tasks:
                render_task(task, tasks)

    st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)
    render_add_task(tasks)

    st.markdown(
        "<div class='footer'>SARA Project Planner &nbsp;·&nbsp; "
        "data saved to <code>planner/tasks.json</code></div>",
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
