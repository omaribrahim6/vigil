"""GDELT v2 historical adverse-mention frequency, queried via the BigQuery public
dataset `gdelt-bq.gdeltv2.events` (no extra key — uses gcloud ADC).

Yields a yearly count of events whose Actor1Name or Actor2Name matches the org
AND whose V2Themes include corruption/fraud/scandal/regulatory tokens. The
earliest such event date drives the timeline's 'first adverse signal' annotation.

We bound SQLDATE to >= 20100101 to keep scan size sensible."""
from __future__ import annotations

import logging
from datetime import date

from google.cloud import bigquery

from ..bigquery_client import get_client

logger = logging.getLogger(__name__)

ADVERSE_THEME_TOKENS = [
    "CORRUPTION",
    "FRAUD",
    "SCANDAL",
    "TRIAL",
    "BANKRUPTCY",
    "TAX_FNCACT_FRAUDSTER",
    "WB_2462_REGULATORY_AGENCIES",
]


def _name_filter(names: list[str]) -> tuple[str, list[bigquery.ScalarQueryParameter]]:
    parts: list[str] = []
    params: list[bigquery.ScalarQueryParameter] = []
    for i, n in enumerate(names):
        parts.append(f"LOWER(Actor1Name) LIKE @n{i} OR LOWER(Actor2Name) LIKE @n{i}")
        params.append(bigquery.ScalarQueryParameter(f"n{i}", "STRING", f"%{n.lower()}%"))
    return "(" + " OR ".join(parts) + ")", params


def _theme_filter() -> str:
    return "(" + " OR ".join(f"V2Themes LIKE '%{t}%'" for t in ADVERSE_THEME_TOKENS) + ")"


async def fetch_yearly_and_first(names: list[str]) -> tuple[dict[int, int], date | None]:
    """Returns (yearly_counts, earliest_adverse_date). Both empty/None when the
    query returns no rows or fails."""
    names = [n for n in names if n][:5]
    if not names:
        return {}, None
    name_clause, name_params = _name_filter(names)
    sql = f"""
    WITH adverse AS (
      SELECT SAFE.PARSE_DATE('%Y%m%d', CAST(SQLDATE AS STRING)) AS dt
      FROM `gdelt-bq.gdeltv2.events`
      WHERE SQLDATE >= 20100101
        AND {name_clause}
        AND {_theme_filter()}
    )
    SELECT
      ARRAY(
        SELECT AS STRUCT EXTRACT(YEAR FROM dt) AS year, COUNT(*) AS n
        FROM adverse
        WHERE dt IS NOT NULL
        GROUP BY year
        ORDER BY year
      ) AS yearly,
      (SELECT MIN(dt) FROM adverse WHERE dt IS NOT NULL) AS first_adverse
    """
    try:
        job = get_client().query(
            sql,
            job_config=bigquery.QueryJobConfig(query_parameters=name_params),
        )
        rows = list(job)
    except Exception as e:  # noqa: BLE001 - any BQ error degrades gracefully
        logger.warning("GDELT query failed for %s: %s", names, e)
        return {}, None
    if not rows:
        return {}, None
    row = rows[0]
    yearly_struct = row.get("yearly") or []
    yearly: dict[int, int] = {}
    for s in yearly_struct:
        y = s.get("year") if isinstance(s, dict) else getattr(s, "year", None)
        n = s.get("n") if isinstance(s, dict) else getattr(s, "n", None)
        if y is not None and n is not None:
            yearly[int(y)] = int(n)
    first = row.get("first_adverse")
    return yearly, first
