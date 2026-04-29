"""FastAPI entrypoint for Vigil.

Routes prefer the disk cache so the demo runs even without external network.
Live `/screen/*` routes hit BigQuery + the external sources and re-cache."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import bigquery_client, cache
from .config import SETTINGS
from .models import (
    PortfolioStats,
    ScreeningDossier,
    TopOrgRow,
)
from .pipeline import screen_by_id, screen_by_name
from .risk_scorer import top_flag_for, RiskBreakdown

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Vigil API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "sources": {
            "anthropic": SETTINGS.has_anthropic,
            "opensanctions": SETTINGS.has_opensanctions,
            "tavily": SETTINGS.has_tavily,
            "canlii": SETTINGS.has_canlii,
        },
    }


@app.get("/api/orgs/top")
def get_top_orgs(limit: int = Query(200, ge=1, le=500)) -> list[TopOrgRow]:
    """Returns the dashboard's top-funded orgs, enriched with cached risk data
    where available (precache populates this)."""
    cached_top = cache.read_top_orgs()
    if cached_top:
        rows = [TopOrgRow(**r) for r in cached_top]
        return rows[:limit]
    rows = bigquery_client.fetch_top_orgs(limit)
    for row in rows:
        screening = cache.read_screening(row.id)
        if not screening:
            continue
        risk = screening.get("risk") or {}
        row.risk_score = risk.get("score")
        row.risk_tier = risk.get("tier") or "UNRATED"
        breakdown = RiskBreakdown(**risk) if risk else None
        row.top_flag = top_flag_for(breakdown) if breakdown else None
    cache.write_top_orgs([r.model_dump(mode="json") for r in rows])
    return rows


@app.get("/api/orgs/search")
def get_search(q: str = Query(..., min_length=2), limit: int = 25) -> list[TopOrgRow]:
    rows = bigquery_client.search_orgs(q, limit)
    for row in rows:
        screening = cache.read_screening(row.id)
        if not screening:
            continue
        risk = screening.get("risk") or {}
        row.risk_score = risk.get("score")
        row.risk_tier = risk.get("tier") or "UNRATED"
    return rows


@app.get("/api/orgs/{org_id}")
def get_org(org_id: str) -> ScreeningDossier:
    cached = cache.read_screening(org_id)
    if cached:
        return ScreeningDossier(**cached)
    raise HTTPException(status_code=404, detail="org not yet screened; POST /api/orgs/{id}/screen first")


@app.post("/api/orgs/{org_id}/screen")
async def post_screen(org_id: str) -> ScreeningDossier:
    dossier = await screen_by_id(org_id)
    if dossier is None:
        raise HTTPException(status_code=404, detail=f"org id {org_id} not found in goldens")
    return dossier


@app.post("/api/screen/by-name")
async def post_screen_by_name(payload: dict[str, str]) -> ScreeningDossier:
    name = (payload or {}).get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    return await screen_by_name(name)


@app.get("/api/portfolio/stats")
def get_portfolio_stats() -> PortfolioStats:
    cached = cache.read_portfolio_stats()
    if cached:
        return PortfolioStats(**cached)
    raise HTTPException(
        status_code=404,
        detail="portfolio stats not yet computed; run scripts/portfolio_stats.py",
    )
