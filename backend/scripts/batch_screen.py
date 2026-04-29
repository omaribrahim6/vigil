"""Batch-screen the top-N federal-funded organizations.

Usage:
    python -m scripts.batch_screen --top 50 --concurrency 4

Concurrency knob keeps Tavily/Bedrock from rate-limiting us. Skips orgs
that already have a cached dossier (so re-runs are cheap).

Run-time math: ~30-60s per org sequentially; with concurrency=4 we can
screen 50 orgs in ~10-15 minutes. The script writes progress to stdout
every org so you can tail the log.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import time

from app import bigquery_client, cache
from app.config import SETTINGS
from app.pipeline import screen_by_id
from scripts.precache import cache_portfolio_stats, cache_top_orgs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("batch_screen")


async def screen_one(org_id: str, name: str, *, sem: asyncio.Semaphore) -> None:
    async with sem:
        if cache.read_screening(org_id):
            log.info("[skip] %s (%s) already cached", org_id, name)
            return
        t0 = time.time()
        try:
            dossier = await screen_by_id(org_id)
            if dossier is None:
                log.warning("[miss] %s not found in goldens", org_id)
                return
            elapsed = time.time() - t0
            immediate = sum(
                1 for a in dossier.actions if a.urgency == "immediate"
            )
            log.info(
                "[ok]  %s (%s) score=%d/%s actions=%d immediate=%d (%.1fs)",
                org_id,
                dossier.org.canonical_name,
                dossier.risk.score,
                dossier.risk.tier,
                len(dossier.actions),
                immediate,
                elapsed,
            )
        except Exception as e:  # noqa: BLE001
            log.exception("[err] %s failed: %s", org_id, e)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()

    if not SETTINGS.has_tavily:
        log.warning("TAVILY_API_KEY not set — news panel will be empty.")
    if not SETTINGS.has_anthropic:
        log.warning("Bedrock/Anthropic not configured — using deterministic fallback.")

    log.info("Fetching top-%d orgs from BigQuery…", args.top)
    rows = bigquery_client.fetch_top_orgs(args.top)
    log.info("Got %d candidates. Concurrency=%d.", len(rows), args.concurrency)

    sem = asyncio.Semaphore(args.concurrency)
    tasks = [
        asyncio.create_task(screen_one(r.id, r.canonical_name, sem=sem))
        for r in rows
    ]
    t0 = time.time()
    await asyncio.gather(*tasks, return_exceptions=False)
    log.info("All screenings complete in %.1fs.", time.time() - t0)

    log.info("Refreshing dashboard caches…")
    await cache_top_orgs()
    await cache_portfolio_stats()
    log.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())
