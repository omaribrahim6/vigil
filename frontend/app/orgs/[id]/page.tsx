import { notFound } from "next/navigation";
import Link from "next/link";
import { ChevronLeft, MapPin } from "lucide-react";
import { getOrg } from "../../../lib/api";
import { fmtDate, fmtMoney } from "../../../lib/format";
import { RiskBadge } from "../../../components/RiskBadge";
import { Timeline } from "../../../components/Timeline";
import { BriefingMemo } from "../../../components/BriefingMemo";
import { ActionItems } from "../../../components/ActionItems";
import { ForensicSignalsPanel } from "../../../components/ForensicSignalsPanel";
import { CourtCasesPanel } from "../../../components/CourtCasesPanel";
import { NewsPanel } from "../../../components/NewsPanel";
import { RemediationPanel } from "../../../components/RemediationPanel";
import { SanctionsPanel } from "../../../components/SanctionsPanel";
import { RelatedEntities } from "../../../components/RelatedEntities";
import { ProvenancePanel } from "../../../components/ProvenancePanel";
import { Section } from "../../../components/Section";
import { StatTile } from "../../../components/StatTile";

export const dynamic = "force-dynamic";

export default async function OrgDetail({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let dossier;
  try {
    dossier = await getOrg(id);
  } catch (e) {
    if ((e as { status?: number }).status === 404) {
      notFound();
    }
    throw e;
  }
  const { org, risk, forensics } = dossier;

  const sanctionsRun = dossier.sources_run.includes("opensanctions");
  const tavilyRun = dossier.sources_run.includes("tavily");
  const canliiRun = dossier.sources_run.includes("canlii");

  return (
    <div className="space-y-6">
      <div>
        <Link
          href="/"
          className="inline-flex items-center gap-1 text-sm text-[var(--muted)] hover:text-[var(--accent)]"
        >
          <ChevronLeft size={14} /> Back to dashboard
        </Link>
      </div>

      {/* ─── Org header ─────────────────────────────────────────────── */}
      <header className="rounded-md border border-[var(--border)] bg-white px-6 py-5">
        <div className="flex items-start justify-between gap-6 flex-wrap">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-3 text-xs uppercase tracking-[0.2em] text-[var(--muted)] font-mono">
              {org.entity_type || "Organization"}
              {org.bn_root && (
                <>
                  <span aria-hidden>·</span>
                  <span>BN {org.bn_root}</span>
                </>
              )}
              {org.cra_designation && (
                <>
                  <span aria-hidden>·</span>
                  <span>CRA-{org.cra_designation}</span>
                </>
              )}
            </div>
            <h1 className="mt-1 text-3xl font-semibold tracking-tight">
              {org.canonical_name}
            </h1>
            <div className="mt-2 flex items-center gap-4 text-sm text-[var(--muted)]">
              {(org.city || org.province) && (
                <span className="inline-flex items-center gap-1.5">
                  <MapPin size={14} />
                  {[org.city, org.province].filter(Boolean).join(", ")}
                </span>
              )}
              {org.aliases.length > 0 && (
                <span>
                  {org.aliases.length} alias{org.aliases.length === 1 ? "" : "es"}
                </span>
              )}
              {org.dataset_sources.length > 0 && (
                <span className="font-mono uppercase tracking-wider text-[10px]">
                  {org.dataset_sources.join(" · ")}
                </span>
              )}
            </div>
          </div>
          <div className="flex flex-col items-end gap-2">
            <RiskBadge tier={risk.tier} score={risk.score} size="lg" />
            {risk.notes.length > 0 && (
              <ul className="text-xs text-[var(--muted)] text-right max-w-xs">
                {risk.notes.slice(0, 3).map((n, i) => (
                  <li key={i}>· {n}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
        <div className="mt-5 grid sm:grid-cols-4 gap-3">
          <StatTile
            label="Federal funding"
            value={fmtMoney(org.fed_total, { compact: true })}
            hint={
              org.fed_grant_count
                ? `${org.fed_grant_count.toLocaleString("en-CA")} agreements`
                : undefined
            }
            emphasis="accent"
          />
          <StatTile
            label="Alberta funding"
            value={fmtMoney(org.ab_total, { compact: true })}
            hint={
              org.ab_payment_count
                ? `${org.ab_payment_count.toLocaleString("en-CA")} payments`
                : undefined
            }
          />
          <StatTile
            label="First adverse signal"
            value={
              dossier.first_adverse_signal
                ? fmtDate(dossier.first_adverse_signal)
                : "—"
            }
            hint={
              dossier.first_adverse_signal
                ? "Earliest adverse marker on the timeline"
                : "No adverse signals returned"
            }
            emphasis={dossier.first_adverse_signal ? "red" : undefined}
          />
          <StatTile
            label="Sources run"
            value={`${dossier.sources_run.length} / ${
              dossier.sources_run.length + dossier.sources_skipped.length
            }`}
            hint={
              dossier.sources_skipped.length > 0
                ? `Skipped: ${dossier.sources_skipped.join(", ")}`
                : "All configured sources executed"
            }
          />
        </div>
        {org.fed_top_departments.length > 0 && (
          <div className="mt-4 text-xs text-[var(--muted)]">
            <span className="font-mono uppercase tracking-wider mr-2">Top federal departments:</span>
            {org.fed_top_departments.slice(0, 4).join(" · ")}
          </div>
        )}
      </header>

      {/* ─── Timeline (the money screen) ────────────────────────────── */}
      <Section
        title="Counterfactual timeline"
        subtitle="Funding events vs adverse signals — with first-signal annotation"
        emphasis
      >
        <Timeline
          funding={dossier.timeline_funding}
          adverse={dossier.timeline_adverse}
          firstAdverse={dossier.first_adverse_signal}
        />
      </Section>

      {/* ─── Action items (the 'so what') ───────────────────────────── */}
      <ActionItems actions={dossier.actions} />

      {/* ─── Remediation context (counterweight to adverse signals) ─── */}
      {dossier.remediation && (
        <RemediationPanel remediation={dossier.remediation} />
      )}

      {/* ─── Briefing memo ──────────────────────────────────────────── */}
      <BriefingMemo memo={dossier.briefing_memo} />

      {/* ─── Two-col panels ─────────────────────────────────────────── */}
      <div className="grid lg:grid-cols-2 gap-6">
        <SanctionsPanel hits={dossier.sanctions} configured={sanctionsRun} />
        <CourtCasesPanel cases={dossier.court_cases} configured={canliiRun} />
      </div>

      <ForensicSignalsPanel forensics={forensics} />

      <NewsPanel articles={dossier.news} configured={tavilyRun} />

      {dossier.related_entities.length > 0 && (
        <RelatedEntities related={dossier.related_entities} />
      )}

      <ProvenancePanel provenance={dossier.provenance} />

      <footer className="text-xs text-[var(--muted)] pt-4 border-t border-[var(--border)]">
        Cached at {dossier.cached_at ? fmtDate(dossier.cached_at) : "—"} · Sources:{" "}
        <span className="font-mono">{dossier.sources_run.join(", ") || "none"}</span>
      </footer>
    </div>
  );
}
