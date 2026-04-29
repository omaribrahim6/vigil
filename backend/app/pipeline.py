"""Pipeline orchestrator.

Given an `OrgProfile`, runs the three external sources (OpenSanctions, Tavily,
CanLII) in parallel via asyncio + the BigQuery-based GDELT and forensic signals
serially (BQ client is sync). Builds the timeline, classifies news, computes the
risk score, asks Claude for a briefing memo, and persists the dossier to disk."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Iterable

from .bigquery_client import (
    fetch_funding_events,
    fetch_funding_events_by_name,
    fetch_org_by_id,
)
from .cache import write_screening
from .classifier import author_actions, author_briefing_memo, classify_articles
from .config import DATA_PROJECT, SETTINGS
from .forensics import fetch_forensics
from .models import (
    AdverseEvent,
    CourtCase,
    FundingEvent,
    NewsArticle,
    OrgProfile,
    ProvenanceTrail,
    RelatedEntity,
    SanctionsHit,
    ScreeningDossier,
)
from .risk_scorer import compute_risk
from .sources import canlii, gdelt, opensanctions, tavily

logger = logging.getLogger(__name__)


def _earliest(*dates: Iterable) -> "datetime | None":
    flat = []
    for d in dates:
        if d is None:
            continue
        if isinstance(d, list):
            flat.extend(d)
        else:
            flat.append(d)
    flat = [d for d in flat if d is not None]
    return min(flat) if flat else None


def _build_provenance(
    profile: OrgProfile,
    sanctions: list[SanctionsHit],
    court: list[CourtCase],
    news: list[NewsArticle],
    forensics,  # ForensicSignals; avoid extra import
) -> ProvenanceTrail:
    """Materialize the full citation trail. Each row is a clickable BQ dataset
    table (or a primary-source URL) — the mentor's 'every fact must trace back
    to a database row or source' requirement."""
    bq_rows: list[str] = [
        f"{DATA_PROJECT}.general.entity_golden_records id={profile.id}",
    ]
    if profile.bn_root:
        bq_rows.append(f"{DATA_PROJECT}.fed.grants_contributions WHERE STARTS_WITH(recipient_business_number, '{profile.bn_root}')")
        bq_rows.append(f"{DATA_PROJECT}.cra.cra_identification WHERE STARTS_WITH(bn, '{profile.bn_root}')")
    if forensics.cra_loop_score is not None:
        bq_rows.append(f"{DATA_PROJECT}.cra.loop_universe WHERE STARTS_WITH(bn, '{profile.bn_root}')")
    if forensics.cra_t3010_violation_count and forensics.cra_t3010_violation_count > 0:
        bq_rows.append(f"{DATA_PROJECT}.cra.t3010_impossibilities WHERE STARTS_WITH(bn, '{profile.bn_root}')")
    if forensics.cra_max_overhead_ratio is not None:
        bq_rows.append(f"{DATA_PROJECT}.cra.overhead_by_charity WHERE STARTS_WITH(bn, '{profile.bn_root}')")
    if forensics.ab_sole_source_count and forensics.ab_sole_source_count > 0:
        bq_rows.append(f"{DATA_PROJECT}.ab.ab_sole_source WHERE LOWER(vendor) LIKE '%{profile.canonical_name.lower()}%'")
    if forensics.shared_directors:
        bq_rows.append(f"{DATA_PROJECT}.cra.cra_directors (shared-director join)")

    external: list[dict[str, str]] = []
    for s in sanctions:
        if s.entity_url:
            external.append({"label": f"OpenSanctions: {s.list_name}", "url": s.entity_url})
    for c in court:
        if c.url:
            external.append({"label": f"CanLII: {c.citation}", "url": c.url})
    for a in news:
        if a.severity in ("CRITICAL", "HIGH") and a.url:
            external.append({
                "label": f"{a.source_name or 'news'}: {a.title[:80]}",
                "url": a.url,
            })
    return ProvenanceTrail(bigquery_rows=bq_rows, external_urls=external[:25])


def _adverse_events_from_sources(
    sanctions: list[SanctionsHit],
    court_cases: list[CourtCase],
    news: list[NewsArticle],
) -> list[AdverseEvent]:
    out: list[AdverseEvent] = []
    for s in sanctions:
        out.append(
            AdverseEvent(
                source="opensanctions",
                date=None,
                title=f"Sanctions hit: {s.list_name}",
                severity="CRITICAL",
                category="sanctions",
                summary=f"Score {s.score:.2f}; jurisdictions: {', '.join(s.countries) or 'n/a'}",
                url=s.entity_url,
                confidence=s.score,
            )
        )
    for c in court_cases:
        out.append(
            AdverseEvent(
                source="canlii",
                date=c.decision_date,
                title=c.title,
                severity="HIGH",
                category="court",
                summary=c.snippet or c.citation,
                url=c.url,
            )
        )
    for a in news:
        if a.severity not in ("CRITICAL", "HIGH", "MEDIUM"):
            continue
        out.append(
            AdverseEvent(
                source="tavily",
                date=a.published_at,
                title=a.title,
                severity=a.severity,
                category=a.category or "news",
                summary=a.summary,
                url=a.url,
                confidence=a.confidence,
            )
        )
    return out


