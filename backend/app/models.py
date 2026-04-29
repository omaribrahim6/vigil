"""Pydantic models for the API. Field names map 1:1 to what the frontend renders."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

RiskTier = Literal["RED", "ORANGE", "YELLOW", "GREEN", "UNRATED"]
Severity = Literal["CRITICAL", "HIGH", "MEDIUM", "NOISE"]


class FundingEvent(BaseModel):
    """Single grant / contribution row, used as a green marker on the timeline."""

    source: Literal["fed", "ab", "cra"]
    date: date | None
    amount: float | None
    department_or_program: str | None = None
    title: str | None = None
    agreement_type: str | None = None
    description: str | None = None


class AdverseEvent(BaseModel):
    """Single adverse event (court case, sanctions hit, news article, GDELT mention)
    that becomes a red marker on the timeline."""

    source: Literal["canlii", "opensanctions", "tavily", "gdelt", "manual"]
    date: date | None
    title: str
    severity: Severity
    category: str | None = None
    summary: str | None = None
    url: str | None = None
    confidence: float | None = None
    raw: dict[str, Any] | None = None


class SanctionsHit(BaseModel):
    list_name: str
    countries: list[str]
    score: float
    schema_: str = Field(alias="schema")
    entity_url: str | None = None
    raw: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}


class CourtCase(BaseModel):
    citation: str
    title: str
    case_id: str | None = None
    decision_date: date | None = None
    jurisdiction: str | None = None
    url: str | None = None
    snippet: str | None = None


class NewsArticle(BaseModel):
    title: str
    url: str
    source_name: str | None = None
    published_at: date | None = None
    severity: Severity | None = None
    category: str | None = None
    summary: str | None = None
    confidence: float | None = None
    is_remediation: bool = False
    is_stale: bool = False
    age_years: float | None = None


class RemediationContext(BaseModel):
    """Positive-integrity signals (settlements completed, leadership change,
    integrity awards, ethics certifications, monitorship concluded).

    Surfaces alongside adverse media so a funder sees the *full* picture, not
    just historic bad news. Used to dampen the risk score when material
    remediation has occurred in the last 24 months."""

    signal_count: int = 0
    recent_signal_count: int = 0
    most_recent_at: date | None = None
    summary: str | None = None
    dampening_factor: float = 1.0
    articles: list[NewsArticle] = Field(default_factory=list)


class ForensicSignals(BaseModel):
    """Pre-computed accountability signals from the hackathon repo's BigQuery tables.
    Each component is independently optional; missing -> None."""

    cra_loop_score: int | None = None
    cra_loop_score_max: int = 30
    cra_loop_total_circular_amt: float | None = None
    cra_loop_hop_breakdown: dict[str, int] | None = None
    cra_t3010_violation_count: int | None = None
    cra_t3010_violation_examples: list[str] | None = None
    cra_max_overhead_ratio: float | None = None
    ab_sole_source_count: int | None = None
    ab_sole_source_value: float | None = None
    shared_directors: list[dict[str, Any]] | None = None


class RelatedEntity(BaseModel):
    related_id: str | int | None = None
    name: str
    relationship: str | None = None
    reasoning: str | None = None
    risk_tier: RiskTier | None = None


class OrgProfile(BaseModel):
    """Funding/identity profile from `general.entity_golden_records`."""

    id: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    bn_root: str | None = None
    entity_type: str | None = None
    province: str | None = None
    city: str | None = None
    fed_total: float | None = None
    fed_grant_count: int | None = None
    fed_top_departments: list[str] = Field(default_factory=list)
    cra_designation: str | None = None
    cra_category: str | None = None
    cra_registration_date: date | None = None
    ab_total: float | None = None
    ab_payment_count: int | None = None
    ab_ministries: list[str] = Field(default_factory=list)
    dataset_sources: list[str] = Field(default_factory=list)


class RiskBreakdown(BaseModel):
    score: int
    tier: RiskTier
    contributions: dict[str, int]
    notes: list[str] = Field(default_factory=list)


class ActionItem(BaseModel):
    """A prescriptive next-step for a funder. The 'what should the funder do'
    answer that the screening produces."""

    urgency: Literal["immediate", "scheduled", "monitor", "none"]
    title: str
    rationale: str
    evidence: list[str] = Field(default_factory=list)


class ProvenanceTrail(BaseModel):
    """Every external row / URL that contributed to this dossier. Lets the UI
    answer 'show me where this fact came from'."""

    bigquery_rows: list[str] = Field(default_factory=list)
    external_urls: list[dict[str, str]] = Field(default_factory=list)


class ScreeningDossier(BaseModel):
    """Top-level dossier shape consumed by the frontend org-detail page."""

    org: OrgProfile
    risk: RiskBreakdown
    timeline_funding: list[FundingEvent] = Field(default_factory=list)
    timeline_adverse: list[AdverseEvent] = Field(default_factory=list)
    sanctions: list[SanctionsHit] = Field(default_factory=list)
    court_cases: list[CourtCase] = Field(default_factory=list)
    news: list[NewsArticle] = Field(default_factory=list)
    forensics: ForensicSignals = Field(default_factory=ForensicSignals)
    related_entities: list[RelatedEntity] = Field(default_factory=list)
    gdelt_yearly: dict[int, int] = Field(default_factory=dict)
    first_adverse_signal: date | None = None
    briefing_memo: str | None = None
    actions: list[ActionItem] = Field(default_factory=list)
    remediation: RemediationContext = Field(default_factory=RemediationContext)
    provenance: ProvenanceTrail = Field(default_factory=ProvenanceTrail)
    sources_run: list[str] = Field(default_factory=list)
    sources_skipped: list[str] = Field(default_factory=list)
    cached_at: datetime | None = None


class TopOrgRow(BaseModel):
    """Row shape for the dashboard table."""

    id: str
    canonical_name: str
    province: str | None = None
    fed_total: float | None = None
    cra_designation: str | None = None
    risk_score: int | None = None
    risk_tier: RiskTier = "UNRATED"
    top_flag: str | None = None
    immediate_actions: int = 0
    total_actions: int = 0


class PortfolioStats(BaseModel):
    total_orgs_screened: int
    flagged_org_count: int
    flagged_total_funding: float
    portfolio_total_funding: float
    by_tier: dict[RiskTier, int]
    immediate_action_count: int = 0
    scheduled_action_count: int = 0
    orgs_with_immediate_actions: int = 0
    headline: str
