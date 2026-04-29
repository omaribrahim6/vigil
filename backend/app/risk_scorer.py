"""Risk scoring.

Spec §6 step 7 extended with a forensic-signals layer (the differentiator).
Each component is independently optional; missing data contributes 0 (graceful
degradation). Score is clipped to 0..100 and tier-coloured."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

from .models import (
    AdverseEvent,
    CourtCase,
    ForensicSignals,
    NewsArticle,
    RiskBreakdown,
    RiskTier,
    SanctionsHit,
)


def _tier(score: int) -> RiskTier:
    if score >= 70:
        return "RED"
    if score >= 40:
        return "ORANGE"
    if score >= 20:
        return "YELLOW"
    return "GREEN"


def _recency_weight(events: Iterable[date | None]) -> float:
    """0..1 based on how many adverse events are within the last 24 months."""
    cutoff = date.today() - timedelta(days=730)
    dates = [d for d in events if d]
    if not dates:
        return 0.0
    recent = sum(1 for d in dates if d >= cutoff)
    if recent == 0:
        return 0.0
    return min(1.0, recent / 3)


def compute_risk(
    *,
    sanctions: list[SanctionsHit],
    court_cases: list[CourtCase],
    news: list[NewsArticle],
    forensics: ForensicSignals,
    adverse_events: list[AdverseEvent],
    gdelt_yearly: dict[int, int] | None = None,
) -> RiskBreakdown:
    contributions: dict[str, int] = {}
    notes: list[str] = []

    # ─── External-signals layer (spec §6 step 7) ──────────────────────
    sanctions_hit_score = 40 if sanctions else 0
    contributions["sanctions"] = sanctions_hit_score
    if sanctions:
        notes.append(f"OpenSanctions hit on {sanctions[0].list_name}")

    court_score = 15 * min(len(court_cases), 3)
    contributions["court_cases"] = court_score
    if court_cases:
        notes.append(f"{len(court_cases)} CanLII court matter(s)")

    crit = sum(1 for a in news if a.severity == "CRITICAL")
    high = sum(1 for a in news if a.severity == "HIGH")
    crit_score = min(30, 10 * crit)
    high_score = min(15, 5 * high)
    contributions["critical_news"] = crit_score
    contributions["high_news"] = high_score
    if crit:
        notes.append(f"{crit} CRITICAL news article(s)")
    elif high:
        notes.append(f"{high} HIGH news article(s)")

    recency = _recency_weight(e.date for e in adverse_events)
    recency_score = round(10 * recency)
    contributions["recency"] = recency_score

    # ─── Forensic-signals layer (the differentiator) ──────────────────
    if forensics.cra_loop_score is not None:
        loop_pts = round(10 * (forensics.cra_loop_score / 30))
        contributions["cra_loop"] = loop_pts
        if loop_pts >= 5:
            notes.append(f"CRA circular-gifting score {forensics.cra_loop_score}/30")
    else:
        contributions["cra_loop"] = 0

    if forensics.cra_t3010_violation_count and forensics.cra_t3010_violation_count > 0:
        contributions["t3010_violations"] = 5
        notes.append(f"{forensics.cra_t3010_violation_count} T3010 form violation(s)")
    else:
        contributions["t3010_violations"] = 0

    overhead = forensics.cra_max_overhead_ratio
    if overhead is not None and overhead > 50:
        contributions["overhead"] = 5
        notes.append(f"high overhead ratio ({overhead:.0f}%)")
    else:
        contributions["overhead"] = 0

    if forensics.ab_sole_source_count and forensics.ab_sole_source_count > 0:
        contributions["ab_sole_source"] = 5
        notes.append(f"{forensics.ab_sole_source_count} Alberta sole-source contract(s)")
    else:
        contributions["ab_sole_source"] = 0

    # GDELT historical-frequency layer (cap at 10 pts).
    if gdelt_yearly:
        peak = max(gdelt_yearly.values()) if gdelt_yearly else 0
        if peak >= 100:
            contributions["gdelt_spike"] = 10
            peak_year = max(gdelt_yearly, key=lambda y: gdelt_yearly[y])
            notes.append(f"GDELT adverse-event spike: {peak} events in {peak_year}")
        elif peak >= 30:
            contributions["gdelt_spike"] = 5
        elif peak >= 5:
            contributions["gdelt_spike"] = 3
        else:
            contributions["gdelt_spike"] = 0
    else:
        contributions["gdelt_spike"] = 0

    raw = sum(contributions.values())
    score = max(0, min(100, raw))
    return RiskBreakdown(
        score=score,
        tier=_tier(score),
        contributions=contributions,
        notes=notes,
    )


def top_flag_for(breakdown: RiskBreakdown) -> str | None:
    """Pick the most important contribution to surface in the dashboard table."""
    priority = [
        ("sanctions", "Sanctions hit"),
        ("court_cases", "Court matter"),
        ("critical_news", "Critical adverse media"),
        ("cra_loop", "Circular gifting"),
        ("gdelt_spike", "Historical adverse-event spike"),
        ("t3010_violations", "T3010 violations"),
        ("ab_sole_source", "Sole-source preference"),
        ("overhead", "High overhead"),
        ("high_news", "Adverse media"),
        ("recency", "Recent adverse signal"),
    ]
    for key, label in priority:
        if breakdown.contributions.get(key, 0) > 0:
            return label
    return None
