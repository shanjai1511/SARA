"""
SARA API — Site management endpoints.

GET  /sites                   — List all configured sites
GET  /sites/{project}         — List sites in a project
POST /sites                   — Create a new site configuration
DELETE /sites/{project}/{site} — Remove a site configuration
GET  /sites/{project}/{site}/validate — Check if site config is complete
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException

ROOT = Path(__file__).resolve().parent.parent.parent.parent

from services.api.schemas import CreateSiteRequest, SiteInfo, SiteListResponse

logger = logging.getLogger("sara.api.sites")
router = APIRouter(prefix="/sites", tags=["Sites"])


def _scan_sites(base_dir: Path) -> list[SiteInfo]:
    """Scan url_discovery/ for all configured sites."""
    discovery_root = base_dir / "url_discovery"
    parser_root    = base_dir / "url_data_parser"
    sites = []

    if not discovery_root.exists():
        return sites

    for project_dir in sorted(discovery_root.iterdir()):
        if not project_dir.is_dir() or project_dir.name.startswith("."):
            continue
        project = project_dir.name
        for yml in sorted(project_dir.glob("*.yml")):
            base = yml.stem
            suffix = f"_{project}"
            if base.endswith(suffix):
                site = base[: -len(suffix)]
                if not site:
                    continue
                has_parser_py = (
                    parser_root / project / f"{site}_{project}.py"
                ).exists()
                has_parser_yml = (
                    parser_root / project / f"{site}_{project}.yml"
                ).exists()
                has_disc_py = (project_dir / f"{site}_{project}.py").exists()

                sites.append(SiteInfo(
                    site=site,
                    project=project,
                    has_discovery=has_disc_py and yml.exists(),
                    has_retriever=True,   # retriever config is inline in YAML
                    has_parser=has_parser_py and has_parser_yml,
                ))

    return sites


@router.get("", response_model=SiteListResponse, summary="List all sites")
async def list_sites(project: Optional[str] = None):
    sites = _scan_sites(ROOT)
    if project:
        sites = [s for s in sites if s.project == project]
    return SiteListResponse(sites=sites, total=len(sites))


@router.get("/{project}", response_model=SiteListResponse, summary="List sites in project")
async def list_project_sites(project: str):
    sites = [s for s in _scan_sites(ROOT) if s.project == project]
    return SiteListResponse(sites=sites, total=len(sites))


@router.post("", summary="Create a new site configuration")
async def create_site(req: CreateSiteRequest):
    """
    Write discovery, retriever, and parser files for a new site.
    Equivalent to the 'Create Project' form in the Streamlit dashboard.
    """
    for module_type, subdir in [
        ("url_discovery", "url_discovery"),
        ("url_data_parser", "url_data_parser"),
    ]:
        project_dir = ROOT / subdir / req.project
        project_dir.mkdir(parents=True, exist_ok=True)

    disc_py  = ROOT / "url_discovery"    / req.project / f"{req.site}_{req.project}.py"
    disc_yml = ROOT / "url_discovery"    / req.project / f"{req.site}_{req.project}.yml"
    pars_py  = ROOT / "url_data_parser"  / req.project / f"{req.site}_{req.project}.py"
    pars_yml = ROOT / "url_data_parser"  / req.project / f"{req.site}_{req.project}.yml"

    # Don't overwrite existing files
    for f in (disc_py, disc_yml, pars_py, pars_yml):
        if f.exists():
            raise HTTPException(
                status_code=409,
                detail=f"File already exists: {f.relative_to(ROOT)}",
            )

    disc_py.write_text(req.discovery_py, encoding="utf-8")
    disc_yml.write_text(req.discovery_yml, encoding="utf-8")
    pars_py.write_text(req.parser_py, encoding="utf-8")
    pars_yml.write_text(req.parser_yml, encoding="utf-8")

    logger.info("Created site: project=%s site=%s", req.project, req.site)
    return {
        "message": "Site created",
        "project": req.project,
        "site": req.site,
        "files": [
            str(disc_py.relative_to(ROOT)),
            str(disc_yml.relative_to(ROOT)),
            str(pars_py.relative_to(ROOT)),
            str(pars_yml.relative_to(ROOT)),
        ],
    }


@router.delete("/{project}/{site}", summary="Delete a site configuration")
async def delete_site(project: str, site: str):
    """Remove all configuration files for a site."""
    removed = []
    for subdir in ("url_discovery", "url_data_parser", "url_retriever"):
        for ext in (".py", ".yml"):
            f = ROOT / subdir / project / f"{site}_{project}{ext}"
            if f.exists():
                f.unlink()
                removed.append(str(f.relative_to(ROOT)))

    if not removed:
        raise HTTPException(status_code=404, detail=f"Site {site}/{project} not found")

    return {"removed": removed}


@router.get("/{project}/{site}/validate", summary="Validate site config completeness")
async def validate_site(project: str, site: str):
    """Check that all required files exist and are non-empty."""
    checks = {}
    required_files = [
        ("url_discovery",   f"{site}_{project}.py"),
        ("url_discovery",   f"{site}_{project}.yml"),
        ("url_data_parser", f"{site}_{project}.py"),
        ("url_data_parser", f"{site}_{project}.yml"),
    ]
    for subdir, filename in required_files:
        path = ROOT / subdir / project / filename
        checks[f"{subdir}/{filename}"] = {
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
        }

    all_ok = all(v["exists"] and v["size_bytes"] > 0 for v in checks.values())
    return {
        "project": project,
        "site": site,
        "valid": all_ok,
        "files": checks,
    }
