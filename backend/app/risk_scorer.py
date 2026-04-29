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
    RemediationContext,
    RiskBreakdown,
    RiskTier,
    SanctionsHit,
)


def _decay_weight(article_date: date | None) -> float:
    """Temporal decay so SNC-Lavalin-2014 doesn't outweigh GC-Strategies-2025.

    - <5y old:  full weight (1.0)
    - 5-10y:    half weight (0.5) — context, not driver
    - >10y:     quarter weight (0.25) — historical record only
    - unknown:  three-quarter weight (0.75) — hedge between recent and stale
    """
    if article_date is None:
        return 0.75
    age_days = (date.today() - article_date).days
    if age_days <= 365 * 5:
        return 1.0
    if age_days <= 365 * 10:
        return 0.5
    return 0.25


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
    remediation: RemediationContext | None = None,
) -> RiskBreakdown:
    contributions: dict[str, int] = {}
    notes: list[str] = []

    # Sanctions hit is current-state by definition — OpenSanctions removes
    # entries when delistings happen. No decay applied.
    sanctions_hit_score = 40 if sanctions else 0
    contributions["sanctions"] = sanctions_hit_score
    if sanctions:
        notes.append(f"OpenSanctions hit on {sanctions[0].list_name}")

    court_weights = [_decay_weight(c.decision_date) for c in court_cases]
    weighted_court = sum(court_weights[:3])
    court_score = round(15 * weighted_court)
    contributions["court_cases"] = court_score
    if court_cases:
        notes.append(
            f"{len(court_cases)} CanLII court matter(s) (weighted {weighted_court:.1f})"
        )

    # Adverse news only — remediation articles are excluded from the risk
    # calculation (they're surfaced separately).
    adverse_news = [a for a in news if not a.is_remediation]
    crit_weighted = sum(
        _decay_weight(a.published_at) for a in adverse_news if a.severity == "CRITICAL"
    )
    high_weighted = sum(
        _decay_weight(a.published_at) for a in adverse_news if a.severity == "HIGH"
    )
    crit_score = min(30, round(10 * crit_weighted))
    high_score = min(15, round(5 * high_weighted))
    contributions["critical_news"] = crit_score
    contributions["high_news"] = high_score

    crit_count = sum(1 for a in adverse_news if a.severity == "CRITICAL")
    high_count = sum(1 for a in adverse_news if a.severity == "HIGH")
    stale_count = sum(1 for a in adverse_news if a.is_stale)
    if crit_count:
        msg = f"{crit_count} CRITICAL news article(s)"
        if stale_count:
            msg += f" — {stale_count} are >5y old (down-weighted)"
        notes.append(msg)
    elif high_count:
        notes.append(f"{high_count} HIGH news article(s)")

    recency = _recency_weight(e.date for e in adverse_events if not e.title.startswith("Sanctions hit"))
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

    # ─── Remediation dampening ────────────────────────────────────────
    # If the org has demonstrated material remediation in the last 24 months
    # (new leadership, completed monitorship, integrity certification, ethics
    # award, settled/concluded historic matters), reduce the risk score so
    # historic adverse signals don't permanently brand the org. We never
    # dampen below the sanctions floor — an active sanctions hit is current
    # state and survives any dampening.
    dampening_factor = 1.0
    if remediation and remediation.recent_signal_count > 0:
        if remediation.recent_signal_count >= 3:
            dampening_factor = 0.55
        elif remediation.recent_signal_count == 2:
            dampening_factor = 0.7
        else:
            dampening_factor = 0.85
        notes.append(
            f"Remediation dampening x{dampening_factor:.2f} "
            f"({remediation.recent_signal_count} recent positive-integrity signal(s))"
        )

    if dampening_factor < 1.0:
        # Apply dampening to the historic-adverse contributions (not to
        # current-state sanctions). Court cases / news / GDELT / forensics
        # all describe past conduct, so they get dampened.
        keep_keys = {"sanctions"}
        damp_total = sum(v for k, v in contributions.items() if k not in keep_keys)
        kept_total = sum(v for k, v in contributions.items() if k in keep_keys)
        damped = round(damp_total * dampening_factor)
        contributions["remediation_dampening"] = -(damp_total - damped)
        raw = kept_total + damped

    score = max(0, min(100, raw))
    tier = _tier(score)

    # If we dampened the score AND the post-dampening tier is YELLOW or below,
    # tag a "post-remediation" note so the UI can show "Moderate — historic,
    # remediated" instead of just "Moderate". The score itself reflects the
    # dampening; this just lets the funder see the *story*.
    if dampening_factor < 1.0 and remediation and remediation.recent_signal_count > 0:
        if tier in ("YELLOW", "GREEN"):
            notes.append("Post-remediation: historic adverse signals are documented as addressed.")
        elif tier == "ORANGE":
            notes.append("Partial remediation: significant signals dampened but residual concerns remain.")

    return RiskBreakdown(
        score=score,
        tier=tier,
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
