"""CanLII case-search integration. Free API key (request via CanLII feedback
form). Without a key the panel renders 'court records not configured' rather
than failing.

Docs: https://github.com/canlii/API_documentation/blob/master/EN.md
Base: https://api.canlii.org/v1/
Auth: query param `?api_key=...`. (CanLII's docs use `key` in some examples,
`api_key` in others; we send both for compatibility.)"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import httpx

from ..config import SETTINGS
from ..models import CourtCase

logger = logging.getLogger(__name__)
BASE = "https://api.canlii.org/v1"
JURISDICTIONS = ["ca", "on", "qc", "ab", "bc"]

ADVERSE_KEYWORDS = (
    "fraud misappropriation breach trust regulatory criminal charges "
    "negligence investigation conspiracy"
)


def _parse_date(raw: Any) -> date | None:
    if not raw:
        return None
    s = str(raw)
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


async def search_decisions(
    name: str,
    *,
    max_results_per_jurisdiction: int = 5,
    timeout: float = 20.0,
) -> list[CourtCase]:
    """Returns court decisions mentioning `name` with adverse keywords. Empty list
    on missing key / network error / no hits — never raises."""
    if not SETTINGS.has_canlii:
        return []
    out: list[CourtCase] = []
    seen_ids: set[str] = set()
    async with httpx.AsyncClient(timeout=timeout) as client:
        for jur in JURISDICTIONS:
            params = {
                "fullText": f'"{name}" {ADVERSE_KEYWORDS}',
                "resultCount": str(max_results_per_jurisdiction),
                "api_key": SETTINGS.canlii_api_key,
                "key": SETTINGS.canlii_api_key,
            }
            url = f"{BASE}/caseBrowse/en/{jur}/"
            try:
                resp = await client.get(url, params=params)
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, ValueError) as e:
                logger.warning("CanLII %s search failed: %s", jur, e)
                continue
            cases = data.get("cases") or data.get("caseList") or []
            for c in cases[:max_results_per_jurisdiction]:
                cid = c.get("caseId", {}).get("en") if isinstance(c.get("caseId"), dict) else c.get("caseId")
                if not cid or cid in seen_ids:
                    continue
                seen_ids.add(cid)
                citation = c.get("citation") or c.get("title") or cid
                title = c.get("title") or citation
                decision_date = _parse_date(c.get("decisionDate") or c.get("date"))
                case_url = (
                    f"https://www.canlii.org/en/{jur}/decisions/{c.get('databaseId', '')}/{cid}.html"
                    if cid else None
                )
                out.append(
                    CourtCase(
                        citation=citation,
                        title=title,
                        case_id=cid,
                        decision_date=decision_date,
                        jurisdiction=jur.upper(),
                        url=case_url,
                        snippet=c.get("snippet"),
                    )
                )
    return out
