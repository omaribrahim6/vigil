"""BigQuery wrapper: top-funded orgs, org-by-id, name/alias search, and per-org
federal-grant timeline events. Uses Application Default Credentials (gcloud)."""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date
from functools import lru_cache
from typing import Any, Iterable

from google.cloud import bigquery

from .config import DATA_PROJECT, SETTINGS
from .models import FundingEvent, OrgProfile, RelatedEntity, TopOrgRow

# Hand-curated alias expansion for the demo orgs (and other well-known
# Canadian recipients) so that searching by current legal name still
# matches grants filed under the historical name. Names are lowercase and
# matched as substrings (LIKE %x%), so we keep them short enough to be
# discriminating but long enough to avoid false positives.
KNOWN_NAME_ALIASES: dict[str, list[str]] = {
    "atkinsrealis": ["snc-lavalin", "snc lavalin", "atkins realis", "snclavalin"],
    "atkins realis": ["snc-lavalin", "snc lavalin", "atkinsrealis", "snclavalin"],
    "snc-lavalin": ["atkinsrealis", "atkins realis", "snclavalin"],
    "mckinsey & company canada": ["mckinsey", "mckinsey company", "mckinsey & company"],
    "mckinsey & company": ["mckinsey"],
    "gc strategies": ["gcstrategies", "g.c. strategies", "g.c strategies"],
    "coradix technology consulting": ["coradix"],
    "dalian enterprises": ["dalian"],
}

# Common corporate / legal suffixes we strip when generating LIKE variants.
_SUFFIX_PATTERNS = re.compile(
    r"\b(inc|incorporated|corp|corporation|ltd|limited|llc|llp|lp|group|"
    r"holdings|company|co|canada|canadian|services?|consulting|technology|"
    r"technologies|enterprises?|partners|associates|society|foundation|"
    r"l\.?p\.?|s\.?a\.?|n\.?v\.?|gmbh|plc|ltée|ltee|ltd\.?|inc\.?|"
    r"limitée|limitee)\b\.?",
    re.IGNORECASE,
)


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _name_variants(name: str) -> list[str]:
    """Generate substring-match candidates for fuzzy BQ funding lookups.

    Covers: original name (lowercased), accent-stripped, suffix-stripped,
    suffix-stripped + accent-stripped, and any hand-curated aliases. Caller
    uses each variant as a `LOWER(field) LIKE %v%` clause."""
    base = (name or "").strip()
    if not base:
        return []
    variants: list[str] = []

    def _add(v: str) -> None:
        v = re.sub(r"\s+", " ", v).strip(" -.,&")
        if not v or len(v) < 4:
            return
        if v.lower() not in {x.lower() for x in variants}:
            variants.append(v.lower())

    _add(base)
    no_accents = _strip_accents(base)
    _add(no_accents)
    no_suffix = _SUFFIX_PATTERNS.sub("", base)
    _add(no_suffix)
    _add(_strip_accents(no_suffix))

    for k, aliases in KNOWN_NAME_ALIASES.items():
        if k in base.lower() or k in no_accents.lower():
            for a in aliases:
                _add(a)

    return variants[:8]

GOLDENS = f"`{DATA_PROJECT}.general.entity_golden_records`"
FED_GC = f"`{DATA_PROJECT}.fed.grants_contributions`"


@lru_cache(maxsize=1)
def get_client() -> bigquery.Client:
    return bigquery.Client(project=SETTINGS.gcp_project_id)


# ─── helpers ──────────────────────────────────────────────────────────────


