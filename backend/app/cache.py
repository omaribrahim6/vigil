"""Disk JSON cache. The demo runs entirely off cache if Wi-Fi dies on stage."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .config import CACHE_DIR, SCREENINGS_DIR


def _json_default(o: Any) -> Any:
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    if hasattr(o, "model_dump"):
        return o.model_dump(mode="json", by_alias=True)
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=_json_default),
        encoding="utf-8",
    )


def read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def screening_path(org_id: str) -> Path:
    return SCREENINGS_DIR / f"{org_id}.json"


def write_screening(org_id: str, dossier_dict: dict) -> None:
    write_json(screening_path(org_id), dossier_dict)


def read_screening(org_id: str) -> dict | None:
    return read_json(screening_path(org_id))


def write_top_orgs(rows: list[dict]) -> None:
    write_json(CACHE_DIR / "orgs_top.json", rows)


def read_top_orgs() -> list[dict] | None:
    data = read_json(CACHE_DIR / "orgs_top.json")
    return data if isinstance(data, list) else None


def write_portfolio_stats(stats: dict) -> None:
    write_json(CACHE_DIR / "portfolio_stats.json", stats)


def read_portfolio_stats() -> dict | None:
    return read_json(CACHE_DIR / "portfolio_stats.json")
