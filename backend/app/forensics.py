"""Forensic-signals layer.

Pulls pre-computed accountability metrics from the hackathon repo's BigQuery
output: charity circular-gifting risk, T3010 form violations, overhead ratios,
sole-source contract preference, and a shared-director adjacency for network
propagation. Each signal is independently optional — `ForensicSignals` carries
None for whatever didn't return."""
from __future__ import annotations

import logging
from typing import Any

from google.cloud import bigquery

from .bigquery_client import get_client
from .config import DATA_PROJECT
from .models import ForensicSignals, OrgProfile

logger = logging.getLogger(__name__)

LOOP_UNIVERSE = f"`{DATA_PROJECT}.cra.loop_universe`"
T3010_VIOL = f"`{DATA_PROJECT}.cra.t3010_impossibilities`"
OVERHEAD = f"`{DATA_PROJECT}.cra.overhead_by_charity`"
DIRECTORS = f"`{DATA_PROJECT}.cra.cra_directors`"
AB_SOLE = f"`{DATA_PROJECT}.ab.ab_sole_source`"


def _bn_root_param(bn_root: str | None) -> bigquery.ScalarQueryParameter | None:
    if not bn_root:
        return None
    bn = bn_root.strip().split()[0][:9]
    if len(bn) < 9 or not bn.isdigit():
        return None
    return bigquery.ScalarQueryParameter("bn", "STRING", bn)


def fetch_loop(bn_root: str | None) -> tuple[int | None, float | None, dict[str, int] | None]:
    bn_param = _bn_root_param(bn_root)
    if not bn_param:
        return None, None, None
    sql = f"""
    SELECT
      MAX(score) AS score,
      MAX(total_circular_amt) AS total_circular_amt,
      MAX(loops_2hop) AS h2,
      MAX(loops_3hop) AS h3,
      MAX(loops_4hop) AS h4,
      MAX(loops_5hop) AS h5,
      MAX(loops_6hop) AS h6,
      MAX(loops_7plus) AS h7p
    FROM {LOOP_UNIVERSE}
    WHERE STARTS_WITH(bn, @bn)
    """
    try:
        rows = list(get_client().query(
            sql, job_config=bigquery.QueryJobConfig(query_parameters=[bn_param])
        ))
    except Exception as e:  # noqa: BLE001
        logger.warning("loop_universe query failed (%s): %s", bn_root, e)
        return None, None, None
    if not rows:
        return None, None, None
    r = rows[0]
    score = r.get("score")
    if score is None:
        return None, None, None
    breakdown = {
        "2hop": int(r.get("h2") or 0),
        "3hop": int(r.get("h3") or 0),
        "4hop": int(r.get("h4") or 0),
        "5hop": int(r.get("h5") or 0),
        "6hop": int(r.get("h6") or 0),
        "7plus": int(r.get("h7p") or 0),
    }
    total = r.get("total_circular_amt")
    return int(score), (float(total) if total is not None else None), breakdown


def fetch_t3010_violations(bn_root: str | None) -> tuple[int | None, list[str] | None]:
    bn_param = _bn_root_param(bn_root)
    if not bn_param:
        return None, None
    sql = f"""
    SELECT rule_code, rule_family, severity, fiscal_year
    FROM {T3010_VIOL}
    WHERE STARTS_WITH(bn, @bn)
    ORDER BY fiscal_year DESC, severity DESC
    LIMIT 25
    """
    try:
        rows = list(get_client().query(
            sql, job_config=bigquery.QueryJobConfig(query_parameters=[bn_param])
        ))
    except Exception as e:  # noqa: BLE001
        logger.warning("t3010_impossibilities query failed (%s): %s", bn_root, e)
        return None, None
    count = len(rows)
    examples: list[str] = []
    seen: set[str] = set()
    for r in rows:
        code = r.get("rule_code") or ""
        family = r.get("rule_family") or ""
        fy = r.get("fiscal_year")
        key = f"{code}|{fy}"
        if key in seen:
            continue
        seen.add(key)
        label = f"{family or 'rule'} {code}"
        if fy:
            label = f"{label} (FY{fy})"
        examples.append(label)
        if len(examples) >= 5:
            break
    if count == 0:
        return 0, []
    return count, examples


def fetch_overhead_max(bn_root: str | None) -> float | None:
    bn_param = _bn_root_param(bn_root)
    if not bn_param:
        return None
    sql = f"""
    SELECT MAX(strict_overhead_pct) AS pct
    FROM {OVERHEAD}
    WHERE STARTS_WITH(bn, @bn)
    """
    try:
        rows = list(get_client().query(
            sql, job_config=bigquery.QueryJobConfig(query_parameters=[bn_param])
        ))
    except Exception as e:  # noqa: BLE001
        logger.warning("overhead query failed (%s): %s", bn_root, e)
        return None
    if not rows:
        return None
    pct = rows[0].get("pct")
    return float(pct) if pct is not None else None