def _json_list(v: Any) -> list:
    """`JSON` columns come back as Python objects already, but legacy paths can
    return strings. Normalize to a list."""
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _json_obj(v: Any) -> dict:
    if v is None:
        return {}
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _safe_float(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _safe_int(v: Any) -> int | None:
    if v in (None, ""):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _aliases_to_strings(aliases: Any) -> list[str]:
    """Goldens `aliases` is an array of objects with a `name` field (and source
    provenance). Flatten to unique strings, capped."""
    out: list[str] = []
    seen: set[str] = set()
    for a in _json_list(aliases):
        if isinstance(a, dict):
            n = a.get("name") or a.get("alias")
        else:
            n = a
        if isinstance(n, str) and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _row_to_profile(row: bigquery.Row) -> OrgProfile:
    fed = _json_obj(row.get("fed_profile"))
    cra = _json_obj(row.get("cra_profile"))
    ab = _json_obj(row.get("ab_profile"))
    aliases = _aliases_to_strings(row.get("aliases"))
    sources = [s for s in _json_list(row.get("dataset_sources")) if isinstance(s, str)]

    province = (
        cra.get("province")
        or fed.get("province")
        or ab.get("province")
    )
    city = cra.get("city") or fed.get("city") or ab.get("city")

    fed_top_depts = []
    raw_depts = fed.get("top_departments") or []
    if isinstance(raw_depts, list):
        for d in raw_depts:
            if isinstance(d, str):
                fed_top_depts.append(d)
            elif isinstance(d, dict):
                name = d.get("name") or d.get("department")
                if isinstance(name, str):
                    fed_top_depts.append(name)

    ab_ministries = []
    raw_min = ab.get("ministries") or []
    if isinstance(raw_min, list):
        for m in raw_min:
            if isinstance(m, str):
                ab_ministries.append(m)
            elif isinstance(m, dict):
                name = m.get("name") or m.get("ministry")
                if isinstance(name, str):
                    ab_ministries.append(name)

    return OrgProfile(
        id=str(row["id"]),
        canonical_name=row["canonical_name"],
        aliases=aliases[:25],
        bn_root=row.get("bn_root"),
        entity_type=row.get("entity_type"),
        province=province,
        city=city,
        fed_total=_safe_float(fed.get("total_grants")),
        fed_grant_count=_safe_int(fed.get("grant_count")),
        fed_top_departments=fed_top_depts[:5],
        cra_designation=cra.get("designation"),
        cra_category=cra.get("category"),
        cra_registration_date=None,
        ab_total=_safe_float(ab.get("total_grants")),
        ab_payment_count=_safe_int(ab.get("payment_count")),
        ab_ministries=ab_ministries[:5],
        dataset_sources=sources,
    )


# ─── public API ───────────────────────────────────────────────────────────


def fetch_top_orgs(limit: int = 200) -> list[TopOrgRow]:
    """Top-funded golden orgs by federal total. The dashboard's main table."""
    sql = f"""
    SELECT
      CAST(id AS STRING) AS id,
      canonical_name,
      JSON_VALUE(fed_profile, '$.total_grants') AS fed_total,
      JSON_VALUE(fed_profile, '$.grant_count') AS fed_count,
      JSON_VALUE(cra_profile, '$.province') AS cra_province,
      JSON_VALUE(fed_profile, '$.province') AS fed_province,
      JSON_VALUE(ab_profile, '$.province') AS ab_province,
      JSON_VALUE(cra_profile, '$.designation') AS cra_designation
    FROM {GOLDENS}
    WHERE JSON_VALUE(fed_profile, '$.total_grants') IS NOT NULL
    ORDER BY CAST(JSON_VALUE(fed_profile, '$.total_grants') AS FLOAT64) DESC
    LIMIT @limit
    """
    job = get_client().query(
        sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("limit", "INT64", limit)]
        ),
    )
    rows: list[TopOrgRow] = []
    for r in job:
        rows.append(
            TopOrgRow(
                id=str(r["id"]),
                canonical_name=r["canonical_name"],
                province=r.get("cra_province") or r.get("fed_province") or r.get("ab_province"),
                fed_total=_safe_float(r.get("fed_total")),
                cra_designation=r.get("cra_designation"),
                risk_score=None,
                risk_tier="UNRATED",
                top_flag=None,
            )
        )
    return rows


def fetch_org_by_id(org_id: str) -> tuple[OrgProfile, list[RelatedEntity]] | None:
    sql = f"""
    SELECT
      id, canonical_name, bn_root, entity_type, aliases,
      fed_profile, cra_profile, ab_profile, dataset_sources, related_entities
    FROM {GOLDENS}
    WHERE CAST(id AS STRING) = @id
    LIMIT 1
    """
    job = get_client().query(
        sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("id", "STRING", org_id)]
        ),
    )
    rows = list(job)
    if not rows:
        return None
    row = rows[0]
    profile = _row_to_profile(row)

    related: list[RelatedEntity] = []
    for r in _json_list(row.get("related_entities")):
        if not isinstance(r, dict):
            continue
        related.append(
            RelatedEntity(
                related_id=r.get("id") or r.get("entity_id"),
                name=r.get("canonical_name") or r.get("name") or "(unknown)",
                relationship=r.get("relationship") or r.get("type"),
                reasoning=r.get("reasoning") or r.get("reason"),
            )
        )
    return profile, related


