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
    fetch_ab_payments_by_name,
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
    RemediationContext,
    RemediationEvent,
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
    is_adhoc = profile.id.startswith("adhoc-") or profile.id.startswith("adhoc:")
    bq_rows: list[str] = []
    if not is_adhoc:
        bq_rows.append(
            f"{DATA_PROJECT}.general.entity_golden_records id={profile.id}"
        )
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
        if a.is_remediation:
            continue
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
    list[SanctionsHit], list[NewsArticle], list[NewsArticle], list[CourtCase]
]:
    coros = [
        opensanctions.match_company(name),
        tavily.search_adverse(name),
        tavily.search_remediation(name),
        canlii.search_decisions(name),
    ]
    sanctions, adverse_news, remediation_news, court = await asyncio.gather(
        *coros, return_exceptions=False
    )
    return (
        sanctions if isinstance(sanctions, list) else [],
        adverse_news if isinstance(adverse_news, list) else [],
        remediation_news if isinstance(remediation_news, list) else [],
        court if isinstance(court, list) else [],
    )


# Independent third-party certifications carry more weight than self-published
# Code-of-Conduct PDFs. A SOURCE-name match here triggers a multiplier on the
# remediation signal so a single Ethisphere certification > 3 self-disclosures.
INDEPENDENT_CERTIFIERS = {
    "ethisphere.com",
    "iso.org",
    "transparencyinternational.org",
    "deloitte.com",   # external compliance audits
    "pwc.com",
    "kpmg.com",
    "ey.com",
    "finance.yahoo.com",  # press coverage of WMEC
    "businesswire.com",
    "globenewswire.com",
    "reuters.com",
    "bloomberg.com",
    "wsj.com",
    "ft.com",
    "csagroup.org",
    "bsigroup.com",
}

# Self-published / promotional sources are still useful context but don't
# count as independent verification of remediation.
SELF_PUBLISHED_DOMAINS = {
    "atkinsrealis.com", "snclavalin.com",
    # Falls through automatically for any *.com that matches the org slug
}


def _is_independent_source(source_name: str | None, org_name: str) -> bool:
    if not source_name:
        return False
    s = source_name.lower()
    if s in INDEPENDENT_CERTIFIERS:
        return True
    org_slug = (org_name or "").lower().replace(" ", "").replace("'", "")
    if org_slug and (org_slug in s or s.startswith(org_slug)):
        return False  # self-published
    return s not in SELF_PUBLISHED_DOMAINS


def _build_remediation_context(
    news: list[NewsArticle], org_name: str = ""
) -> RemediationContext:
    """Aggregate remediation-flagged articles into a single context object.

    A signal is 'recent' if it occurred in the last 24 months. Signals from
    independent third-party certifiers (Ethisphere, ISO, audit firms, major
    business press) count *double* — a self-published Code-of-Conduct PDF is
    not the same evidence as a Compliance Leader Verification."""
    from datetime import date, timedelta

    rem = [a for a in news if a.is_remediation]
    if not rem:
        return RemediationContext()
    cutoff = date.today() - timedelta(days=730)
    recent = [a for a in rem if a.published_at and a.published_at >= cutoff]
    independent_recent = [
        a for a in recent if _is_independent_source(a.source_name, org_name)
    ]
    most_recent = max(
        (a.published_at for a in rem if a.published_at),
        default=None,
    )
    summary_bits: list[str] = []
    for a in rem[:3]:
        bit = a.title.strip()
        if a.published_at:
            bit += f" ({a.published_at.isoformat()})"
        summary_bits.append(bit)
    summary = "; ".join(summary_bits) if summary_bits else None

    # Weighted recent count: independent certifications worth 2x.
    weighted = len(recent) + len(independent_recent)
    if weighted >= 5:
        damp = 0.35
    elif weighted >= 4:
        damp = 0.45
    elif weighted >= 3:
        damp = 0.55
    elif weighted == 2:
        damp = 0.7
    elif weighted == 1:
        damp = 0.85
    else:
        damp = 1.0
    return RemediationContext(
        signal_count=len(rem),
        recent_signal_count=len(recent),
        most_recent_at=most_recent,
        summary=summary,
        dampening_factor=damp,
        articles=rem[:6],
    )


def _annotate_age(news: list[NewsArticle]) -> list[NewsArticle]:
    """Compute `age_years` and `is_stale` on each article so the UI can show
    'historic / >5y old' badges without recomputing on every render."""
    from datetime import date

    today = date.today()
    out: list[NewsArticle] = []
    for a in news:
        if a.published_at:
            age = (today - a.published_at).days / 365.25
            out.append(a.model_copy(update={
                "age_years": round(age, 1),
                "is_stale": age > 5.0,
            }))
        else:
            out.append(a)
    return out


