"""GDELT v2 historical adverse-mention frequency, queried via the BigQuery public
GKG dataset `gdelt-bq.gdeltv2.gkg_partitioned`.

GKG (Global Knowledge Graph) carries `V2Organizations`, `V2Persons`, and
`V2Themes` — the right surfaces for org-level adverse-event detection. We bound
DATE to >= 20100101 to keep scan size sensible. No extra key — uses gcloud ADC."""
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
    "REGULATORY_AGENCIES",
    "TAX_FNCACT_INVESTIGATOR",
    "MILITARY",
]


def _name_filter(names: list[str]) -> tuple[str, list[bigquery.ScalarQueryParameter]]:
    parts: list[str] = []
    params: list[bigquery.ScalarQueryParameter] = []
    for i, n in enumerate(names):
        parts.append(f"LOWER(V2Organizations) LIKE @n{i}")
        params.append(bigquery.ScalarQueryParameter(f"n{i}", "STRING", f"%{n.lower()}%"))
    return "(" + " OR ".join(parts) + ")", params


def _theme_filter() -> str:
    return "(" + " OR ".join(f"V2Themes LIKE '%{t}%'" for t in ADVERSE_THEME_TOKENS) + ")"


async def fetch_yearly_and_first(names: list[str]) -> tuple[dict[int, int], date | None]:
    """Returns (yearly_counts, earliest_adverse_date). Both empty/None on no
    rows or any error."""
    names = [n for n in names if n][:5]
    if not names:
        return {}, None
    name_clause, name_params = _name_filter(names)
    sql = f"""
    WITH adverse AS (
      SELECT SAFE.PARSE_DATE('%Y%m%d', SUBSTR(CAST(DATE AS STRING), 1, 8)) AS dt
      FROM `gdelt-bq.gdeltv2.gkg_partitioned`
      WHERE _PARTITIONTIME >= TIMESTAMP("2010-01-01")
        AND DATE >= 20100101000000
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
    except Exception as e:  # noqa: BLE001
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