def search_orgs(query: str, limit: int = 25) -> list[TopOrgRow]:
    """Substring search by canonical_name. (Aliases live in JSON; we fold them
    into ranking via a CONTAINS_SUBSTR over JSON_QUERY for breadth.)"""
    if not query or not query.strip():
        return []
    sql = f"""
    SELECT
      CAST(id AS STRING) AS id,
      canonical_name,
      JSON_VALUE(fed_profile, '$.total_grants') AS fed_total,
      JSON_VALUE(cra_profile, '$.province') AS cra_province,
      JSON_VALUE(fed_profile, '$.province') AS fed_province,
      JSON_VALUE(cra_profile, '$.designation') AS cra_designation
    FROM {GOLDENS}
    WHERE LOWER(canonical_name) LIKE LOWER(@q)
       OR CONTAINS_SUBSTR(JSON_QUERY(aliases, '$'), @term)
    ORDER BY
      (CASE WHEN LOWER(canonical_name) = LOWER(@term) THEN 0
            WHEN LOWER(canonical_name) LIKE LOWER(@start) THEN 1
            ELSE 2 END),
      CAST(COALESCE(JSON_VALUE(fed_profile, '$.total_grants'), '0') AS FLOAT64) DESC
    LIMIT @limit
    """
    term = query.strip()
    job = get_client().query(
        sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("q", "STRING", f"%{term}%"),
                bigquery.ScalarQueryParameter("term", "STRING", term),
                bigquery.ScalarQueryParameter("start", "STRING", f"{term}%"),
                bigquery.ScalarQueryParameter("limit", "INT64", limit),
            ]
        ),
    )
    out: list[TopOrgRow] = []
    for r in job:
        out.append(
            TopOrgRow(
                id=str(r["id"]),
                canonical_name=r["canonical_name"],
                province=r.get("cra_province") or r.get("fed_province"),
                fed_total=_safe_float(r.get("fed_total")),
                cra_designation=r.get("cra_designation"),
            )
        )
    return out


def fetch_funding_events(profile: OrgProfile, limit: int = 80) -> list[FundingEvent]:
    """Pulls actual federal grant rows for the timeline. Joins by canonical_name +
    aliases (LOWER substring). BN match is most precise but the goldens column
    holds the root only; recipient_business_number includes program suffixes."""
    names = [profile.canonical_name] + profile.aliases[:5]
    names = [n for n in names if n]
    if not names:
        return []
    name_params = [bigquery.ScalarQueryParameter(f"n{i}", "STRING", f"%{n.lower()}%")
                   for i, n in enumerate(names)]
    name_filter = " OR ".join(
        f"LOWER(recipient_legal_name) LIKE @n{i} OR LOWER(recipient_operating_name) LIKE @n{i}"
        for i, _ in enumerate(names)
    )
    bn_filter = ""
    params: list[bigquery.ScalarQueryParameter | bigquery.ArrayQueryParameter] = list(name_params)
    if profile.bn_root:
        bn_filter = " OR STARTS_WITH(recipient_business_number, @bn)"
        params.append(bigquery.ScalarQueryParameter("bn", "STRING", profile.bn_root))
    params.append(bigquery.ScalarQueryParameter("lim", "INT64", limit))

    sql = f"""
    SELECT
      agreement_start_date,
      agreement_value,
      owner_org_title,
      prog_name_en,
      agreement_title_en,
      agreement_type,
      description_en
    FROM {FED_GC}
    WHERE is_amendment IS NOT TRUE
      AND ({name_filter} {bn_filter})
    ORDER BY agreement_start_date DESC
    LIMIT @lim
    """
    job = get_client().query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
    events: list[FundingEvent] = []
    for r in job:
        d = r.get("agreement_start_date")
        events.append(
            FundingEvent(
                source="fed",
                date=d.date() if d else None,
                amount=_safe_float(r.get("agreement_value")),
                department_or_program=r.get("owner_org_title") or r.get("prog_name_en"),
                title=r.get("agreement_title_en"),
                agreement_type=r.get("agreement_type"),
                description=(r.get("description_en") or "")[:400] or None,
            )
        )
    return events


