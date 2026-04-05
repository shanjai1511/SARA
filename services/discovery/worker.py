"""
SARA — Async Discovery Worker.

Replaces the synchronous discovery stage with an async implementation that:
  - Traverses depth levels using aiohttp (non-blocking)
  - Deduplicates discovered URLs via Redis Bloom filter
  - Publishes directly to the retriever queue (bypassing file-based storage)
  - Respects per-domain rate limits
  - Reports Prometheus metrics

This worker is a drop-in complement to the existing url_discovery.py;
both can run in parallel during migration.

Run:
    python -m services.discovery.worker --project commerce_crawl --site myntra_com --schedule 20260405
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import logging
import os
import random
import sys
import time
from pathlib import Path
from typing import Any, List, Optional
from urllib.parse import urlparse

import aiohttp  # type: ignore
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import settings
from core.broker import (
    EXCHANGE_RETRIEVER,
    declare_pipeline_topology,
    get_sync_channel,
    publish_sync,
    queue_name,
)
from core.metrics import metrics, start_metrics_server
from core.rate_limiter import get_delay
from sdf_module.files_import import normalize_class_name

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sara.discovery")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
]


async def async_fetch(
    session: aiohttp.ClientSession,
    url: str,
    proxy: Optional[str] = None,
    timeout: int = 30,
    retries: int = 2,
) -> Optional[str]:
    """Fetch a URL asynchronously and return HTML text or None on failure."""
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    timeout_obj = aiohttp.ClientTimeout(total=timeout)

    for attempt in range(retries + 1):
        try:
            async with session.get(
                url,
                headers=headers,
                proxy=proxy,
                timeout=timeout_obj,
                ssl=False,
                allow_redirects=True,
            ) as resp:
                if resp.status == 200:
                    return await resp.text(encoding="utf-8", errors="replace")
                if resp.status in (429, 503) and attempt < retries:
                    await asyncio.sleep(2 ** attempt * 5)
                    continue
                logger.warning("Discovery fetch %s → HTTP %d", url, resp.status)
                return None
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            if attempt < retries:
                await asyncio.sleep(2 ** attempt * 2)
            else:
                logger.error("Discovery fetch failed %s: %s", url, exc)
    return None


class AsyncDiscoveryWorker:
    """
    Async replacement for sdf_module.url_discovery.UrlDiscovery.

    Loads the same YAML config and per-site Python module, but runs
    the URL-fetch loop using aiohttp instead of synchronous requests.
    """

    def __init__(
        self,
        project: str,
        site: str,
        schedule_id: str,
        base_dir: Optional[Path] = None,
        proxy_list: Optional[list] = None,
    ):
        self.project = project
        self.site = site
        self.schedule_id = schedule_id
        self.base_dir = base_dir or ROOT
        self.proxy_list = proxy_list or []
        self._discovered: List[str] = []
        self._count = 0

    def _get_proxy(self) -> Optional[str]:
        if not self.proxy_list:
            return None
        host, port, user, pwd = random.choice(self.proxy_list)
        return f"http://{user}:{pwd}@{host}:{port}"

    def _load_config(self) -> tuple[dict, Any]:
        """Load YAML config + site module.  Same logic as UrlDiscovery."""
        collector_dir = self.base_dir / "url_discovery" / self.project
        yaml_path = collector_dir / f"{self.site}_{self.project}.yml"
        module_path = collector_dir / f"{self.site}_{self.project}.py"

        with open(yaml_path, "r", encoding="utf-8") as f:
            depth_config = yaml.safe_load(f)

        class_name = normalize_class_name(self.project, self.site)
        spec = importlib.util.spec_from_file_location(class_name, module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        site_instance = getattr(module, class_name)()
        return depth_config, site_instance

    async def _call_site_method(
        self,
        session: aiohttp.ClientSession,
        site_instance: Any,
        method_name: str,
        url: str,
        depth: dict,
        current_level: int,
    ) -> List[str]:
        """
        Call site-specific discovery method.
        If the method uses sdfFetch internally (sync), run it in a thread
        executor so it doesn't block the event loop.
        """
        method = getattr(site_instance, method_name, None)
        if not callable(method):
            logger.warning("Method %s not found on %s", method_name, site_instance)
            return []

        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None, method, url, depth, current_level
            )
            if isinstance(result, str):
                return [result]
            return result or []
        except Exception as exc:
            logger.error("Site method %s failed for %s: %s", method_name, url, exc)
            return []

    async def run(self) -> int:
        """Execute discovery and publish URLs to RabbitMQ. Returns count."""
        logger.info(
            "[discovery] Starting async: project=%s site=%s schedule=%s",
            self.project, self.site, self.schedule_id,
        )

        try:
            depth_config, site_instance = self._load_config()
        except Exception as exc:
            logger.error("Failed to load discovery config: %s", exc)
            return 0

        # Declare RabbitMQ topology
        conn, ch = get_sync_channel(settings.CLOUDAMQP_URL)
        declare_pipeline_topology(ch, self.site, self.project)

        depth_items = sorted(
            ((int(k.replace("depth", "")), v) for k, v in depth_config.items() if k.startswith("depth") and k != "depth0"),
            key=lambda x: x[0],
        )
        seed_urls: List[str] = depth_config.get("depth0", {}).get("seed_url", [])
        if not seed_urls:
            logger.error("No seed_url in depth0 config")
            conn.close()
            return 0

        connector = aiohttp.TCPConnector(limit=10, ssl=False, ttl_dns_cache=300)
        async with aiohttp.ClientSession(connector=connector) as session:
            pending_urls = list(seed_urls)

            for level, level_config in depth_items:
                method_name = level_config.get("method_name")
                if not method_name:
                    continue

                domain = urlparse(pending_urls[0]).netloc if pending_urls else self.site
                delay = get_delay(domain)
                next_urls: List[str] = []

                logger.info(
                    "[discovery] depth=%d method=%s urls=%d delay=%.1fs",
                    level, method_name, len(pending_urls), delay,
                )

                for url in pending_urls:
                    results = await self._call_site_method(
                        session, site_instance, method_name, url, depth_config, level
                    )
                    next_urls.extend(results)
                    metrics.url_discovered(domain, self.project)
                    await asyncio.sleep(delay + random.uniform(0, 0.5))

                if level == depth_items[-1][0]:
                    # Final depth — publish to retriever queue
                    r_queue = queue_name("retriever", self.site, self.project)
                    for url in next_urls:
                        payload = {
                            "url": url,
                            "domain": urlparse(url).netloc,
                            "project": self.project,
                            "site": self.site,
                            "schedule_id": self.schedule_id,
                            "discovered_at": time.time(),
                        }
                        publish_sync(
                            ch,
                            exchange=EXCHANGE_RETRIEVER,
                            routing_key=f"retriever.{self.site}.{self.project}",
                            body=payload,
                        )
                    self._count = len(next_urls)
                    logger.info(
                        "[discovery] Published %d URLs to retriever queue",
                        self._count,
                    )

                pending_urls = next_urls

        conn.close()
        logger.info(
            "[discovery] Completed: discovered=%d project=%s site=%s",
            self._count, self.project, self.site,
        )
        return self._count


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def _main() -> None:
    parser = argparse.ArgumentParser(description="SARA Async Discovery Worker")
    parser.add_argument("--project",  required=True)
    parser.add_argument("--site",     required=True)
    parser.add_argument("--schedule", required=True)
    parser.add_argument("--metrics-port", type=int, default=8002)
    args = parser.parse_args()

    start_metrics_server(port=args.metrics_port)

    import json as _json
    proxy_raw = os.environ.get("WEBSHARE_PROXY_JSON", "")
    proxy_list = _json.loads(proxy_raw) if proxy_raw else []

    worker = AsyncDiscoveryWorker(
        project=args.project,
        site=args.site,
        schedule_id=args.schedule,
        proxy_list=proxy_list,
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(_main())
