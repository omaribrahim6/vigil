"""Tavily Search integration with Canadian-source bias.

Docs: https://docs.tavily.com — POST /search with `api_key` in body, supports
`include_domains`, `search_depth`, `max_results`, `include_raw_content`."""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import httpx

from ..config import SETTINGS
from ..models import NewsArticle

logger = logging.getLogger(__name__)
URL = "https://api.tavily.com/search"

CANADIAN_DOMAINS = [
    "cbc.ca",
    "theglobeandmail.com",
    "ottawacitizen.com",
    "nationalpost.com",
    "thestar.ca",
    "ctvnews.ca",
    "globalnews.ca",
    "ipolitics.ca",
    "thehilltimes.ca",
    "lapresse.ca",
    "ledevoir.com",
    "winnipegfreepress.com",
    "edmontonjournal.com",
    "calgaryherald.com",
    "macleans.ca",
]

ADVERSE_TERMS = (
    "fraud OR investigation OR sanctions OR charges OR lawsuit OR misconduct "
    "OR \"regulatory action\" OR criminal OR bribery OR corruption "
    "OR \"auditor general\" OR \"CRA revoked\""
)

# Positive-integrity / remediation queries — what has the org done to fix
# past issues? Picks up settlements completed, leadership turnover,
# monitorship completed, integrity awards, ethics certifications, rebrands.
REMEDIATION_TERMS = (
    "remediation OR settled OR \"deferred prosecution\" OR \"integrity award\" "
    "OR \"ethics certification\" OR \"compliance program\" OR \"new CEO\" "
    "OR \"leadership change\" OR \"monitor concluded\" OR \"reform\" "
    "OR \"new code of conduct\" OR rebrand OR \"culture change\""
)


def _parse_date(raw: Any) -> date | None:
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    s = str(raw)
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _domain_to_source_name(url: str) -> str:
    try:
        host = url.split("/")[2].lower()
    except IndexError:
        return url
    if host.startswith("www."):
        host = host[4:]
    return host


async def _run_query(
    *,
    name: str,
    terms: str,
    max_results: int,
    canadian_only: bool,
    timeout: float,
    is_remediation: bool = False,
) -> list[NewsArticle]:
    if not SETTINGS.has_tavily:
        return []
    body: dict[str, Any] = {
        "api_key": SETTINGS.tavily_api_key,
        "query": f'"{name}" {terms}',
        "search_depth": "advanced",
        "max_results": max_results,
        "include_answer": False,
        # raw_content gives Claude enough text to extract event_date / dates
        # mentioned inside the article (Tavily 'published_date' is often null).
        "include_raw_content": True,
    }
    if canadian_only:
        body["include_domains"] = CANADIAN_DOMAINS
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(URL, json=body)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Tavily request failed for %r: %s", name, e)
        return []

    out: list[NewsArticle] = []
    for r in data.get("results", []) or []:
        url = r.get("url")
        if not url:
            continue
        snippet = (r.get("content") or r.get("snippet") or "").strip()
        raw = (r.get("raw_content") or "").strip()
        if raw and raw != snippet:
            raw = raw[:1200]
            summary = (snippet + "\n\n" + raw)[:1500]
        else:
            summary = snippet[:1500]
        out.append(
            NewsArticle(
                title=r.get("title") or url,
                url=url,
                source_name=_domain_to_source_name(url),
                published_at=_parse_date(r.get("published_date") or r.get("publishedDate")),
                summary=summary or None,
                confidence=float(r.get("score") or 0) or None,
                is_remediation=is_remediation,
            )
        )
    return out


async def search_adverse(
    name: str,
    *,
    max_results: int = 8,
    canadian_only: bool = False,
    timeout: float = 20.0,
) -> list[NewsArticle]:
    """Returns up to `max_results` adverse-keyword news hits. Empty list on
    missing key, network error, or no hits — never raises."""
    return await _run_query(
        name=name,
        terms=ADVERSE_TERMS,
        max_results=max_results,
        canadian_only=canadian_only,
        timeout=timeout,
    )


async def search_remediation(
    name: str,
    *,
    max_results: int = 5,
    canadian_only: bool = False,
    timeout: float = 20.0,
) -> list[NewsArticle]:
    """Returns positive-integrity / remediation signals so the funder sees
    *both sides* — not just historic bad news. Articles come back pre-tagged
    `is_remediation=True`; the classifier still labels severity (typically
    NOISE, but Claude may downgrade an explicitly remediated event)."""
    return await _run_query(
        name=name,
        terms=REMEDIATION_TERMS,
        max_results=max_results,
        canadian_only=canadian_only,
        timeout=timeout,
        is_remediation=True,
    )