async def screen_profile(
    profile: OrgProfile,
    related: list[RelatedEntity] | None = None,
    *,
    funding_events: list[FundingEvent] | None = None,
) -> ScreeningDossier:
    sources_run: list[str] = []
    sources_skipped: list[str] = []

    sanctions, adverse_news, remediation_news, court = await _run_external_sources(
        profile.canonical_name
    )
    if SETTINGS.has_opensanctions:
        sources_run.append("opensanctions")
    else:
        sources_skipped.append("opensanctions")
    if SETTINGS.has_tavily:
        sources_run.append("tavily_adverse")
        sources_run.append("tavily_remediation")
    else:
        sources_skipped.append("tavily")
    if SETTINGS.has_canlii:
        sources_run.append("canlii")
    else:
        sources_skipped.append("canlii")

    # Classify adverse and remediation streams together so Claude sees them
    # in one pass and can disambiguate (e.g. a Tavily remediation hit that's
    # actually re-reporting the original wrongdoing).
    combined = adverse_news + remediation_news
    news = await classify_articles(profile.canonical_name, combined)
    news = _annotate_age(news)
    if SETTINGS.has_anthropic:
        sources_run.append("claude_classifier")
    else:
        sources_skipped.append("claude_classifier")

    remediation = _build_remediation_context(news, org_name=profile.canonical_name)

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
        # Merge in Alberta sole-source contracts so the timeline shows both
        # provincial and federal flow. Goldens orgs already have ab_total
        # from the goldens table; this just adds dated rows for the chart.
        try:
            ab_events = fetch_ab_payments_by_name(profile.canonical_name)
            funding_events = (funding_events or []) + ab_events
        except Exception as e:  # noqa: BLE001
            logger.warning("AB events fetch failed: %s", e)

    adverse = _adverse_events_from_sources(sanctions, court, news)

    risk = compute_risk(
        sanctions=sanctions,
        court_cases=court,
        news=news,
        forensics=forensics,
        adverse_events=adverse,
        gdelt_yearly=gdelt_yearly,
        remediation=remediation,
    )

    briefing = await author_briefing_memo(
        profile=profile,
        sanctions=sanctions,
        court=court,
        news=news,
        forensics=forensics,
        risk_score=risk.score,
        remediation=remediation,
    )
    actions = await author_actions(
        profile=profile,
        sanctions=sanctions,
        court=court,
        news=news,
        forensics=forensics,
        risk_score=risk.score,
        remediation=remediation,
    )

    candidates = [a.date for a in adverse if a.date]
    if gdelt_first:
        candidates.append(gdelt_first)
    first_adverse = min(candidates) if candidates else None

    # Surface dated remediation articles as their own timeline band so the
    # chart shows the full counter-narrative (e.g. Ethisphere certification
    # in 2023 sitting *after* a 2019 fraud article).
    timeline_rem: list[RemediationEvent] = []
    for a in news:
        if not a.is_remediation or not a.published_at:
            continue
        timeline_rem.append(
            RemediationEvent(
                date=a.published_at,
                title=a.title,
                summary=a.summary,
                url=a.url,
                source_name=a.source_name,
                is_independent=_is_independent_source(
                    a.source_name, profile.canonical_name
                ),
            )
        )

    provenance = _build_provenance(profile, sanctions, court, news, forensics)

    dossier = ScreeningDossier(
        org=profile,
        risk=risk,
        timeline_funding=funding_events or [],
        timeline_adverse=adverse,
        timeline_remediation=timeline_rem,
        sanctions=sanctions,
        court_cases=court,
        news=news,
        forensics=forensics,
        related_entities=related or [],
        gdelt_yearly=gdelt_yearly,
        first_adverse_signal=first_adverse,
        briefing_memo=briefing,
        actions=actions,
        remediation=remediation,
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
    and run the screening anyway. Used for the demo's 'type any org' moment.

    The fuzzy name matcher in `bigquery_client._name_variants` expands the
    query to accent-stripped, suffix-stripped, and known-alias variants so
    rebrands (AtkinsRéalis → SNC-Lavalin) and diacritics still hit BQ rows.
    Federal grants + Alberta sole-source contracts are merged into a single
    timeline; their summed amounts populate fed_total / ab_total so the
    header tiles aren't empty for adhoc orgs."""
    funding = fetch_funding_events_by_name(name)
    ab_funding = fetch_ab_payments_by_name(name)
    combined_funding = funding + ab_funding
    fed_total = sum((f.amount or 0) for f in funding) or None
    ab_total = sum((f.amount or 0) for f in ab_funding) or None
    fed_count = sum(1 for f in funding if f.amount) or None
    ab_count = sum(1 for f in ab_funding if f.amount) or None
    slug = "".join(
        c if c.isalnum() else "_"
        for c in name.lower().strip()
    ).strip("_") or "unknown"
    profile = OrgProfile(
        id=f"adhoc-{slug}",
        canonical_name=name.strip(),
        aliases=[],
        fed_total=fed_total,
        fed_grant_count=fed_count,
        ab_total=ab_total,
        ab_payment_count=ab_count,
    )
    return await screen_profile(profile, related=[], funding_events=combined_funding)
