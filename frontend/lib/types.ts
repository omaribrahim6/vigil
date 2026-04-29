// Mirrors backend/app/models.py — keep in sync if either side changes.

export type RiskTier = "RED" | "ORANGE" | "YELLOW" | "GREEN" | "UNRATED";
export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "NOISE";

export interface FundingEvent {
  source: "fed" | "ab" | "cra";
  date: string | null;
  amount: number | null;
  department_or_program?: string | null;
  title?: string | null;
  agreement_type?: string | null;
  description?: string | null;
}

export interface AdverseEvent {
  source: "canlii" | "opensanctions" | "tavily" | "gdelt" | "manual";
  date: string | null;
  title: string;
  severity: Severity;
  category?: string | null;
  summary?: string | null;
  url?: string | null;
  confidence?: number | null;
}

export interface SanctionsHit {
  list_name: string;
  countries: string[];
  score: number;
  schema: string;
  entity_url?: string | null;
}

export interface CourtCase {
  citation: string;
  title: string;
  case_id?: string | null;
  decision_date?: string | null;
  jurisdiction?: string | null;
  url?: string | null;
  snippet?: string | null;
}

export interface NewsArticle {
  title: string;
  url: string;
  source_name?: string | null;
  published_at?: string | null;
  severity?: Severity | null;
  category?: string | null;
  summary?: string | null;
  confidence?: number | null;
}

export interface ForensicSignals {
  cra_loop_score?: number | null;
  cra_loop_score_max: number;
  cra_loop_total_circular_amt?: number | null;
  cra_loop_hop_breakdown?: Record<string, number> | null;
  cra_t3010_violation_count?: number | null;
  cra_t3010_violation_examples?: string[] | null;
  cra_max_overhead_ratio?: number | null;
  ab_sole_source_count?: number | null;
  ab_sole_source_value?: number | null;
  shared_directors?: Array<{
    bn: string | null;
    legal_name: string;
    shared_count: number;
    sample_director?: string | null;
  }> | null;
}

export interface RelatedEntity {
  related_id?: string | number | null;
  name: string;
  relationship?: string | null;
  reasoning?: string | null;
  risk_tier?: RiskTier | null;
}

export interface OrgProfile {
  id: string;
  canonical_name: string;
  aliases: string[];
  bn_root?: string | null;
  entity_type?: string | null;
  province?: string | null;
  city?: string | null;
  fed_total?: number | null;
  fed_grant_count?: number | null;
  fed_top_departments: string[];
  cra_designation?: string | null;
  cra_category?: string | null;
  cra_registration_date?: string | null;
  ab_total?: number | null;
  ab_payment_count?: number | null;
  ab_ministries: string[];
  dataset_sources: string[];
}

export interface RiskBreakdown {
  score: number;
  tier: RiskTier;
  contributions: Record<string, number>;
  notes: string[];
}

export interface ActionItem {
  urgency: "immediate" | "scheduled" | "monitor" | "none";
  title: string;
  rationale: string;
  evidence: string[];
}

export interface ProvenanceTrail {
  bigquery_rows: string[];
  external_urls: Array<{ label: string; url: string }>;
}

export interface ScreeningDossier {
  org: OrgProfile;
  risk: RiskBreakdown;
  timeline_funding: FundingEvent[];
  timeline_adverse: AdverseEvent[];
  sanctions: SanctionsHit[];
  court_cases: CourtCase[];
  news: NewsArticle[];
  forensics: ForensicSignals;
  related_entities: RelatedEntity[];
  gdelt_yearly: Record<string, number>;
  first_adverse_signal?: string | null;
  briefing_memo?: string | null;
  actions: ActionItem[];
  provenance: ProvenanceTrail;
  sources_run: string[];
  sources_skipped: string[];
  cached_at?: string | null;
}

export interface TopOrgRow {
  id: string;
  canonical_name: string;
  province?: string | null;
  fed_total?: number | null;
  cra_designation?: string | null;
  risk_score?: number | null;
  risk_tier: RiskTier;
  top_flag?: string | null;
  immediate_actions?: number;
  total_actions?: number;
}

export interface PortfolioStats {
  total_orgs_screened: number;
  flagged_org_count: number;
  flagged_total_funding: number;
  portfolio_total_funding: number;
  by_tier: Record<RiskTier, number>;
  immediate_action_count?: number;
  scheduled_action_count?: number;
  orgs_with_immediate_actions?: number;
  headline: string;
}