def fetch_funding_events_by_name(name: str, limit: int = 80) -> list[FundingEvent]:
    """Fallback used by live-search when the org isn't in the goldens table.

    Builds a *fuzzy* substring match: tries the original name, accent-stripped,
    suffix-stripped, and any known aliases (e.g. AtkinsRéalis ↔ SNC-Lavalin).
    Without this, demo orgs with diacritics or rebrands return zero funding
    events and the timeline / fed_total reads as `—`."""
    variants = _name_variants(name)
    if not variants:
        return []
    params: list[bigquery.ScalarQueryParameter] = []
    likes: list[str] = []
    for i, v in enumerate(variants):
        likes.append(
            f"LOWER(recipient_legal_name) LIKE @v{i} "
            f"OR LOWER(recipient_operating_name) LIKE @v{i}"
        )
        params.append(bigquery.ScalarQueryParameter(f"v{i}", "STRING", f"%{v}%"))
    params.append(bigquery.ScalarQueryParameter("lim", "INT64", limit))
    sql = f"""
    SELECT
      agreement_start_date,
      agreement_value,
      owner_org_title,
      prog_name_en,
      agreement_title_en,
      agreement_type,
      description_en,
      recipient_legal_name
    FROM {FED_GC}
    WHERE is_amendment IS NOT TRUE
      AND ({' OR '.join(likes)})
    ORDER BY agreement_start_date DESC
    LIMIT @lim
    """
    try:
        job = get_client().query(
            sql, job_config=bigquery.QueryJobConfig(query_parameters=params)
        )
    except Exception:  # noqa: BLE001
        return []
    out: list[FundingEvent] = []
    for r in job:
        d = r.get("agreement_start_date")
        out.append(
            FundingEvent(
                source="fed",
                date=d.date() if d else None,
                amount=_safe_float(r.get("agreement_value")),
                department_or_program=r.get("owner_org_title") or r.get("prog_name_en"),
                title=r.get("agreement_title_en"),
                agreement_type=r.get("agreement_type"),
                description=(r.get("description_en") or "")[:400] or None,
            )
        )
    return out


def fetch_ab_payments_by_name(name: str, limit: int = 60) -> list[FundingEvent]:
    """Pull Alberta sole-source contracts for the timeline. (No general AB
    grants table is available in the dataset, but `ab.ab_sole_source` covers
    most of the Alberta funding flow we care about for due diligence.)
    Used by both screen_by_name and to populate the AB band of the timeline.
    """
    variants = _name_variants(name)
    if not variants:
        return []
    params: list[bigquery.ScalarQueryParameter] = []
    likes: list[str] = []
    for i, v in enumerate(variants):
        likes.append(f"LOWER(vendor) LIKE @v{i}")
        params.append(bigquery.ScalarQueryParameter(f"v{i}", "STRING", f"%{v}%"))
    params.append(bigquery.ScalarQueryParameter("lim", "INT64", limit))
    sql = f"""
    SELECT
      start_date,
      amount,
      ministry,
      contract_services,
      vendor
    FROM `{DATA_PROJECT}.ab.ab_sole_source`
    WHERE {' OR '.join(likes)}
    ORDER BY start_date DESC
    LIMIT @lim
    """
    try:
        job = get_client().query(
            sql, job_config=bigquery.QueryJobConfig(query_parameters=params)
        )
    except Exception:  # noqa: BLE001
        return []
    out: list[FundingEvent] = []
    for r in job:
        d = r.get("start_date")
        out.append(
            FundingEvent(
                source="ab",
                date=d.date() if hasattr(d, "date") and d else (d if isinstance(d, date) else None),
                amount=_safe_float(r.get("amount")),
                department_or_program=r.get("ministry"),
                title=r.get("contract_services"),
                agreement_type="sole_source",
                description=None,
            )
        )
    return out
