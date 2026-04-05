"""
SARA Dashboard - Comprehensive Streamlit Application
Full web interface for URL discovery, crawling, and site management.
Run: streamlit run dashboard/streamlit_app.py
"""
from dotenv import load_dotenv #type: ignore
import os

load_dotenv()
import os as _os
if _os.getenv("WEBSHARE_PROXY_JSON"):
    pass  # env loaded
import sys
import subprocess
from pathlib import Path
import streamlit as st #type: ignore
from datetime import datetime
import base64

import json
import os
from typing import Dict, List, Tuple

# Ensure project root is on path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sdf_module.crawl_status import get_status
from sdf_module.files_import import *
from config.settings import settings as _settings

# Page configuration
st.set_page_config(
    page_title="SARA Crawl Dashboard",
    layout="wide",
    initial_sidebar_state="auto"
)

# ── Authentication gate ───────────────────────────────────────────────────────
# All pages are blocked until the user provides the correct password.
# The password is read from the DASHBOARD_PASSWORD environment variable.


def _check_auth() -> None:
    """Block the entire dashboard behind a password wall.

    Uses st.session_state so the check survives page reruns within the same
    browser session. Only the correct DASHBOARD_PASSWORD unlocks the app.
    """
    if st.session_state.get("authenticated"):
        return  # already authenticated this session

    st.markdown("## SARA — Login Required")
    pwd = st.text_input("Password", type="password", key="_login_pwd")
    if st.button("Login"):
        if pwd == _settings.DASHBOARD_PASSWORD:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password. Please try again.")
    st.stop()  # halt rendering of all subsequent code


_check_auth()