def fetch_ab_sole_source(name: str, aliases: list[str]) -> tuple[int | None, float | None]:
    candidate_names = [name] + (aliases or [])[:5]
    candidate_names = [n for n in candidate_names if n]
    if not candidate_names:
        return None, None
    params: list[bigquery.ScalarQueryParameter] = []
    likes = []
    for i, n in enumerate(candidate_names):
        likes.append(f"LOWER(vendor) LIKE @v{i}")
        params.append(bigquery.ScalarQueryParameter(f"v{i}", "STRING", f"%{n.lower()}%"))
    sql = f"""
    SELECT COUNT(*) AS n, SUM(amount) AS total
    FROM {AB_SOLE}
    WHERE {' OR '.join(likes)}
    """
    try:
        rows = list(get_client().query(
            sql, job_config=bigquery.QueryJobConfig(query_parameters=params)
        ))
    except Exception as e:  # noqa: BLE001
        logger.warning("ab_sole_source query failed (%s): %s", name, e)
        return None, None
    if not rows:
        return 0, 0.0
    r = rows[0]
    return int(r.get("n") or 0), float(r.get("total") or 0)


def fetch_shared_directors(bn_root: str | None, *, limit: int = 6) -> list[dict[str, Any]] | None:
    """Return up to `limit` other charities that share at least one director
    name with this org's most recent filing. Each row: {bn, legal_name,
    shared_count, sample_director}."""
    bn_param = _bn_root_param(bn_root)
    if not bn_param:
        return None
    sql = f"""
    WITH latest AS (
      SELECT bn, MAX(fpe) AS latest_fpe
      FROM {DIRECTORS}
      WHERE first_name IS NOT NULL AND last_name IS NOT NULL
      GROUP BY bn
    ),
    my_dirs AS (
      SELECT DISTINCT
        UPPER(TRIM(CONCAT(IFNULL(first_name,''), ' ', IFNULL(last_name,'')))) AS person
      FROM {DIRECTORS} d
      JOIN latest l ON l.bn = d.bn AND l.latest_fpe = d.fpe
      WHERE STARTS_WITH(d.bn, @bn)
        AND d.first_name IS NOT NULL AND d.last_name IS NOT NULL
    ),
    others AS (
      SELECT
        d.bn,
        UPPER(TRIM(CONCAT(IFNULL(d.first_name,''), ' ', IFNULL(d.last_name,'')))) AS person
      FROM {DIRECTORS} d
      JOIN latest l ON l.bn = d.bn AND l.latest_fpe = d.fpe
      WHERE NOT STARTS_WITH(d.bn, @bn)
        AND d.first_name IS NOT NULL AND d.last_name IS NOT NULL
    ),
    shared AS (
      SELECT
        o.bn,
        COUNT(DISTINCT o.person) AS shared_count,
        ANY_VALUE(o.person) AS sample_director
      FROM others o
      JOIN my_dirs m ON m.person = o.person
      GROUP BY o.bn
    )
    SELECT
      s.bn,
      s.shared_count,
      s.sample_director,
      ANY_VALUE(i.legal_name) AS legal_name
    FROM shared s
    LEFT JOIN `{DATA_PROJECT}.cra.cra_identification` i
      ON i.bn = s.bn
    GROUP BY s.bn, s.shared_count, s.sample_director
    ORDER BY s.shared_count DESC
    LIMIT @lim
    """
    params = [bn_param, bigquery.ScalarQueryParameter("lim", "INT64", limit)]
    try:
        rows = list(get_client().query(
            sql, job_config=bigquery.QueryJobConfig(query_parameters=params)
        ))
    except Exception as e:  # noqa: BLE001
        logger.warning("shared_directors query failed (%s): %s", bn_root, e)
        return None
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "bn": r.get("bn"),
                "legal_name": r.get("legal_name") or "(unknown charity)",
                "shared_count": int(r.get("shared_count") or 0),
                "sample_director": (r.get("sample_director") or "").title() or None,
            }
        )
    return out


async def fetch_forensics(profile: OrgProfile) -> ForensicSignals:
    """Run all forensic queries serially (each is fast and BQ caches identical
    queries). Async signature so the pipeline can `await` it alongside other
    sources, but underlying `get_client()` is sync."""
    bn_root = profile.bn_root
    loop_score, loop_total, loop_breakdown = fetch_loop(bn_root)
    t3010_count, t3010_examples = fetch_t3010_violations(bn_root)
    overhead = fetch_overhead_max(bn_root)
    ab_count, ab_total = fetch_ab_sole_source(profile.canonical_name, profile.aliases)
    shared = fetch_shared_directors(bn_root)
    return ForensicSignals(
        cra_loop_score=loop_score,
        cra_loop_total_circular_amt=loop_total,
        cra_loop_hop_breakdown=loop_breakdown,
        cra_t3010_violation_count=t3010_count,
        cra_t3010_violation_examples=t3010_examples,
        cra_max_overhead_ratio=overhead,
        ab_sole_source_count=ab_count,
        ab_sole_source_value=ab_total,
        shared_directors=shared,
    )
