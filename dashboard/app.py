"""
SARA dashboard: real-time crawl progress + start crawls from the UI.
Run from project root: python dashboard/app.py
Then open http://127.0.0.1:5000
"""
import sys
import subprocess
from pathlib import Path

# Ensure project root is on path so sdf_module resolves
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask import Flask, send_from_directory, jsonify, request, send_file, redirect

app = Flask(__name__, static_folder="static", static_url_path="")


@app.route("/api/download/", methods=["GET"])
def api_download_slash():
    """Redirect to /api/download so trailing slash doesn't 404."""
    return redirect("/api/download" + ("?" + request.query_string.decode() if request.query_string else ""), code=302)


def list_projects_sites():
    """Scan url_discovery/ for project/site configs (no Python needed for listing)."""
    discovery = ROOT / "url_discovery"
    result = {}
    if not discovery.exists():
        return result
    for project_dir in discovery.iterdir():
        if project_dir.is_dir() and not project_dir.name.startswith("."):
            sites = []
            for f in project_dir.glob("*.yml"):
                # site name is before _project in filename, e.g. vogue_in_media_crawl.yml -> vogue_in
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


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/status")
def api_status():
    try:
        from sdf_module.crawl_status import get_status
        return jsonify(get_status())
    except Exception as e:
        return jsonify({"current_run": None, "last_runs": [], "_error": str(e)}), 200


@app.route("/api/projects")
def api_projects():
    return jsonify(list_projects_sites())


@app.route("/api/run", methods=["POST"])
def api_run():
    try:
        body = request.get_json() or {}
        project = (body.get("project") or "").strip()
        site = (body.get("site") or "").strip()
        schedule_id = (body.get("schedule_id") or "").strip()
        if not project or not site or not schedule_id:
            return jsonify({"ok": False, "error": "project, site, and schedule_id are required"}), 400
        cmd = [sys.executable, str(ROOT / "crawl_runner.py"), project, site, schedule_id]
        subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return jsonify({"ok": True, "message": "Crawl started. Click Refresh to see progress."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/download", methods=["GET"])
def api_download():
    """Serve CSV for the given project, site, schedule_id."""
    project = (request.args.get("project") or "").strip()
    site = (request.args.get("site") or "").strip()
    schedule_id = (request.args.get("schedule_id") or "").strip()
    if not project or not site or not schedule_id:
        return jsonify({"ok": False, "error": "project, site, and schedule_id are required"}), 400
    dir_name = f"{site}_{project}_{schedule_id}"
    csv_name = f"{site}_{project}.csv"
    csv_path = (ROOT / "scrape_output" / "parser_output" / project / dir_name / csv_name).resolve()
    if not csv_path.is_file():
        return jsonify({"ok": False, "error": "CSV not found for this run. Run the parser first."}), 404
    return send_file(
        str(csv_path),
        as_attachment=True,
        download_name=csv_name,
        mimetype="text/csv",
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
