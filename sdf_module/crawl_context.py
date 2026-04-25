from __future__ import annotations

import re
import sys
from dataclasses import dataclass

_SAFE = re.compile(r'^[a-zA-Z0-9_-]+$')


@dataclass(frozen=True)
class CrawlContext:
    """
    Immutable identity for a single crawl job.

    Encapsulates the (project, site, schedule_id) triple that previously
    floated as bare strings through every function signature, and exposes
    all derived identifiers and subprocess commands as properties.
    """
    project:     str
    site:        str
    schedule_id: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.project,     "project"),
            (self.site,        "site"),
            (self.schedule_id, "schedule_id"),
        ):
            if not value or not _SAFE.match(value):
                raise ValueError(
                    f"Invalid {label} '{value}': only letters, digits, "
                    "underscores, and hyphens are allowed."
                )

    # ── Derived identifiers ───────────────────────────────────────────────────

    @property
    def run_key(self) -> str:
        """Unique key used in crawl_status and Redis."""
        return f"{self.project}__{self.site}__{self.schedule_id}"

    @property
    def queue_name(self) -> str:
        """RabbitMQ queue name for this crawl job."""
        return f"{self.site}_{self.project}_{self.schedule_id}_queue"

    # ── Subprocess commands for each pipeline stage ───────────────────────────

    @property
    def discovery_cmd(self) -> list[str]:
        return [sys.executable, "-m", "sdf_module.url_discovery",
                self.project, self.site, self.schedule_id]

    @property
    def retriever_cmd(self) -> list[str]:
        return [sys.executable, "-m", "sdf_module.url_retriever",
                self.project, self.site, self.schedule_id]

    @property
    def parser_cmd(self) -> list[str]:
        return [sys.executable, "-m", "sdf_module.url_parser",
                self.project, self.site, self.schedule_id]

    def __str__(self) -> str:
        return f"{self.project}/{self.site}@{self.schedule_id}"
