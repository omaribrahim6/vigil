"""Pre-cache the demo dossiers and the top-orgs/portfolio summary so the
demo can run with no live API calls.

Run:
    python -m scripts.precache
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from google.cloud import bigquery

from app import bigquery_client, cache
from app.config import DATA_PROJECT, SETTINGS
from app.models import RiskBreakdown
from app.pipeline import screen_by_id
from app.risk_scorer import top_flag_for

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("precache")

DEMO_ORG_IDS = [
    ("42406", "WE Charity Foundation \u2014 primary headline"),
    ("72807", "WE Charity \u2014 network propagation"),
    ("50517", "Canada Charity Partners \u2014 CRA-revoked obscure case"),
]


def find_top_circular_charity_with_funding() -> tuple[str, str] | None:
    """Highest cra.loop_universe score for a BN whose root matches a goldens
    record with non-zero federal funding. The forensic kill-shot demo org."""
    sql = f"""
    WITH loops AS (
      SELECT SUBSTR(bn, 1, 9) AS bn9, MAX(score) AS score, ANY_VALUE(legal_name) AS legal_name
      FROM `{DATA_PROJECT}.cra.loop_universe`
      WHERE score IS NOT NULL
      GROUP BY bn9
    )
    SELECT
      CAST(g.id AS STRING) AS id,
      g.canonical_name,
      l.score,
      CAST(JSON_VALUE(g.fed_profile, '$.total_grants') AS FLOAT64) AS fed_total
    FROM loops l
    JOIN `{DATA_PROJECT}.general.entity_golden_records` g
      ON g.bn_root = l.bn9
    WHERE JSON_VALUE(g.fed_profile, '$.total_grants') IS NOT NULL
      AND CAST(JSON_VALUE(g.fed_profile, '$.total_grants') AS FLOAT64) >= 1000000
    ORDER BY l.score DESC, fed_total DESC
    LIMIT 1
    """
    try:
        rows = list(bigquery_client.get_client().query(sql))
    except Exception as e:  # noqa: BLE001
        log.warning("loop kill-shot query failed: %s", e)
        return None
    if not rows:
        return None
    r = rows[0]
    log.info(
        "loop kill-shot: %s (id=%s, score=%s, fed=%.0f)",
        r["canonical_name"], r["id"], r["score"], r["fed_total"] or 0,
    )
    return str(r["id"]), f"top circular-gifting (score {r['score']}/30)"


async def cache_top_orgs() -> int:
    """Caches the dashboard's top-orgs list. We ALWAYS prepend any screened
    org (even if its fed_total wouldn't make the top 200) so the demo's
    flagged entities are guaranteed visible."""
    log.info("Caching top-200 orgs from BigQuery\u2026")
    rows = bigquery_client.fetch_top_orgs(200)
    enriched: list[dict] = []
    seen_ids: set[str] = set()

    # 1. Inject screened orgs first so they show at the top with their risk badges.
    screenings_dir = Path(cache.SCREENINGS_DIR)
    for f in sorted(screenings_dir.glob("*.json")):
        if f.stem.startswith("adhoc:"):
            continue
        data = cache.read_screening(f.stem)
        if not data:
            continue
        org = data.get("org") or {}
        risk = data.get("risk") or {}
        breakdown = RiskBreakdown(**risk) if risk else None
        actions = data.get("actions") or []
        immediate = sum(1 for a in actions if a.get("urgency") == "immediate")
        province = org.get("province")
        enriched.append(
            {
                "id": str(org.get("id") or f.stem),
                "canonical_name": org.get("canonical_name") or "(unknown)",
                "province": province,
                "fed_total": org.get("fed_total"),
                "cra_designation": org.get("cra_designation"),
                "risk_score": risk.get("score"),
                "risk_tier": risk.get("tier") or "UNRATED",
                "top_flag": top_flag_for(breakdown) if breakdown else None,
                "immediate_actions": immediate,
                "total_actions": len(actions),
            }
        )
        seen_ids.add(str(org.get("id") or f.stem))

    # 2. Append the BigQuery top-N, skipping anything already shown.
    for row in rows:
        if row.id in seen_ids:
            continue
        screening = cache.read_screening(row.id)
        if screening:
            risk = screening.get("risk") or {}
            row.risk_score = risk.get("score")
            row.risk_tier = risk.get("tier") or "UNRATED"
            breakdown = RiskBreakdown(**risk) if risk else None
            row.top_flag = top_flag_for(breakdown) if breakdown else None
            actions = screening.get("actions") or []
            row.immediate_actions = sum(1 for a in actions if a.get("urgency") == "immediate")
            row.total_actions = len(actions)
        enriched.append(row.model_dump(mode="json"))
        seen_ids.add(row.id)

    cache.write_top_orgs(enriched)
    log.info("Cached %d top orgs (%d screened + others).", len(enriched), len(seen_ids) - (len(rows) - sum(1 for r in rows if r.id in seen_ids)))
    return len(enriched)


async def cache_portfolio_stats() -> None:
    log.info("Computing portfolio stats from cached screenings\u2026")
    screenings_dir = Path(cache.SCREENINGS_DIR)
    files = list(screenings_dir.glob("*.json"))
    flagged_count = 0
    flagged_funding = 0.0
    portfolio_funding = 0.0
    immediate_action_count = 0
    scheduled_action_count = 0
    orgs_with_immediate_actions = 0
    by_tier: dict[str, int] = {"RED": 0, "ORANGE": 0, "YELLOW": 0, "GREEN": 0, "UNRATED": 0}
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        risk = data.get("risk") or {}
        tier = risk.get("tier", "UNRATED")
        by_tier[tier] = by_tier.get(tier, 0) + 1
        fed = ((data.get("org") or {}).get("fed_total")) or 0
        ab = ((data.get("org") or {}).get("ab_total")) or 0
        total = float(fed or 0) + float(ab or 0)
        portfolio_funding += total
        if tier in ("RED", "ORANGE", "YELLOW"):
            flagged_count += 1
            flagged_funding += total
        actions = data.get("actions") or []
        org_imm = sum(1 for a in actions if a.get("urgency") == "immediate")
        immediate_action_count += org_imm
        scheduled_action_count += sum(1 for a in actions if a.get("urgency") == "scheduled")
        if org_imm > 0:
            orgs_with_immediate_actions += 1
    if immediate_action_count > 0:
        headline = (
            f"{immediate_action_count} immediate action{'s' if immediate_action_count != 1 else ''} "
            f"outstanding across {orgs_with_immediate_actions} flagged "
            f"{'organization' if orgs_with_immediate_actions == 1 else 'organizations'} "
            f"in the screened portfolio."
        )
    elif scheduled_action_count > 0:
        headline = (
            f"{scheduled_action_count} scheduled review{'s' if scheduled_action_count != 1 else ''} "
            f"recommended across the screened portfolio; no immediate actions."
        )
    else:
        headline = "No outstanding actions in the screened portfolio."
    stats = {
        "total_orgs_screened": len(files),
        "flagged_org_count": flagged_count,
        "flagged_total_funding": flagged_funding,
        "portfolio_total_funding": portfolio_funding,
        "by_tier": by_tier,
        "immediate_action_count": immediate_action_count,
        "scheduled_action_count": scheduled_action_count,
        "orgs_with_immediate_actions": orgs_with_immediate_actions,
        "headline": headline,
    }
    cache.write_portfolio_stats(stats)
    log.info("Portfolio: %s", headline)


async def main() -> None:
    if not SETTINGS.has_anthropic:
        log.warning("ANTHROPIC_API_KEY not set \u2014 briefing memo + classifier will use deterministic fallback.")
    if not SETTINGS.has_opensanctions:
        log.warning("OPENSANCTIONS_API_KEY not set \u2014 sanctions panel will be empty.")
    if not SETTINGS.has_tavily:
        log.warning("TAVILY_API_KEY not set \u2014 news panel will be empty.")
    if not SETTINGS.has_canlii:
        log.warning("CANLII_API_KEY not set \u2014 court panel will be empty.")

    targets = list(DEMO_ORG_IDS)
    fk = find_top_circular_charity_with_funding()
    if fk:
        targets.append(fk)
    for org_id, label in targets:
        log.info("Screening %s (%s)\u2026", org_id, label)
        try:
            dossier = await screen_by_id(org_id)
            if dossier is None:
                log.error("Org %s not found in goldens; skipping.", org_id)
                continue
            log.info(
                "  -> id=%s name=%r risk=%s/%s sources=%s",
                org_id, dossier.org.canonical_name, dossier.risk.score, dossier.risk.tier,
                dossier.sources_run,
            )
        except Exception as e:  # noqa: BLE001
            log.exception("screening %s failed: %s", org_id, e)

    await cache_top_orgs()
    await cache_portfolio_stats()
    log.info("Pre-cache complete.")


if __name__ == "__main__":
    asyncio.run(main())
