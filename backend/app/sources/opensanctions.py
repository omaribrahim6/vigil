"""OpenSanctions /match/default integration.

Docs: https://www.opensanctions.org/docs/api/matching/
Auth: `Authorization: ApiKey <KEY>`. Algorithm pinned to `logic-v2` per March 2026
changelog. We pass the canonical name + Canada jurisdiction; results capped at 5
per query (the API default)."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config import SETTINGS
from ..models import SanctionsHit

logger = logging.getLogger(__name__)
URL = "https://api.opensanctions.org/match/default"
THRESHOLD = 0.65


async def match_company(name: str, *, country: str = "ca", timeout: float = 15.0) -> list[SanctionsHit]:
    """Returns sanctions/PEP/debarment matches above THRESHOLD. Empty list on
    missing key, network error, or no hits — never raises."""
    if not SETTINGS.has_opensanctions:
        return []
    headers = {
        "Authorization": f"ApiKey {SETTINGS.opensanctions_api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "queries": {
            "q": {
                "schema": "Company",
                "properties": {
                    "name": [name],
                    "jurisdiction": [country],
                },
            }
        }
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                URL,
                params={"algorithm": "logic-v2"},
                headers=headers,
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("OpenSanctions request failed for %r: %s", name, e)
        return []

    results = (
        data.get("responses", {})
        .get("q", {})
        .get("results", [])
    )
    hits: list[SanctionsHit] = []
    for r in results:
        score = float(r.get("score") or 0)
        if score < THRESHOLD:
            continue
        props: dict[str, Any] = r.get("properties", {}) or {}
        countries: list[str] = []
        for k in ("country", "jurisdiction", "addressCountry"):
            for v in props.get(k, []) or []:
                if isinstance(v, str) and v not in countries:
                    countries.append(v)
        topics = []
        for v in props.get("topics", []) or []:
            if isinstance(v, str):
                topics.append(v)
        list_name = ", ".join(topics) if topics else (r.get("dataset") or "OpenSanctions")
        entity_url = None
        ent_id = r.get("id")
        if ent_id:
            entity_url = f"https://www.opensanctions.org/entities/{ent_id}/"
        hits.append(
            SanctionsHit(
                list_name=list_name,
                countries=countries,
                score=round(score, 3),
                schema=r.get("schema") or "Company",
                entity_url=entity_url,
                raw=r,
            )
        )
    return hits
