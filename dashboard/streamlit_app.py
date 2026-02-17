"""
SARA Dashboard - Streamlit Version
Real-time crawl progress monitoring + start crawls from the UI.
Run: streamlit run dashboard/streamlit_app.py
"""
import sys
import subprocess
from pathlib import Path
import streamlit as st
from datetime import datetime

# Ensure project root is on path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sdf_module.crawl_status import get_status

# Page configuration
st.set_page_config(
    page_title="SARA Crawl Dashboard",

    layout="wide",
    initial_sidebar_state="auto"
)

# Custom CSS for 3D Design with elegant color scheme
st.markdown("""
<style>
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
</style>
""", unsafe_allow_html=True)


def list_projects_sites():
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


# Title and header
logo_path = Path(__file__).parent / "logo.png"

# Create header with logo and title in same line
if logo_path.exists():
    header_col1, header_col2 = st.columns([0.08, 0.92], gap="medium", vertical_alignment="center")
    with header_col1:
        st.image(str(logo_path), use_container_width=True)
    with header_col2:
        st.markdown('<h1 class="main-title" style="margin: 0 0 0.1rem 20px; display: inline; vertical-align: middle;">SARA Crawl Board</h1><p style="margin: 0 0 0 20px; font-size: 0.95rem; color: #374151;">Real-time crawl progress monitoring & management</p>', unsafe_allow_html=True)
else:
    st.markdown('<h1 class="main-title" style="margin-bottom: 0.1rem;">SARA Crawl Board</h1>\n**Real-time crawl progress monitoring & management**', unsafe_allow_html=True)

st.markdown("---")

# Get projects and status data
projects_data = list_projects_sites()
status_data = get_status_data()
current_run = status_data.get("current_run")
last_runs = status_data.get("last_runs", [])

# ============================================================================
# SECTION 1: Run Crawl
# ============================================================================
st.markdown('<div class="section-header">Run Crawl</div>', unsafe_allow_html=True)

col1, col2, col3, col4, col5 = st.columns([1.3, 1.3, 1.3, 0.7, 0.7], gap="small")

with col1:
    selected_project = st.selectbox(
        "Project",
        options=[""] + sorted(projects_data.keys()),
        key="run_project",
        index=0
    )

with col2:
    if selected_project and selected_project in projects_data:
        sites = projects_data[selected_project]
    else:
        sites = []
    
    selected_site = st.selectbox(
        "Site",
        options=[""] + sites,
        key="run_site",
        index=0
    )

with col3:
    schedule_id = st.text_input(
        "Schedule ID",
        placeholder="e.g. 20260215",
        key="run_schedule",
        value=""
    )

with col4:
    run_button = st.button("Run", key="btn_run", use_container_width=True)

with col5:
    refresh_button = st.button("Refresh", key="btn_refresh", use_container_width=True)

# Handle run button click
if run_button:
    if not selected_project or not selected_site or not schedule_id:
        st.error("Please fill in all fields: Project, Site, and Schedule ID")
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
            st.success(f"Crawl started: **{selected_site}** ({selected_project}, {schedule_id}) - Click Refresh to see progress")
            st.balloons()
        except Exception as e:
            st.error(f"Failed to start crawl: {str(e)}")

# Handle refresh button click
if refresh_button:
    st.rerun()

# ============================================================================
# SECTION 2: Current Run (if running)
# ============================================================================
if current_run:
    st.markdown("---")
    st.markdown('<div class="section-header">Current Run</div>', unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Project", current_run.get("project", "—"))
    with col2:
        st.metric("Site", current_run.get("site", "—"))
    with col3:
        st.metric("Schedule ID", current_run.get("schedule_id", "—"))
    with col4:
        stage = current_run.get("stage", "discovery").replace("_", " ").title()
        st.metric("Current Stage", stage)
    
    # Progress visualization for current run
    progress = current_run.get("progress", {})
    summary = progress_summary(progress)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"""
        <div class='stage-box'>
            <h4>Discovery</h4>
            <div class='count'>{summary['discovery']}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class='stage-box'>
            <h4>Retriever</h4>
            <div class='count'>{summary['retriever']}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class='stage-box'>
            <h4>Parser</h4>
            <div class='count'>{summary['parser']}</div>
        </div>
        """, unsafe_allow_html=True)