async def _run_external_sources(name: str) -> tuple[
    list[SanctionsHit], list[NewsArticle], list[CourtCase]
]:
    coros = []
    coros.append(opensanctions.match_company(name))
    coros.append(tavily.search_adverse(name))
    coros.append(canlii.search_decisions(name))
    sanctions, news, court = await asyncio.gather(*coros, return_exceptions=False)
    return (
        sanctions if isinstance(sanctions, list) else [],
        news if isinstance(news, list) else [],
        court if isinstance(court, list) else [],
    )


async def screen_profile(
    profile: OrgProfile,
    related: list[RelatedEntity] | None = None,
    *,
    funding_events: list[FundingEvent] | None = None,
) -> ScreeningDossier:
    sources_run: list[str] = []
    sources_skipped: list[str] = []

    sanctions, news, court = await _run_external_sources(profile.canonical_name)
    if SETTINGS.has_opensanctions:
        sources_run.append("opensanctions")
    else:
        sources_skipped.append("opensanctions")
    if SETTINGS.has_tavily:
        sources_run.append("tavily")
    else:
        sources_skipped.append("tavily")
    if SETTINGS.has_canlii:
        sources_run.append("canlii")
    else:
        sources_skipped.append("canlii")

    news = await classify_articles(profile.canonical_name, news)
    if SETTINGS.has_anthropic:
        sources_run.append("claude_classifier")
    else:
        sources_skipped.append("claude_classifier")

    forensics = await fetch_forensics(profile)
    sources_run.append("forensics")

    gdelt_yearly, gdelt_first = await gdelt.fetch_yearly_and_first(
        [profile.canonical_name] + profile.aliases[:4]
    )
    sources_run.append("gdelt")

    if funding_events is None:
        try:
            funding_events = fetch_funding_events(profile)
        except Exception as e:  # noqa: BLE001
            logger.warning("funding events fetch failed: %s", e)
            funding_events = []

    adverse = _adverse_events_from_sources(sanctions, court, news)

    risk = compute_risk(
        sanctions=sanctions,
        court_cases=court,
        news=news,
        forensics=forensics,
        adverse_events=adverse,
        gdelt_yearly=gdelt_yearly,
    )

    briefing = await author_briefing_memo(
        profile=profile,
        sanctions=sanctions,
        court=court,
        news=news,
        forensics=forensics,
        risk_score=risk.score,
    )
    actions = await author_actions(
        profile=profile,
        sanctions=sanctions,
        court=court,
        news=news,
        forensics=forensics,
        risk_score=risk.score,
    )

    candidates = [a.date for a in adverse if a.date]
    if gdelt_first:
        candidates.append(gdelt_first)
    first_adverse = min(candidates) if candidates else None

    provenance = _build_provenance(profile, sanctions, court, news, forensics)

    dossier = ScreeningDossier(
        org=profile,
        risk=risk,
        timeline_funding=funding_events or [],
        timeline_adverse=adverse,
        sanctions=sanctions,
        court_cases=court,
        news=news,
        forensics=forensics,
        related_entities=related or [],
        gdelt_yearly=gdelt_yearly,
        first_adverse_signal=first_adverse,
        briefing_memo=briefing,
        actions=actions,
        provenance=provenance,
        sources_run=sources_run,
        sources_skipped=sources_skipped,
        cached_at=datetime.utcnow(),
    )
    write_screening(profile.id, dossier.model_dump(mode="json", by_alias=True))
    return dossier


async def screen_by_id(org_id: str) -> ScreeningDossier | None:
    found = fetch_org_by_id(org_id)
    if not found:
        return None
    profile, related = found
    return await screen_profile(profile, related)


async def screen_by_name(name: str) -> ScreeningDossier:
    """Live-search fallback: build a synthetic OrgProfile from name+fed lookup
    and run the screening anyway. Used for the demo's 'type any org' moment."""
    funding = fetch_funding_events_by_name(name)
    fed_total = sum((f.amount or 0) for f in funding) or None
    profile = OrgProfile(
        id=f"adhoc:{name.lower().strip().replace(' ', '_')}",
        canonical_name=name.strip(),
        aliases=[],
        fed_total=fed_total,
    )
    return await screen_profile(profile, related=[], funding_events=funding)