# Custom CSS for 3D Design with elegant color scheme
st.markdown("""
<style>
    /* override default Streamlit padding & toolbar */
    .block-container {
        padding-top: 0rem;
        padding-bottom: 1rem;
    }
    header { visibility: hidden; }

    /* custom header bar (logo + title) */
    .custom-header {
        display: flex;
        align-items: center;      /* vertical center logo & text */
        justify-content: flex-start;  /* left align the whole block */
        gap: 1rem;
        padding: 0.5rem 0;
    }
    .custom-title {
        margin: 0 0 0.2rem 0;   /* small bottom margin to bring subtitle closer */
        font-size: 2rem;
        font-weight: 600;
        line-height: 1.1;
    }
    .custom-subtitle {
        margin: 0;              /* already zero, keep it tight */
        font-size: 0.95rem;
        color: #374151;
        line-height: 1.2;
    }

    /* Main container styling - elegant soft background */
    [data-testid="stMainBlockContainer"] {
        background: linear-gradient(135deg, 0%, #f0f0f0 100%);
    }
    
    /* Card styling with 3D effect - elegant light background */
    .card-3d {
        background: linear-gradient(145deg, #ffffff, #fafafa);
        border-radius: 12px;
        padding: 1.75rem;
        margin: 1.5rem 0;
        box-shadow: 
            0 2px 4px rgba(0, 0, 0, 0.08),
            0 8px 16px rgba(0, 0, 0, 0.1),
            0 16px 32px rgba(44, 62, 80, 0.12);
        border: 1px solid rgba(212, 165, 116, 0.15);
        backdrop-filter: blur(10px);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }
    
    .card-3d:hover {
        transform: translateY(-4px);
        box-shadow: 
            0 4px 8px rgba(44, 62, 80, 0.12),
            0 12px 24px rgba(44, 62, 80, 0.15),
            0 20px 40px rgba(44, 62, 80, 0.15);
    }
    
    /* Section headers - elegant dark blue with gold underline */
    .section-header {
        font-size: 1.3rem;
        font-weight: 700;
        color: #2c3e50;
        margin: 1.5rem 0 1rem 0;
        padding-bottom: 0.75rem;
        border-bottom: 3px solid;
        border-image: linear-gradient(90deg, #c4a853, #d4af85) 1;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    
    /* Input and select styling */
    input, select {
        box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.06);
        border-radius: 8px;
        border: 1px solid #d4d4d4 !important;
        transition: all 0.2s;
        caret-color: transparent;
    }
    
    input:focus, select:focus {
        border-color: #2c3e50 !important;
        box-shadow: 
            inset 0 2px 4px rgba(0, 0, 0, 0.06),
            0 0 0 3px rgba(212, 165, 116, 0.15) !important;
    }
    
    /* Button styling with 3D effect - elegant navy */
    .stButton > button {
        background: linear-gradient(145deg, #2c3e50, #1a2530);
        border: none;
        border-radius: 8px;
        padding: 0.65rem 1.5rem !important;
        font-weight: 600;
        color: white;
        box-shadow: 
            0 4px 6px rgba(44, 62, 80, 0.2),
            0 8px 12px rgba(44, 62, 80, 0.15),
            inset 0 0 0 1px rgba(212, 165, 116, 0.2);
        transition: all 0.2s;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 
            0 6px 10px rgba(44, 62, 80, 0.3),
            0 12px 20px rgba(44, 62, 80, 0.2),
            inset 0 0 0 1px rgba(212, 165, 116, 0.3);
    }
    
    .stButton > button:active {
        transform: translateY(0px);
        box-shadow: 
            0 2px 4px rgba(44, 62, 80, 0.2),
            inset 0 2px 4px rgba(0, 0, 0, 0.1);
    }
    
    /* Metric boxes with 3D depth */
    .metric-box {
        background: linear-gradient(135deg, #ffffff 0%, #fafafa 100%);
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 4px solid #2c3e50;
        box-shadow: 
            0 2px 4px rgba(0, 0, 0, 0.06),
            0 8px 16px rgba(44, 62, 80, 0.08);
        border: 1px solid rgba(212, 165, 116, 0.1);
    }
    
    /* Stage boxes with gradient */
    .stage-box {
        background: linear-gradient(135deg, #f5f7ff 0%, #eff2fa 100%);
        padding: 1.25rem;
        border-radius: 10px;
        border: 1px solid rgba(44, 62, 80, 0.15);
        margin: 0.75rem 0;
        box-shadow: 
            0 2px 4px rgba(44, 62, 80, 0.08),
            0 6px 12px rgba(44, 62, 80, 0.06);
        transition: all 0.3s;
    }
    
    .stage-box:hover {
        transform: translateX(4px);
        border-color: rgba(212, 165, 116, 0.4);
        box-shadow: 
            0 4px 8px rgba(44, 62, 80, 0.12),
            0 8px 16px rgba(212, 165, 116, 0.1);
    }
    
    .stage-box h4 {
        margin: 0 0 0.5rem 0;
        color: #2c3e50;
        font-size: 0.85rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    .stage-box .count {
        font-size: 1.1rem;
        font-weight: 700;
        color: #1f2937;
        font-family: ui-monospace, monospace;
    }
    
    /* Status badges with 3D effect */
    .badge {
        display: inline-block;
        padding: 0.35rem 0.75rem;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 600;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        backdrop-filter: blur(4px);
    }
    
    .badge.ok {
        background: linear-gradient(135deg, #e8f5e9, #c8e6c9);
        color: #2e7d32;
        border: 1px solid #a5d6a7;
    }
    
    .badge.fail {
        background: linear-gradient(135deg, #ffebee, #ffcdd2);
        color: #c62828;
        border: 1px solid #ef9a9a;
    }
    
    .badge.run {
        background: linear-gradient(135deg, #e3f2fd, #bbdefb);
        color: #1565c0;
        border: 1px solid #90caf9;
    }
    
    /* Table styling */
    .dataframe {
        font-size: 0.9rem;
        border-collapse: collapse;
    }
    
    .dataframe thead {
        background: linear-gradient(145deg, #f5f7fa, #e8e8e8);
        border-bottom: 2px solid #2c3e50;
    }
    
    .dataframe tbody tr {
        border-bottom: 1px solid #e5e7eb;
        transition: background-color 0.2s;
    }
    
    .dataframe tbody tr:hover {
        background-color: #f9fafb;
        box-shadow: inset 0 0 0 1px rgba(212, 165, 116, 0.1);
    }
    
    /* Divider styling */
    hr {
        height: 2px;
        border: none;
        background: linear-gradient(90deg, transparent, #2c3e50, transparent);
        margin: 2rem 0;
    }
    
    /* Title styling - elegant gradient */
    .main-title {
        background: linear-gradient(135deg, #2c3e50, #34495e);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-size: 2.5rem;
        font-weight: 800;
        margin-bottom: 0.5rem;
    }
    
    /* Success/Error messages */
    .stSuccess, .stError, .stInfo {
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(44, 62, 80, 0.08);
        border-left: 4px solid #c4a853;
    }
    
    /* Tabs styling */
    .stTabs [data-baseweb="tab-list"] button {
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

import re as _re

_SAFE_NAME = _re.compile(r'^[a-zA-Z0-9_-]+$')


def _validate_dashboard_input(value: str, label: str) -> str | None:
    """Return an error message string if value is unsafe, else None.

    Only allows [a-zA-Z0-9_-] to prevent path traversal and injection
    in file paths, queue names, and subprocess arguments.
    """
    if not value or not _SAFE_NAME.match(value.strip()):
        return (
            f"Invalid {label} '{value}': only letters, digits, underscores, "
            "and hyphens are allowed."
        )
    return None


@st.cache_data(show_spinner=False)
def list_projects_sites() -> Dict[str, List[str]]:
    """Scan url_discovery/ for project/site configs.

    Results are cached in Streamlit to avoid repeated disk walks when the UI
    refreshes often.
    """
    discovery = ROOT / "url_discovery"
    result: Dict[str, List[str]] = {}
    if not discovery.exists():
        return result

    for project_dir in discovery.iterdir():
        if project_dir.is_dir() and not project_dir.name.startswith("."):
            sites: List[str] = []
            for f in project_dir.glob("*.yml"):
                base = f.stem
                if "_" in base and base.endswith(project_dir.name):
                    site = base[: -len(project_dir.name) - 1]
                    if site:
                        sites.append(site)
            if sites:
                result.setdefault(project_dir.name, []).extend(sites)

    for k in result:
        result[k] = sorted(set(result[k]))
    return result


def format_time(iso_string):
    """Format ISO timestamp to readable format."""
    if not iso_string:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return iso_string


def progress_summary(progress):
    """Extract progress summary from progress dict."""
    if not progress:
        return {"discovery": "—", "retriever": "—", "parser": "—"}
    
    discovery = (
        f"{progress.get('discovery_urls', '?')} URLs"
        if progress.get('discovery_urls') is not None else "—"
    )
    
    fetched = progress.get('retriever_fetched', 0)
    total = progress.get('retriever_total')
    retriever = (
        f"{fetched} / {total} pages"
        if total is not None else "—"
    )
    
    records = progress.get('parser_records', 0)
    pages_done = progress.get('parser_pages_done', 0)
    pages_total = progress.get('parser_pages')
    parser = (
        f"{records} records, {pages_done}/{pages_total} pages"
        if pages_total is not None else "—"
    )
    
    return {"discovery": discovery, "retriever": retriever, "parser": parser}


@st.cache_data(ttl=5, show_spinner=False)
def get_status_data():
    """Fetch crawl status data.

    The TTL ensures that rapid UI refreshes don't hammer the JSON file but
    still update every few seconds.
    """
    try:
        return get_status()
    except Exception as e:
        return {"current_run": None, "last_runs": [], "_error": str(e)}

def create_project_structure(base_path: str, project_name: str, site_name: str, py_content: str, yml_content: str) -> Tuple[bool, str]:
    """Create project structure for discovery, retriever, and parser."""
    try:
        project_path = os.path.join(base_path, project_name)
        if not os.path.exists(project_path):
            os.makedirs(project_path)
        
        py_file_path = os.path.join(project_path, f"{site_name}_{project_name}.py")
        yml_file_path = os.path.join(project_path, f"{site_name}_{project_name}.yml")
        
        with open(py_file_path, 'w') as py_file:
            py_file.write(py_content)
        
        with open(yml_file_path, 'w') as yml_file:
            yml_file.write(yml_content)
        
        return True, f"Created files in {project_path}"
    except Exception as e:
        return False, str(e)

def delete_project_structure(base_path: str, project_name: str, site_name: str) -> Tuple[bool, str]:
    """Delete project structure files."""
    try:
        project_path = os.path.join(base_path, project_name)
        
        py_file = os.path.join(project_path, f"{site_name}_{project_name}.py")
        yml_file = os.path.join(project_path, f"{site_name}_{project_name}.yml")
        
        if os.path.exists(py_file):
            os.remove(py_file)
        if os.path.exists(yml_file):
            os.remove(yml_file)
        
        if os.path.exists(project_path) and not os.listdir(project_path):
            os.rmdir(project_path)
        
        return True, f"Deleted {site_name}_{project_name} from {project_name}"
    except Exception as e:
        return False, str(e)

@st.cache_data(show_spinner=False)
def get_template_content(project_name: str, site_name: str) -> Dict[str, str]:
    """Generate template content for discovery, retriever, and parser.

    The results are deterministic and relatively heavy to build, so cache them
    between Streamlit reruns.
    """
    class_name = f"{site_name}_{project_name}"
    class_name = "".join(word.capitalize() for word in class_name.split("_"))

    discovery_py = f"""from sdf_module.url_discovery import *

class {class_name}():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = []
        try:
            pass
        except Exception as e:
            print(f"Exception occurred: {{e}}")
        return pagination_url[:10]

    def get_product_url(self, url, depth, current_depth_level):
        product_url = []
        try:
            url = url.replace("-page", "")
        except Exception as e:
            print(f"Exception occurred: {{e}}")
        return product_url[:10]
"""

    discovery_yml = """depth0:
  seed_url: ["", ""]
  method_name: get_pagination_url
depth1:
  method_name: get_product_url"""

    retriever_py = f"""from sdf_module.url_retriever import *

class {class_name}():
    def get_page_content(self, url, args_hash):
        page_content = sdfFetch.get_page_content_hash(url, args_hash)
        return page_content
"""

    retriever_yml = """request_type: curl
request_params:
  max_retries: 3
  timeout: 30"""

    parser_py = f"""from sdf_module.url_parser import *

class {class_name}():

    @staticmethod
    def modify_page_doc(inhash, page_doc):
        final_data = []
        try:
            pass
        except Exception as e:
            print(f"Exception occurred: {{e}}")
        return final_data

    @staticmethod
    def get_crawl_timestamp(page_doc, inhash):
        current_datetime = datetime.now()
        formatted_datetime = current_datetime.strftime("%b %d, %Y @ %H:%M:%S.%f")[:-3]
        return formatted_datetime

    @staticmethod
    def get_product_name(page_doc, inhash):
        return None

    @staticmethod
    def get_list_price(page_doc, inhash):
        return None
    
    @staticmethod
    def get_selling_price(page_doc, inhash):
        return None
"""

    parser_yml = f"""---
domain: {site_name.replace("_", ".")}
fields:
  product_name:
    desc_of_xpath: "Product name XPath"
    standard_nodeset_range: first
  list_price:
    desc_of_xpath: "List price XPath"
    standard_nodeset_range: first
  selling_price:
    desc_of_xpath: "Selling price XPath"
    standard_nodeset_range: first"""

    return {
        "discovery_py": discovery_py,
        "discovery_yml": discovery_yml,
        "retriever_py": retriever_py,
        "retriever_yml": retriever_yml,
        "parser_py": parser_py,
        "parser_yml": parser_yml,
    }

# ============================================================================
# HEADER & NAVIGATION
# ============================================================================

logo_path = Path(__file__).parent / "logo.png"

# render header as a single block so logo and text sit side-by-side
if logo_path.exists():
    # embed the logo as base64 so it never breaks
    with open(logo_path, "rb") as img_file:
        b64 = base64.b64encode(img_file.read()).decode()
    img_tag = f'<img src="data:image/png;base64,{b64}" width="70" style="margin-right:1rem;" />'
else:
    img_tag = ''

st.markdown(f"""
<div class="custom-header">
    {img_tag}
    <div>
        <h1 class="custom-title">SARA</h1>
        <p class="custom-subtitle">Comprehensive Web Crawling & Data Extraction</p>
    </div>
</div>
""", unsafe_allow_html=True)

# Sidebar navigation
page = st.sidebar.radio(
    "Navigation",
    [
        "Dashboard",
        "Run Crawl",
        "Create Project",
        "Delete Project",
        "Manage Data",
        "Projects and sites",
        "─────────────",          # visual separator (SaaS section)
        "Schedules",
        "Analytics",
        "DLQ Inspector",
        "System Health",
        "API Access",
    ]
)

# ============================================================================
# PAGE: DASHBOARD
# ============================================================================
if page == "Dashboard":
    st.markdown('<div class="section-header">📊 Crawl Dashboard</div>', unsafe_allow_html=True)
    
    projects_data = list_projects_sites()
    status_data = get_status_data()
    current_run = status_data.get("current_run")
    last_runs = status_data.get("last_runs", [])
    
    # Current Run Status
    if current_run:
        st.markdown('<div class="section-header">⚡ Current Run</div>', unsafe_allow_html=True)
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Project", current_run.get("project", "—"))
        with col2:
            st.metric("Site", current_run.get("site", "—"))
        with col3:
            st.metric("Schedule ID", current_run.get("schedule_id", "—"))
        with col4:
            stage = current_run.get("stage", "discovery").replace("_", " ").title()
            st.metric("Stage", stage)
        
        progress = current_run.get("progress", {})
        summary = progress_summary(progress)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <div class='stage-box'>
                <h4>🔍 Discovery</h4>
                <div class='count'>{summary['discovery']}</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div class='stage-box'>
                <h4>📥 Retriever</h4>
                <div class='count'>{summary['retriever']}</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown(f"""
            <div class='stage-box'>
                <h4>📊 Parser</h4>
                <div class='count'>{summary['parser']}</div>
            </div>
            """, unsafe_allow_html=True)
        
        # Auto refresh
        
        if st.button("🔄 Refresh Status", use_container_width=True):
            st.rerun()
    
    # History with Filters
    if last_runs:
        # Extract unique values for filters
        all_projects = sorted(set(run.get("project") for run in last_runs if run.get("project")))
        all_sites = sorted(set(run.get("site") for run in last_runs if run.get("site")))
        all_schedule_ids = sorted(set(run.get("schedule_id") for run in last_runs if run.get("schedule_id")))
        
        # Filter controls
        col1, col2, col3 = st.columns([1, 1, 1], gap="medium")
        
        with col1:
            filter_project = st.selectbox(
                "Filter by Project",
                options=["All Projects"] + all_projects,
                key="filter_project"
            )
        
        with col2:
            # Filter sites based on selected project
            if filter_project == "All Projects":
                filtered_sites = all_sites
            else:
                filtered_sites = sorted(set(
                    run.get("site") for run in last_runs 
                    if run.get("project") == filter_project
                ))
            
            filter_site = st.selectbox(
                "Filter by Site",
                options=["All Sites"] + filtered_sites,
                key="filter_site"
            )
        
        with col3:
            # Filter schedule_ids based on project and site
            if filter_project == "All Projects" and filter_site == "All Sites":
                filtered_schedule_ids = all_schedule_ids
            elif filter_project != "All Projects" and filter_site == "All Sites":
                filtered_schedule_ids = sorted(set(
                    run.get("schedule_id") for run in last_runs 
                    if run.get("project") == filter_project
                ))
            elif filter_project == "All Projects" and filter_site != "All Sites":
                filtered_schedule_ids = sorted(set(
                    run.get("schedule_id") for run in last_runs 
                    if run.get("site") == filter_site
                ))
            else:
                filtered_schedule_ids = sorted(set(
                    run.get("schedule_id") for run in last_runs 
                    if run.get("project") == filter_project and run.get("site") == filter_site
                ))
            
            filter_schedule_id = st.selectbox(
                "Filter by Schedule ID",
                options=["All Schedule IDs"] + filtered_schedule_ids,
                key="filter_schedule"
            )
        
        # Apply filters to data
        filtered_runs = last_runs
        if filter_project != "All Projects":
            filtered_runs = [r for r in filtered_runs if r.get("project") == filter_project]
        if filter_site != "All Sites":
            filtered_runs = [r for r in filtered_runs if r.get("site") == filter_site]
        if filter_schedule_id != "All Schedule IDs":
            filtered_runs = [r for r in filtered_runs if r.get("schedule_id") == filter_schedule_id]
        
        # Display stage counts summary
        if filtered_runs:
            total_discovery = 0
            total_retriever = 0
            total_parser = 0
            
            for run in filtered_runs:
                progress = run.get("progress", {})
                total_discovery += progress.get("discovery_urls", 0)
                total_retriever += progress.get("retriever_fetched", 0)
                total_parser += progress.get("parser_records", 0)
            
            st.markdown("**📊 Stage Counts (Filtered Results):**")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("🔍 Discovery URLs", total_discovery)
            with col2:
                st.metric("📥 Retrieved URLs", total_retriever)
            with col3:
                st.metric("📊 Parsed Records", total_parser)
            with col4:
                st.metric("📋 Total Runs", len(filtered_runs))
        
        # Build and display table
        table_data = []
        for run in filtered_runs[:50]:
            summary = progress_summary(run.get("progress", {}))
            run_status = run.get("status", "in_progress")
            status_display = "✅ Completed" if run_status == "completed" else ("❌ Failed" if run_status == "failed" else "⏳ In Progress")
            completed = format_time(run.get("completed_at")) if run.get("completed_at") else "—"
            
            table_data.append({
                "Schedule ID": run.get("schedule_id", "—"),
                "Project": run.get("project", "—"),
                "Site": run.get("site", "—"),
                "Discovery": summary["discovery"],
                "Retriever": summary["retriever"],
                "Parser": summary["parser"],
                "Status": status_display,
                "Completed": completed
            })
        
        if table_data:
            st.dataframe(table_data, use_container_width=True, hide_index=True)
        else:
            st.info("📌 No runs match the selected filters.")
    else:
        st.info("📌 No crawl history yet. Start your first crawl using the 'Run Crawl' page.")

# ============================================================================
# PAGE: RUN CRAWL
# ============================================================================
elif page == "Run Crawl":
    st.markdown('<div class="section-header">▶️ Run Crawl</div>', unsafe_allow_html=True)
    
    projects_data = list_projects_sites()
    
    if not projects_data:
        st.error("❌ No projects found. Create a project first using 'Create Project' page.")
    else:
        col1, col2, col3 = st.columns([1.5, 1.5, 1.3], gap="medium")
        
        with col1:
            selected_project = st.selectbox(
                "Select Project",
                options=sorted(projects_data.keys()),
                key="run_project"
            )
        
        with col2:
            sites = projects_data.get(selected_project, [])
            selected_site = st.selectbox(
                "Select Site",
                options=sites,
                key="run_site"
            )
        
        with col3:
            schedule_id = st.text_input(
                "Schedule ID",
                placeholder="e.g. 20260215",
                key="run_schedule"
            )
        
        
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("▶️ Start Crawl", use_container_width=True, type="primary"):
                if not schedule_id.strip():
                    st.error("⚠️ Please enter a Schedule ID")
                else:
                    _errors = [
                        _validate_dashboard_input(selected_project, "project"),
                        _validate_dashboard_input(selected_site, "site"),
                        _validate_dashboard_input(schedule_id.strip(), "schedule_id"),
                    ]
                    _errors = [e for e in _errors if e]
                    if _errors:
                        for _err in _errors:
                            st.error(_err)
                    else:
                        try:
                            cmd = [
                                sys.executable,
                                str(ROOT / "crawl_runner.py"),
                                selected_project,
                                selected_site,
                                schedule_id.strip()
                            ]
                            subprocess.Popen(
                                cmd,
                                cwd=str(ROOT),
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                            )
                            st.success(f"✅ Crawl started!\n**{selected_site}** ({selected_project}, {schedule_id})")
                            st.balloons()
                        except Exception as e:
                            st.error(f"❌ Error: {str(e)}")
        
        with col2:
            if st.button("🔄 Refresh", use_container_width=True):
                st.rerun()
        
        
        st.info("**Pipeline stages:**\n1. 🔍 Discovery - Find URLs\n2. 📥 Retriever - Fetch content\n3. 📊 Parser - Extract data")

# ============================================================================
# PAGE: CREATE PROJECT
# ============================================================================
elif page == "Create Project":
    st.markdown('<div class="section-header">➕ Create New Project</div>', unsafe_allow_html=True)
    
    with st.form("create_project_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            project_name = st.text_input(
                "Project Name",
                placeholder="e.g. media_crawl",
                help="Lowercase, use underscores for spaces"
            )
        
        with col2:
            site_name = st.text_input(
                "Site Name",
                placeholder="e.g. vogue_in",
                help="Lowercase, use underscores for spaces"
            )
        
        
        
        col1, col2, col3 = st.columns(3)
        with col1:
            create_discovery = st.checkbox("Discovery", value=True)
        with col2:
            create_retriever = st.checkbox("Retriever", value=True)
        with col3:
            create_parser = st.checkbox("Parser", value=True)
        
        
        
        submitted = st.form_submit_button("✅ Create Project", use_container_width=True, type="primary")
        
        if submitted:
            _name_errors = [
                _validate_dashboard_input(project_name, "project_name") if project_name else None,
                _validate_dashboard_input(site_name, "site_name") if site_name else None,
            ]
            _name_errors = [e for e in _name_errors if e]
            if not project_name or not site_name:
                st.error("⚠️ Please fill in both Project Name and Site Name")
            elif _name_errors:
                for _nerr in _name_errors:
                    st.error(_nerr)
            else:
                success_count = 0
                error_messages = []
                
                # Get templates
                templates = get_template_content(project_name, site_name)
                
                # Create Discovery
                if create_discovery:
                    discovery_path = ROOT / "url_discovery"
                    success, msg = create_project_structure(
                        str(discovery_path),
                        project_name,
                        site_name,
                        templates["discovery_py"],
                        templates["discovery_yml"]
                    )
                    if success:
                        success_count += 1
                        st.success(f"✅ Discovery: {msg}")
                    else:
                        error_messages.append(f"Discovery: {msg}")
                
                # Create Retriever
                if create_retriever:
                    retriever_path = ROOT / "url_retriever"
                    success, msg = create_project_structure(
                        str(retriever_path),
                        project_name,
                        site_name,
                        templates["retriever_py"],
                        templates["retriever_yml"]
                    )
                    if success:
                        success_count += 1
                        st.success(f"✅ Retriever: {msg}")
                    else:
                        error_messages.append(f"Retriever: {msg}")
                
                # Create Parser
                if create_parser:
                    parser_path = ROOT / "url_data_parser"
                    success, msg = create_project_structure(
                        str(parser_path),
                        project_name,
                        site_name,
                        templates["parser_py"],
                        templates["parser_yml"]
                    )
                    if success:
                        success_count += 1
                        st.success(f"✅ Parser: {msg}")
                    else:
                        error_messages.append(f"Parser: {msg}")
                
                
                
                if error_messages:
                    for error in error_messages:
                        st.error(f"❌ {error}")
                else:
                    st.success(f"✅ Project created successfully! {success_count} modules created.")

# ============================================================================
# PAGE: DELETE PROJECT
# ============================================================================
elif page == "Delete Project":
    st.markdown('<div class="section-header">🗑️ Delete Project</div>', unsafe_allow_html=True)
    
    st.warning("⚠️ This action will DELETE all project files. This cannot be undone!")
    
    projects_data = list_projects_sites()
    
    if not projects_data:
        st.info("ℹ️ No projects found to delete.")
    else:
        col1, col2 = st.columns([1.5, 1.5])
        
        with col1:
            selected_project = st.selectbox(
                "Select Project to Delete",
                options=sorted(projects_data.keys()),
                key="del_project"
            )
        
        with col2:
            sites = projects_data.get(selected_project, [])
            selected_site = st.selectbox(
                "Select Site to Delete",
                options=sites,
                key="del_site"
            )
        
        
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            del_discovery = st.checkbox("Delete from Discovery", value=True, key="del_disc")
        with col2:
            del_retriever = st.checkbox("Delete from Retriever", value=True, key="del_retr")
        with col3:
            del_parser = st.checkbox("Delete from Parser", value=True, key="del_pars")
        
        
        
        if st.button("🗑️ Delete Project", use_container_width=True, type="secondary"):
            success_count = 0
            error_messages = []
            
            if del_discovery:
                discovery_path = ROOT / "url_discovery"
                success, msg = delete_project_structure(str(discovery_path), selected_project, selected_site)
                if success:
                    success_count += 1
                    st.success(f"✅ Discovery: Deleted")
                else:
                    error_messages.append(f"Discovery: {msg}")
            
            if del_retriever:
                retriever_path = ROOT / "url_retriever"
                success, msg = delete_project_structure(str(retriever_path), selected_project, selected_site)
                if success:
                    success_count += 1
                    st.success(f"✅ Retriever: Deleted")
                else:
                    error_messages.append(f"Retriever: {msg}")
            
            if del_parser:
                parser_path = ROOT / "url_data_parser"
                success, msg = delete_project_structure(str(parser_path), selected_project, selected_site)
                if success:
                    success_count += 1
                    st.success(f"✅ Parser: Deleted")
                else:
                    error_messages.append(f"Parser: {msg}")
            
            
            
            if error_messages:
                for error in error_messages:
                    st.error(f"❌ {error}")
            else:
                st.success(f"✅ Project deleted successfully! {success_count} modules removed.")

# ============================================================================
# PAGE: MANAGE DATA
# ============================================================================
elif page == "Manage Data":
    st.markdown('<div class="section-header">📦 Manage Data</div>', unsafe_allow_html=True)
    
    status_data = get_status_data()
    all_runs = status_data.get("last_runs", [])
    
    if not all_runs:
        st.info("ℹ️ No data available yet.")
    else:
        col1, col2, col3 = st.columns(3)
        
        # Extract unique projects
        all_projects = sorted(set(r.get("project") for r in all_runs if r.get("project")))
        
        with col1:
            filter_project = st.selectbox("Filter Project", options=["All"] + all_projects)
        
        # Filter runs
        filtered_runs = all_runs
        if filter_project != "All":
            filtered_runs = [r for r in filtered_runs if r.get("project") == filter_project]
        
        with col2:
            all_sites = sorted(set(r.get("site") for r in filtered_runs if r.get("site")))
            filter_site = st.selectbox("Filter Site", options=["All"] + all_sites)
        
        if filter_site != "All":
            filtered_runs = [r for r in filtered_runs if r.get("site") == filter_site]
        
        with col3:
            all_schedules = sorted(set(r.get("schedule_id") for r in filtered_runs if r.get("schedule_id")), reverse=True)
            filter_schedule = st.selectbox("Filter Schedule", options=all_schedules[:10])
        
        if filter_schedule:
            filtered_runs = [r for r in filtered_runs if r.get("schedule_id") == filter_schedule]
        
        
        
        if filtered_runs:
            run = filtered_runs[0]
            project = run.get("project")
            site = run.get("site")
            schedule = run.get("schedule_id")
            
            # Try to find CSV
            csv_path = ROOT / "scrape_output" / "parser_output" / project / f"{site}_{project}_{schedule}" / f"{site}_{project}.csv"
            
            if csv_path.exists():
                with open(csv_path, "rb") as f:
                    csv_data = f.read()
                
                st.success(f"✅ CSV found: {csv_path.name}")
                st.download_button(
                    label="📥 Download CSV",
                    data=csv_data,
                    file_name=f"{site}_{project}_{schedule}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                
                # Show preview
                try:
                    import pandas as pd #type: ignore
                    df = pd.read_csv(csv_path)
                    
                    st.markdown(f"**Preview** ({len(df)} rows)")
                    st.dataframe(df.head(20), use_container_width=True)
                except Exception as e:
                    st.error(f"Could not preview: {e}")
            else:
                st.error(f"❌ CSV not found: {csv_path.relative_to(ROOT)}")

# ============================================================================
# PAGE: Projects and sites
# ============================================================================
elif page == "Projects and sites":
    st.markdown('<div class="section-header">⚙️ Projects and sites</div>', unsafe_allow_html=True)
    
    st.subheader("📁 Project Structure")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        discovery_path = ROOT / "url_discovery"
        discovery_count = len(list(discovery_path.glob("*"))) if discovery_path.exists() else 0
        st.metric("Discovery Projects", discovery_count)
    
    with col2:
        retriever_path = ROOT / "url_retriever"
        retriever_count = len(list(retriever_path.glob("*"))) if retriever_path.exists() else 0
        st.metric("Retriever Projects", retriever_count)
    
    with col3:
        parser_path = ROOT / "url_data_parser"
        parser_count = len(list(parser_path.glob("*"))) if parser_path.exists() else 0
        st.metric("Parser Projects", parser_count)
    
    
    
    st.subheader("📊 Output Data")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        discovery_output = ROOT / "scrape_output" / "discovery_output"
        discovery_files = len(list(discovery_output.glob("*/*.txt"))) if discovery_output.exists() else 0
        st.metric("Discovery Outputs", discovery_files)
    
    with col2:
        parser_output = ROOT / "scrape_output" / "parser_output"
        parser_files = len(list(parser_output.glob("*/*.csv"))) if parser_output.exists() else 0
        st.metric("Parser Outputs", parser_files)
    
    with col3:
        retriever_output = ROOT / "scrape_output" / "retriever_output"
        retriever_files = len(list(retriever_output.glob("*/*/*.txt"))) if retriever_output.exists() else 0
        st.metric("Retriever Outputs", retriever_files)

# ── Separator item: do nothing ────────────────────────────────────────────────
elif page == "─────────────":
    st.info("Select a page from the sidebar.")

# ============================================================================
# ============================================================================
# PAGE: SCHEDULES
# ============================================================================
elif page == "Schedules":
    st.markdown('<div class="section-header">🕐 Crawl Schedules</div>', unsafe_allow_html=True)
    st.markdown("Set per-site crawl frequency. The scheduler picks up changes within 5 minutes.")

    SCHEDULES_FILE = ROOT / "config" / "schedules.json"

    def _load_schedules():
        if not SCHEDULES_FILE.exists():
            return {}
        with open(SCHEDULES_FILE, encoding="utf-8") as f:
            return json.load(f)

    def _save_schedules(data):
        with open(SCHEDULES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    projects_data = list_projects_sites()
    schedules = _load_schedules()

    if not projects_data:
        st.error("No projects found. Create a project first.")
    else:
        # ── Scheduler status ──────────────────────────────────────────────────
        sched_running = False
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "sara-scheduler"],
                capture_output=True, text=True
            )
            sched_running = result.stdout.strip() == "active"
        except Exception:
            pass

        if sched_running:
            st.success("✅ Scheduler service is running")
        else:
            st.warning("⚠️ Scheduler service is not running — start it with: `sudo systemctl start sara-scheduler`")

        st.divider()

        # ── Per-site schedule editor ──────────────────────────────────────────
        FREQ_OPTIONS = ["disabled", "hourly", "daily", "weekly", "custom"]
        DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

        updated = False

        for project, sites in sorted(projects_data.items()):
            st.markdown(f"### {project.replace('_', ' ').title()}")
            proj_schedules = schedules.setdefault(project, {})

            for site in sorted(sites):
                site_cfg = proj_schedules.setdefault(site, {
                    "frequency": "disabled", "hour": 2, "minute": 0,
                    "day_of_week": "mon", "cron": "0 2 * * *",
                    "enabled": False, "last_run": None
                })

                with st.expander(f"**{site}**  —  _{site_cfg.get('frequency', 'disabled')}_", expanded=False):
                    col1, col2, col3, col4 = st.columns([1.5, 1, 1, 1.5])

                    with col1:
                        freq = st.selectbox(
                            "Frequency", FREQ_OPTIONS,
                            index=FREQ_OPTIONS.index(site_cfg.get("frequency", "disabled")),
                            key=f"freq_{project}_{site}"
                        )
                    with col2:
                        hour = st.number_input(
                            "Hour (0-23)", 0, 23,
                            value=int(site_cfg.get("hour", 2)),
                            key=f"hour_{project}_{site}"
                        )
                    with col3:
                        minute = st.number_input(
                            "Minute (0-59)", 0, 59,
                            value=int(site_cfg.get("minute", 0)),
                            key=f"min_{project}_{site}"
                        )
                    with col4:
                        if freq == "weekly":
                            day_of_week = st.selectbox(
                                "Day of week", DAYS,
                                index=DAYS.index(site_cfg.get("day_of_week", "mon")),
                                key=f"dow_{project}_{site}"
                            )
                        elif freq == "custom":
                            cron_expr = st.text_input(
                                "Cron expression",
                                value=site_cfg.get("cron", "0 2 * * *"),
                                key=f"cron_{project}_{site}"
                            )
                        else:
                            day_of_week = site_cfg.get("day_of_week", "mon")
                            cron_expr = site_cfg.get("cron", "0 2 * * *")

                    last_run = site_cfg.get("last_run")
                    if last_run:
                        st.caption(f"Last run: {last_run[:19]}")

                    if st.button(f"💾 Save", key=f"save_{project}_{site}"):
                        proj_schedules[site] = {
                            "frequency": freq,
                            "hour": int(hour),
                            "minute": int(minute),
                            "day_of_week": day_of_week if freq == "weekly" else site_cfg.get("day_of_week", "mon"),
                            "cron": cron_expr if freq == "custom" else site_cfg.get("cron", "0 2 * * *"),
                            "enabled": freq != "disabled",
                            "last_run": site_cfg.get("last_run"),
                        }
                        schedules[project] = proj_schedules
                        _save_schedules(schedules)
                        st.success(f"✅ Saved schedule for {site}")
                        updated = True

        if updated:
            st.info("Scheduler will pick up changes within 5 minutes.")

# ============================================================================
# PAGE: ANALYTICS
# ============================================================================
elif page == "Analytics":
    st.markdown('<div class="section-header">📈 Analytics & Throughput</div>', unsafe_allow_html=True)

    try:
        import pandas as pd
        import plotly.express as px
        import plotly.graph_objects as go
    except ImportError:
        st.error("Install pandas and plotly: pip install pandas plotly")
        st.stop()

    status_data = get_status_data()
    all_runs = status_data.get("last_runs", [])

    if not all_runs:
        st.info("No crawl history yet. Run some crawls to see analytics.")
    else:
        # ── KPI row ─────────────────────────────────────────────────────────
        total_records  = sum(r.get("progress", {}).get("parser_records", 0)  for r in all_runs)
        total_pages    = sum(r.get("progress", {}).get("retriever_fetched", 0) for r in all_runs)
        total_disc_urls = sum(r.get("progress", {}).get("discovery_urls", 0) for r in all_runs)
        completed_runs = sum(1 for r in all_runs if r.get("status") == "completed")
        success_rate   = (completed_runs / len(all_runs) * 100) if all_runs else 0

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Total Records", f"{total_records:,}")
        k2.metric("Pages Fetched", f"{total_pages:,}")
        k3.metric("URLs Discovered", f"{total_disc_urls:,}")
        k4.metric("Success Rate", f"{success_rate:.1f}%")
        k5.metric("Total Runs", len(all_runs))

        st.divider()

        # ── Records by site chart ────────────────────────────────────────────
        site_data = {}
        for r in all_runs:
            key = f"{r.get('site','?')} / {r.get('project','?')}"
            site_data[key] = site_data.get(key, 0) + r.get("progress", {}).get("parser_records", 0)

        df_sites = pd.DataFrame(
            [{"Site / Project": k, "Records": v} for k, v in site_data.items()]
        ).sort_values("Records", ascending=False).head(15)

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Records by Site**")
            if not df_sites.empty:
                fig = px.bar(
                    df_sites, x="Records", y="Site / Project", orientation="h",
                    color="Records", color_continuous_scale="Blues",
                    template="plotly_white",
                )
                fig.update_layout(height=400, showlegend=False, yaxis_title="",
                                  margin=dict(l=0, r=0, t=10, b=10))
                st.plotly_chart(fig, use_container_width=True)

        # ── Records vs Pages fetched per run ─────────────────────────────────
        with col2:
            st.markdown("**Records vs Pages (last 20 runs)**")
            run_rows = []
            for r in all_runs[:20]:
                p = r.get("progress", {})
                run_rows.append({
                    "Run": r.get("schedule_id", "?")[-8:],
                    "Records": p.get("parser_records", 0),
                    "Pages": p.get("retriever_fetched", 0),
                    "Site": r.get("site", "?"),
                    "Status": r.get("status", "?"),
                })
            df_runs = pd.DataFrame(run_rows)
            if not df_runs.empty:
                fig2 = go.Figure()
                fig2.add_trace(go.Bar(
                    name="Records", x=df_runs["Run"], y=df_runs["Records"],
                    marker_color="#2c3e50"
                ))
                fig2.add_trace(go.Bar(
                    name="Pages", x=df_runs["Run"], y=df_runs["Pages"],
                    marker_color="#c4a853"
                ))
                fig2.update_layout(
                    barmode="group", template="plotly_white", height=400,
                    legend=dict(orientation="h", y=1.02, x=1, xanchor="right"),
                    margin=dict(l=0, r=0, t=10, b=10),
                )
                st.plotly_chart(fig2, use_container_width=True)

        # ── Pipeline funnel ──────────────────────────────────────────────────
        st.markdown("**Pipeline Conversion Funnel**")
        funnel_col1, funnel_col2 = st.columns([1, 2])
        with funnel_col1:
            st.markdown(f"""
            <div class='stage-box'>
                <h4>🔍 Discovery</h4>
                <div class='count'>{total_disc_urls:,} URLs</div>
            </div>
            <div class='stage-box'>
                <h4>📥 Retriever</h4>
                <div class='count'>{total_pages:,} Pages</div>
                <small style='color:#6b7280'>
                    {(total_pages/total_disc_urls*100) if total_disc_urls else 0:.1f}% of discovered
                </small>
            </div>
            <div class='stage-box'>
                <h4>📊 Parser</h4>
                <div class='count'>{total_records:,} Records</div>
                <small style='color:#6b7280'>
                    {(total_records/total_pages*100) if total_pages else 0:.1f}% of fetched
                </small>
            </div>
            """, unsafe_allow_html=True)

        with funnel_col2:
            if total_disc_urls > 0:
                fig_funnel = go.Figure(go.Funnel(
                    y=["Discovery (URLs)", "Retriever (Pages)", "Parser (Records)"],
                    x=[total_disc_urls, total_pages, total_records],
                    textinfo="value+percent initial",
                    marker=dict(color=["#2c3e50", "#c4a853", "#27ae60"]),
                ))
                fig_funnel.update_layout(
                    template="plotly_white", height=300,
                    margin=dict(l=0, r=0, t=10, b=10),
                )
                st.plotly_chart(fig_funnel, use_container_width=True)

        # ── Run history table ────────────────────────────────────────────────
        st.markdown("**Run History**")
        df_history = pd.DataFrame([
            {
                "Schedule ID": r.get("schedule_id", "—"),
                "Project": r.get("project", "—"),
                "Site": r.get("site", "—"),
                "Discovery": r.get("progress", {}).get("discovery_urls", 0),
                "Fetched": r.get("progress", {}).get("retriever_fetched", 0),
                "Records": r.get("progress", {}).get("parser_records", 0),
                "Status": "✅" if r.get("status") == "completed" else ("❌" if r.get("status") == "failed" else "⏳"),
                "Completed": format_time(r.get("completed_at", "")),
            }
            for r in all_runs[:50]
        ])
        st.dataframe(df_history, use_container_width=True, hide_index=True)

# ============================================================================
# PAGE: DLQ INSPECTOR
# ============================================================================
elif page == "DLQ Inspector":
    st.markdown('<div class="section-header">☠️ Dead Letter Queue Inspector</div>', unsafe_allow_html=True)
    st.markdown(
        "Messages land here after **3 failed retries**. "
        "Inspect the error, fix the root cause, then requeue."
    )

    import json as _json

    # ── Queue depth overview ─────────────────────────────────────────────────
    from core.broker import get_sync_channel, dlq_name
    from config.settings import settings as _cfg

    def _get_dlq_depths() -> dict[str, int]:
        try:
            conn, ch = get_sync_channel(_cfg.CLOUDAMQP_URL, max_attempts=1, base_backoff=1.0)
            depths = {}
            for stage in ("discovery", "retriever", "parser"):
                q = dlq_name(stage)
                try:
                    r = ch.queue_declare(queue=q, passive=True)
                    depths[stage] = r.method.message_count
                except Exception:
                    depths[stage] = 0
            conn.close()
            return depths
        except Exception as e:
            return {"error": str(e)}

    if st.button("🔄 Refresh", key="dlq_refresh"):
        st.cache_data.clear()

    depths = _get_dlq_depths()
    if "error" in depths:
        st.error(f"Cannot connect to RabbitMQ: {depths['error']}")
    else:
        d1, d2, d3 = st.columns(3)
        d1.metric("Discovery DLQ", depths.get("discovery", 0),
                  delta=None if depths.get("discovery", 0) == 0 else f"⚠️ {depths['discovery']} messages")
        d2.metric("Retriever DLQ", depths.get("retriever", 0),
                  delta=None if depths.get("retriever", 0) == 0 else f"⚠️ {depths['retriever']} messages")
        d3.metric("Parser DLQ",    depths.get("parser", 0),
                  delta=None if depths.get("parser", 0) == 0 else f"⚠️ {depths['parser']} messages")

    st.divider()

    # ── Browse DLQ ───────────────────────────────────────────────────────────
    selected_stage = st.selectbox("Inspect stage", ["retriever", "discovery", "parser"])
    peek_limit = st.slider("Messages to peek", 1, 100, 20)

    def _peek_dlq(stage: str, limit: int) -> list[dict]:
        """Peek at messages without consuming them."""
        import pika as _pika
        try:
            conn, ch = get_sync_channel(_cfg.CLOUDAMQP_URL, max_attempts=1, base_backoff=1.0)
            dlq = dlq_name(stage)
            msgs = []
            for _ in range(limit):
                method, props, body = ch.basic_get(queue=dlq, auto_ack=False)
                if body is None:
                    break
                try:
                    payload = _json.loads(body)
                    dlq_meta = payload.get("_dlq", {})
                    msgs.append({
                        "url": payload.get("url", "—"),
                        "site": payload.get("site", "—"),
                        "project": payload.get("project", "—"),
                        "error": dlq_meta.get("error", "unknown"),
                        "retries": payload.get("_retry_count", 0),
                        "failed_at": format_time(
                            datetime.utcfromtimestamp(dlq_meta["failed_at"]).isoformat()
                            if dlq_meta.get("failed_at") else ""
                        ),
                        "_raw": payload,
                    })
                except Exception:
                    pass
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            conn.close()
            return msgs
        except Exception as e:
            return [{"error": str(e)}]

    if st.button(f"🔍 Peek {selected_stage} DLQ", type="primary"):
        msgs = _peek_dlq(selected_stage, peek_limit)
        if not msgs:
            st.success("DLQ is empty!")
        elif "error" in msgs[0]:
            st.error(msgs[0]["error"])
        else:
            try:
                import pandas as pd
                df_dlq = pd.DataFrame([
                    {k: v for k, v in m.items() if k != "_raw"}
                    for m in msgs
                ])
                st.dataframe(df_dlq, use_container_width=True, hide_index=True)
            except ImportError:
                for m in msgs:
                    st.code(_json.dumps({k: v for k, v in m.items() if k != "_raw"}, indent=2))

    st.divider()

    # ── Requeue controls ─────────────────────────────────────────────────────
    st.markdown("**Requeue / Discard**")
    col1, col2 = st.columns(2)

    with col1:
        requeue_limit = st.number_input("Max messages to requeue", 1, 500, 50)
        if st.button(f"♻️ Requeue {selected_stage} DLQ → main queue", type="primary", use_container_width=True):
            from core.broker import publish_sync, EXCHANGE_DISCOVERY, EXCHANGE_RETRIEVER, EXCHANGE_PARSER
            exchange_map = {
                "discovery": EXCHANGE_DISCOVERY,
                "retriever": EXCHANGE_RETRIEVER,
                "parser": EXCHANGE_PARSER,
            }
            try:
                conn, ch = get_sync_channel(_cfg.CLOUDAMQP_URL, max_attempts=1)
                dlq = dlq_name(selected_stage)
                requeued = 0
                for _ in range(requeue_limit):
                    method, props, body = ch.basic_get(queue=dlq, auto_ack=False)
                    if body is None:
                        break
                    try:
                        payload = _json.loads(body)
                        payload.pop("_dlq", None)
                        payload["_retry_count"] = 0
                        site = payload.get("site", "unknown")
                        project = payload.get("project", "unknown")
                        publish_sync(ch, exchange_map[selected_stage],
                                     f"{selected_stage}.{site}.{project}", payload)
                        ch.basic_ack(delivery_tag=method.delivery_tag)
                        requeued += 1
                    except Exception:
                        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                conn.close()
                st.success(f"♻️ Requeued {requeued} messages from {selected_stage} DLQ")
            except Exception as e:
                st.error(f"Requeue failed: {e}")

    with col2:
        st.warning("Discard permanently removes messages from the DLQ.")
        if st.button(f"🗑️ Discard all {selected_stage} DLQ messages", use_container_width=True):
            try:
                conn, ch = get_sync_channel(_cfg.CLOUDAMQP_URL, max_attempts=1)
                ch.queue_purge(queue=dlq_name(selected_stage))
                conn.close()
                st.success(f"DLQ {selected_stage} purged.")
            except Exception as e:
                st.error(f"Purge failed: {e}")

# ============================================================================
# PAGE: SYSTEM HEALTH
# ============================================================================
elif page == "System Health":
    st.markdown('<div class="section-header">❤️ System Health</div>', unsafe_allow_html=True)

    from config.settings import settings as _cfg
    from core.broker import get_sync_channel
    from core.proxy_manager import ProxyManager
    from core.storage import get_storage

    if st.button("🔄 Refresh Health", key="health_refresh"):
        st.cache_data.clear()

    # ── RabbitMQ ──────────────────────────────────────────────────────────────
    st.markdown("### Message Broker (RabbitMQ)")
    try:
        conn, ch = get_sync_channel(_cfg.CLOUDAMQP_URL, max_attempts=1, base_backoff=1.0)
        conn.close()
        st.success("✅ RabbitMQ — Connected")
        st.code(_cfg.CLOUDAMQP_URL.split("@")[-1] if "@" in _cfg.CLOUDAMQP_URL else _cfg.CLOUDAMQP_URL[:40])
    except Exception as e:
        st.error(f"❌ RabbitMQ — {e}")

    # ── Redis ─────────────────────────────────────────────────────────────────
    st.markdown("### Cache / Dedup (Redis)")
    if _cfg.redis_enabled:
        try:
            import redis as _redis_sync
            r = _redis_sync.from_url(_cfg.REDIS_URL, socket_timeout=2)
            info = r.info("memory")
            mem_mb = info.get("used_memory_human", "?")
            st.success(f"✅ Redis — Connected (memory: {mem_mb})")
        except Exception as e:
            st.error(f"❌ Redis — {e}")
    else:
        st.info("Redis not configured (REDIS_URL not set). Bloom filter and rate limiter are in-process only.")

    # ── Storage ───────────────────────────────────────────────────────────────
    st.markdown("### Storage")
    store = get_storage(base_dir=ROOT / "scrape_output" / "raw_html")
    storage_type = "S3" if "S3Storage" in type(store).__name__ else "Local Filesystem"
    if storage_type == "S3":
        st.success(f"✅ Storage — S3 (bucket: {_cfg.SARA_S3_BUCKET})")
    else:
        raw_dir = ROOT / "scrape_output" / "raw_html"
        try:
            import shutil
            total, used, free = shutil.disk_usage(ROOT)
            free_gb = free / (1024 ** 3)
            st.info(f"Local Filesystem — {raw_dir.relative_to(ROOT)} | Free: {free_gb:.1f} GB")
        except Exception:
            st.info(f"Local Filesystem — {raw_dir}")

    # ── Output file sizes ─────────────────────────────────────────────────────
    st.markdown("### Output Directories")
    cols = st.columns(3)
    dirs = [
        ("discovery_output", "Discovery"),
        ("retriever_output", "Retriever"),
        ("parser_output", "Parser"),
    ]
    for i, (subdir, label) in enumerate(dirs):
        p = ROOT / "scrape_output" / subdir
        if p.exists():
            files = list(p.rglob("*"))
            total_bytes = sum(f.stat().st_size for f in files if f.is_file())
            total_mb = total_bytes / (1024 ** 2)
            cols[i].metric(f"{label} Output", f"{len([f for f in files if f.is_file()])} files",
                           delta=f"{total_mb:.1f} MB")
        else:
            cols[i].metric(f"{label} Output", "0 files")

    # ── Proxy pool ────────────────────────────────────────────────────────────
    st.markdown("### Proxy Pool")
    mgr = ProxyManager.from_env()
    stats = mgr.stats()
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Total Proxies", stats["total"])
    p2.metric("Healthy", stats["healthy"],
              delta="OK" if stats["healthy"] == stats["total"] else f"-{stats['degraded']} degraded")
    p3.metric("Degraded", stats["degraded"])
    p4.metric("Avg Success Rate", f"{stats['avg_success_rate']*100:.1f}%")

    if stats["total"] > 0:
        report = mgr.health_report()
        try:
            import pandas as pd
            df_proxy = pd.DataFrame(report)
            st.dataframe(df_proxy, use_container_width=True, hide_index=True)
        except ImportError:
            st.json(report)

    # ── Change detection stats ─────────────────────────────────────────────
    st.markdown("### Change Detection Cache")
    from core.change_detection import FileChangeStore
    cs = FileChangeStore(path=ROOT / "logs" / "change_state.json")
    cs_stats = cs.stats()
    c1, c2 = st.columns(2)
    c1.metric("Tracked URLs", f"{cs_stats['total_urls']:,}")
    c2.metric("Total Changes Detected", f"{cs_stats['total_changes']:,}")

    # ── Settings summary (non-secret) ─────────────────────────────────────────
    st.markdown("### Configuration")
    config_rows = {
        "NUM_FETCH_WORKERS": _cfg.NUM_FETCH_WORKERS,
        "NUM_PARSE_WORKERS": _cfg.NUM_PARSE_WORKERS,
        "MAX_URLS": _cfg.MAX_URLS,
        "FETCH_DELAY": f"{_cfg.FETCH_DELAY}s",
        "FETCH_SLEEP_SEC": f"{_cfg.FETCH_SLEEP_SEC}s",
        "Redis": "enabled" if _cfg.redis_enabled else "disabled",
        "S3": f"s3://{_cfg.SARA_S3_BUCKET}" if _cfg.s3_enabled else "local",
        "API Auth": "enabled" if _cfg.api_auth_enabled else "dev mode (no key)",
    }
    try:
        import pandas as pd
        st.dataframe(
            pd.DataFrame(list(config_rows.items()), columns=["Setting", "Value"]),
            use_container_width=True, hide_index=True,
        )
    except ImportError:
        st.json(config_rows)

# ============================================================================
# PAGE: API ACCESS
# ============================================================================
elif page == "API Access":
    st.markdown('<div class="section-header">🔌 API Access</div>', unsafe_allow_html=True)
    st.markdown(
        "SARA exposes a REST API (FastAPI) for programmatic control. "
        "Start the API server with:"
    )
    st.code("uvicorn services.api.main:app --host 0.0.0.0 --port 8080 --reload", language="bash")

    from config.settings import settings as _cfg

    # ── Live API test ─────────────────────────────────────────────────────────
    st.markdown("### Live API Health Check")
    api_base = st.text_input(
        "API Base URL",
        value=os.environ.get("SARA_API_BASE_URL", "http://localhost:8080"),
        key="api_base_url",
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🏓 Ping /health", use_container_width=True):
            try:
                import httpx
                resp = httpx.get(f"{api_base}/health", timeout=5)
                if resp.status_code == 200:
                    st.success("✅ API is reachable")
                    st.json(resp.json())
                else:
                    st.error(f"HTTP {resp.status_code}")
            except Exception as e:
                st.error(f"Connection failed: {e}")

    with col2:
        if st.button("📊 Get /metrics/summary", use_container_width=True):
            try:
                import httpx
                headers = {}
                if _cfg.SARA_API_KEY:
                    headers["Authorization"] = f"Bearer {_cfg.SARA_API_KEY}"
                resp = httpx.get(f"{api_base}/metrics/summary", headers=headers, timeout=5)
                if resp.status_code == 200:
                    st.json(resp.json())
                else:
                    st.error(f"HTTP {resp.status_code}: {resp.text[:200]}")
            except Exception as e:
                st.error(f"Request failed: {e}")

    # ── Endpoint reference ────────────────────────────────────────────────────
    st.divider()
    st.markdown("### Endpoint Reference")

    endpoints = [
        ("GET",    "/health",                  "System health (no auth required)"),
        ("GET",    "/docs",                    "Interactive Swagger UI"),
        ("POST",   "/crawls/trigger",          "Launch a crawl pipeline"),
        ("GET",    "/crawls/status",           "List current + recent runs"),
        ("GET",    "/crawls/queue/depth",      "RabbitMQ queue depths"),
        ("GET",    "/crawls/dlq/{stage}",      "Peek dead-letter queue"),
        ("POST",   "/crawls/dlq/{stage}/requeue", "Requeue DLQ messages"),
        ("GET",    "/sites",                   "List all configured sites"),
        ("POST",   "/sites",                   "Create a new site"),
        ("DELETE", "/sites/{project}/{site}",  "Delete a site"),
        ("GET",    "/sites/{project}/{site}/validate", "Validate site config"),
        ("GET",    "/proxy/health",            "Proxy pool health"),
        ("GET",    "/metrics/summary",         "Analytics summary"),
    ]

    try:
        import pandas as pd
        df_ep = pd.DataFrame(endpoints, columns=["Method", "Path", "Description"])
        st.dataframe(df_ep, use_container_width=True, hide_index=True)
    except ImportError:
        for method, path, desc in endpoints:
            st.markdown(f"**{method}** `{path}` — {desc}")

    # ── Code examples ─────────────────────────────────────────────────────────
    st.divider()
    st.markdown("### Quick-Start Examples")

    tab1, tab2, tab3 = st.tabs(["Trigger a Crawl", "List Runs", "Requeue DLQ"])

    with tab1:
        st.code(f"""import httpx

response = httpx.post(
    "{api_base}/crawls/trigger",
    json={{
        "project": "commerce_crawl",
        "site": "myntra_com",
        "schedule_id": "20260405",
        "use_async_worker": True,
        "priority": 8
    }},
    headers={{"Authorization": "Bearer YOUR_API_KEY"}},
)
print(response.json())
""", language="python")

    with tab2:
        st.code(f"""import httpx

response = httpx.get(
    "{api_base}/crawls/status",
    params={{"project": "commerce_crawl", "limit": 10}},
    headers={{"Authorization": "Bearer YOUR_API_KEY"}},
)
for run in response.json()["last_runs"]:
    print(run["site"], run["status"], run["progress"])
""", language="python")

    with tab3:
        st.code(f"""import httpx

# Requeue all retriever DLQ messages
response = httpx.post(
    "{api_base}/crawls/dlq/retriever/requeue",
    params={{"limit": 500}},
    headers={{"Authorization": "Bearer YOUR_API_KEY"}},
)
print(f"Requeued: {{response.json()['requeued']}} messages")
""", language="python")

    # ── Auth info ─────────────────────────────────────────────────────────────
    st.divider()
    st.markdown("### Authentication")
    if _cfg.api_auth_enabled:
        st.success("API key is configured (SARA_API_KEY is set).")
        st.markdown("Pass it as a Bearer token in the `Authorization` header:")
        st.code('Authorization: Bearer <your-key>', language="http")
    else:
        st.warning(
            "No API key configured — API is in **dev mode** (unauthenticated). "
            "Set `SARA_API_KEY` in your `.env` file before deploying."
        )