# ============================================================================
# SECTION 3: Filters and Download
# ============================================================================
if last_runs or current_run:
    st.markdown("---")
    st.markdown('<div class="section-header">History & Download</div>', unsafe_allow_html=True)
    
    # Collect all runs
    all_runs = []
    if current_run:
        all_runs.append(current_run)
    all_runs.extend(last_runs)
    
    # Extract all available projects
    all_projects_list = sorted(set(r.get("project") for r in all_runs if r.get("project")))
    
    # Filter Project Selection
    col1, col_space = st.columns([3, 2], gap="small")
    
    with col1:
        filter_project = st.selectbox(
            "Filter Project",
            options=["All"] + all_projects_list,
            key="filter_project"
        )
    
    # Show Filter Site only if a specific project is selected
    if filter_project != "All":
        col2, col_space2 = st.columns([3, 2], gap="small")
        
        with col2:
            available_sites = sorted(set(
                r.get("site") for r in all_runs 
                if r.get("site") and r.get("project") == filter_project
            ))
            
            filter_site = st.selectbox(
                "Filter Site",
                options=["All"] + available_sites,
                key="filter_site"
            )
        
        # Show Filter Schedule only if a specific site is selected
        if filter_site != "All":
            col3, col_space3 = st.columns([3, 2], gap="small")
            
            with col3:
                available_schedules = sorted(
                    set(r.get("schedule_id") for r in all_runs 
                        if r.get("schedule_id") and r.get("project") == filter_project and r.get("site") == filter_site),
                    reverse=True
                )
                
                filter_schedule = st.selectbox(
                    "Filter Schedule",
                    options=["Latest 3"] + available_schedules,
                    key="filter_schedule"
                )
            
            # Show Download checkbox
            col_download, col_space4 = st.columns([3, 2], gap="small")
            with col_download:
                show_download = st.checkbox("Show Download", value=False, key="toggle_download")
        else:
            filter_schedule = "Latest 3"
            show_download = False
    else:
        filter_site = "All"
        filter_schedule = "Latest 3"
        show_download = False
    
    # Apply all filters
    filtered_runs = all_runs
    
    # Filter by project
    if filter_project != "All":
        filtered_runs = [r for r in filtered_runs if r.get("project") == filter_project]
    
    # Filter by site
    if filter_site != "All":
        filtered_runs = [r for r in filtered_runs if r.get("site") == filter_site]
    
    # Filter by schedule
    if filter_schedule != "Latest 3":
        filtered_runs = [r for r in filtered_runs if r.get("schedule_id") == filter_schedule]
    else:
        filtered_runs = filtered_runs[:3]
    
    # Download section
    if show_download and filtered_runs:
        st.markdown("---")
        st.markdown('<div class="section-header">Download Results</div>', unsafe_allow_html=True)
        
        down_col1, down_col2 = st.columns(2)
        
        with down_col1:
            selected_download = st.selectbox(
                "Select run to download",
                options=range(len(filtered_runs)),
                format_func=lambda i: f"{filtered_runs[i].get('schedule_id')} - {filtered_runs[i].get('site')} ({filtered_runs[i].get('project')})",
                key="selected_download"
            )
            
            selected_run = filtered_runs[selected_download]
            project = selected_run.get("project", "")
            site = selected_run.get("site", "")
            schedule = selected_run.get("schedule_id", "")
            
            csv_path = (
                ROOT / "scrape_output" / "parser_output" / project / 
                f"{site}_{project}_{schedule}" / f"{site}_{project}.csv"
            )
            
            csv_exists = csv_path.exists()
        
        with down_col2:
            if csv_exists:
                with open(csv_path, "rb") as f:
                    csv_data = f.read()
                    st.download_button(
                        label="Download CSV",
                        data=csv_data,
                        file_name=f"{site}_{project}_{schedule}.csv",
                        mime="text/csv",
                        key="download_csv",
                        use_container_width=True
                    )
                st.success(f"CSV ready: {csv_path.name}")
            else:
                st.error(f"CSV not found: {csv_path.relative_to(ROOT)}")
    
    # Display runs table
    st.markdown("---")
    st.markdown(f'<div class="section-header">Crawl History ({len(filtered_runs)} shown)</div>', unsafe_allow_html=True)
    
    if filtered_runs:
        # Create table data
        table_data = []
        for run in filtered_runs:
            summary = progress_summary(run.get("progress", {}))
            is_current = current_run and (
                run.get("schedule_id") == current_run.get("schedule_id") and
                run.get("project") == current_run.get("project") and
                run.get("site") == current_run.get("site")
            )
            
            if is_current:
                status = "Running"
            elif run.get("success") is False:
                status = "Failed"
            else:
                status = "Success"
            
            completed = format_time(run.get("completed_at")) if run.get("completed_at") else "—"
            
            table_data.append({
                "Schedule ID": run.get("schedule_id", "—"),
                "Project": run.get("project", "—"),
                "Site": run.get("site", "—"),
                "Discovery": summary["discovery"],
                "Retriever": summary["retriever"],
                "Parser": summary["parser"],
                "Status": status,
                "Completed": completed
            })
        
        # Display as table
        st.dataframe(table_data, use_container_width=True, hide_index=True)
    else:
        st.info("No crawl data matches your filters. Try adjusting the filters or running a crawl.")
else:
    st.markdown("---")
    st.info("""
    ### No Crawl Data Yet
    
    **Get started:**
    1. Use the **Run Crawl** section above to start a crawl
    2. Or run from terminal: `python crawl_runner.py <project> <site> <schedule_id>`
    3. Click **Refresh** to update the dashboard
    
    **Example:** `python crawl_runner.py media_crawl vogue_in 20260217`
    """)