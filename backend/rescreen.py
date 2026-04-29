"""One-shot re-screen helper for the demo orgs (re-run after pipeline edits)."""
from __future__ import annotations

import asyncio
import sys

from app.pipeline import screen_by_name

NAMES = [
    "AtkinsRealis",
    "GC Strategies",
    "Dalian Enterprises",
    "Coradix Technology Consulting",
    "McKinsey & Company Canada",
]


async def main() -> None:
    for n in NAMES:
        print(f">>> {n}", flush=True)
        d = await screen_by_name(n)
        rem = d.remediation
        immediate = sum(1 for a in d.actions if a.urgency == "immediate")
        print(
            f"    score={d.risk.score}/{d.risk.tier} "
            f"actions={len(d.actions)} immediate={immediate}",
            flush=True,
        )
        print(
            f"    remediation: {rem.signal_count} total / "
            f"{rem.recent_signal_count} recent / "
            f"dampening={rem.dampening_factor:.2f}",
            flush=True,
        )


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0)
