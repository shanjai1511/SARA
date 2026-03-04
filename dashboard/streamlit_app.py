"""
SARA Dashboard - Comprehensive Streamlit Application
Full web interface for URL discovery, crawling, and site management.
Run: streamlit run dashboard/streamlit_app.py
"""
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

# Page configuration
st.set_page_config(
    page_title="SARA Crawl Dashboard",
    layout="wide",
    initial_sidebar_state="auto"
)

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

def list_projects_sites() -> Dict[str, List[str]]:
    """Scan url_discovery/ for project/site configs."""
    discovery = ROOT / "url_discovery"
    result = {}
    if not discovery.exists():
        return result
    
    for project_dir in discovery.iterdir():
        if project_dir.is_dir() and not project_dir.name.startswith("."):
            sites = []
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


def get_status_data():
    """Fetch crawl status data."""
    try:
        return get_status()
    except Exception as e:
        return {
            "current_run": None,
            "last_runs": [],
            "_error": str(e)
        }

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

def get_template_content(project_name: str, site_name: str) -> Dict[str, str]:
    """Generate template content for discovery, retriever, and parser."""
    class_name = f"{site_name}_{project_name}"
    class_name = ''.join([word.capitalize() for word in class_name.split('_')])
    
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
            url = url.replace("-page","")
        except Exception as e:
            print(f"Exception occurred: {{e}}")
        return product_url[:10]
"""
    
    discovery_yml = """depth0:
  seed_url: ["",""]
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
domain: {site_name.replace("_",".")}
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
    ["Dashboard", "Run Crawl", "Create Project", "Delete Project", "Manage Data", "Settings"]
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
    
    # History
    if last_runs:
        
        st.markdown('<div class="section-header">📜 Recent Runs</div>', unsafe_allow_html=True)
        
        table_data = []
        for run in last_runs[:20]:
            summary = progress_summary(run.get("progress", {}))
            status = "✅ Success" if run.get("success") else "❌ Failed"
            completed = format_time(run.get("completed_at")) if run.get("completed_at") else "—"
            
            table_data.append({
                "Schedule ID": run.get("schedule_id", "—"),
                "Project": run.get("project", "—"),
                "Site": run.get("site", "—"),
                "Discovery": summary["discovery"],
                "Status": status,
                "Completed": completed
            })
        
        st.dataframe(table_data, use_container_width=True, hide_index=True)
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
            if not project_name or not site_name:
                st.error("⚠️ Please fill in both Project Name and Site Name")
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
# PAGE: SETTINGS
# ============================================================================
elif page == "Settings":
    st.markdown('<div class="section-header">⚙️ Settings</div>', unsafe_allow_html=True)
    
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
    
    
    
    st.subheader("🔧 Environment Info")
    
    env_info = {
        "Project Root": str(ROOT),
        "Python Version": sys.version.split()[0],
        "Working Directory": os.getcwd(),
    }
    
    for key, value in env_info.items():
        st.text(f"{key}: {value}")
    
    
    
    st.subheader("📚 Documentation")
    
    st.info("""
    **Quick Start Guide:**
    
    1. **Create a Project**: Go to "Create Project" and set up a new project with discovery, retriever, and parser
    2. **Run a Crawl**: Use "Run Crawl" to start the pipeline with a schedule ID (e.g., 20260215)
    3. **Monitor**: Check "Dashboard" to see real-time crawl progress
    4. **Manage Data**: Download and preview results in "Manage Data"
    
    **Pipeline Stages:**
    - 🔍 **Discovery**: Finds URLs on target websites
    - 📥 **Retriever**: Fetches page content/HTML
    - 📊 **Parser**: Extracts structured data into CSV
    """)
