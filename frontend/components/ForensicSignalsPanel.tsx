import type { ForensicSignals } from "../lib/types";
import { fmtMoney } from "../lib/format";
import { EmptyPanel, Section } from "./Section";
import { AlertTriangle, ChartNetwork, FileWarning, Repeat, Users2 } from "lucide-react";

interface Props {
  forensics: ForensicSignals;
}

export function ForensicSignalsPanel({ forensics }: Props) {
  const items = [
    {
      key: "loop",
      icon: Repeat,
      label: "CRA circular-gifting risk",
      hide: forensics.cra_loop_score === null || forensics.cra_loop_score === undefined,
      primary:
        forensics.cra_loop_score !== null && forensics.cra_loop_score !== undefined
          ? `${forensics.cra_loop_score} / ${forensics.cra_loop_score_max}`
          : "—",
      detail:
        forensics.cra_loop_total_circular_amt
          ? `${fmtMoney(forensics.cra_loop_total_circular_amt, { compact: true })} in detected cycle flow`
          : forensics.cra_loop_hop_breakdown
          ? Object.entries(forensics.cra_loop_hop_breakdown)
              .filter(([, v]) => v > 0)
              .map(([k, v]) => `${v} × ${k}`)
              .join(" · ") || "no detected loops"
          : null,
      severity:
        forensics.cra_loop_score && forensics.cra_loop_score >= 15
          ? "high"
          : forensics.cra_loop_score && forensics.cra_loop_score >= 5
          ? "medium"
          : "info",
      source: "Pre-computed via Tarjan SCC + 2–6-hop cycle detection",
    },
    {
      key: "t3010",
      icon: FileWarning,
      label: "T3010 form violations",
      hide:
        forensics.cra_t3010_violation_count === null ||
        forensics.cra_t3010_violation_count === undefined,
      primary:
        forensics.cra_t3010_violation_count !== null &&
        forensics.cra_t3010_violation_count !== undefined
          ? `${forensics.cra_t3010_violation_count}`
          : "—",
      detail:
        forensics.cra_t3010_violation_examples?.slice(0, 3).join(" · ") ||
        (forensics.cra_t3010_violation_count === 0
          ? "no form impossibilities detected"
          : null),
      severity:
        forensics.cra_t3010_violation_count && forensics.cra_t3010_violation_count > 0
          ? "medium"
          : "info",
      source: "10 arithmetic-identity rules across CRA T3010 schedules",
    },
    {
      key: "overhead",
      icon: AlertTriangle,
      label: "Max overhead ratio",
      hide:
        forensics.cra_max_overhead_ratio === null ||
        forensics.cra_max_overhead_ratio === undefined,
      primary:
        forensics.cra_max_overhead_ratio !== null && forensics.cra_max_overhead_ratio !== undefined
          ? `${forensics.cra_max_overhead_ratio.toFixed(0)}%`
          : "—",
      detail:
        forensics.cra_max_overhead_ratio !== null && forensics.cra_max_overhead_ratio !== undefined
          ? "strict overhead = (admin + fundraising) / total expenditures"
          : null,
      severity:
        forensics.cra_max_overhead_ratio && forensics.cra_max_overhead_ratio > 50
          ? "medium"
          : "info",
      source: "Pre-computed per-charity per-year overhead rollup",
    },
    {
      key: "ss",
      icon: ChartNetwork,
      label: "Alberta sole-source contracts",
      hide:
        forensics.ab_sole_source_count === null ||
        forensics.ab_sole_source_count === undefined,
      primary: `${forensics.ab_sole_source_count ?? 0}`,
      detail:
        forensics.ab_sole_source_value
          ? `${fmtMoney(forensics.ab_sole_source_value, { compact: true })} total non-competitive value`
          : forensics.ab_sole_source_count === 0
          ? "no non-competitive Alberta contracts on file"
          : null,
      severity:
        forensics.ab_sole_source_count && forensics.ab_sole_source_count > 0
          ? "medium"
          : "info",
      source: "ab.ab_sole_source — Alberta sole-source contract registry",
    },
  ];

  const visible = items.filter((i) => !i.hide);
  const dirCluster = forensics.shared_directors || [];

  if (visible.length === 0 && dirCluster.length === 0) {
    return (
      <Section title="Forensic signals" subtitle="Pre-computed accountability metrics">
        <EmptyPanel message="No forensic signals available. (Likely a non-charity entity — CRA-T3010 metrics don't apply.)" />
      </Section>
    );
  }

  return (
    <Section
      title="Forensic signals"
      subtitle="Pre-computed accountability metrics from the CRA / fed / AB pipelines"
    >
      <div className="grid sm:grid-cols-2 gap-3">
        {visible.map((item) => {
          const Icon = item.icon;
          const sev =
            item.severity === "high"
              ? "border-[var(--risk-red)] bg-[var(--risk-red-bg)]/50"
              : item.severity === "medium"
              ? "border-[var(--risk-orange)] bg-[var(--risk-orange-bg)]/40"
              : "border-[var(--border)] bg-[var(--background)]/50";
          return (
            <div
              key={item.key}
              className={`rounded-md border-l-4 ${sev} px-4 py-3`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2 text-xs text-[var(--muted)] uppercase tracking-wider font-mono">
                  <Icon size={14} />
                  {item.label}
                </div>
                <div className="font-mono font-semibold text-lg leading-none">{item.primary}</div>
              </div>
              {item.detail && (
                <p className="mt-2 text-xs text-[var(--muted)] leading-snug">{item.detail}</p>
              )}
              <p className="mt-1.5 text-[10px] uppercase tracking-wider text-[var(--muted)]/70 font-mono">
                {item.source}
              </p>
            </div>
          );
        })}
      </div>

      {dirCluster.length > 0 && (
        <div className="mt-5 pt-5 border-t border-[var(--border)]">
          <div className="flex items-center gap-2 text-xs text-[var(--muted)] uppercase tracking-wider font-mono mb-3">
            <Users2 size={14} />
            Shared-director clusters
          </div>
          <ul className="divide-y divide-[var(--border)]">
            {dirCluster.map((d) => (
              <li
                key={d.bn || d.legal_name}
                className="py-2 flex items-baseline justify-between gap-3"
              >
                <div className="min-w-0">
                  <div className="text-sm font-medium truncate">{d.legal_name}</div>
                  {d.sample_director && (
                    <div className="text-[11px] text-[var(--muted)]">
                      shared director: {d.sample_director.replace(/\s+/g, " ").trim().toLowerCase().replace(/\b\w/g, c => c.toUpperCase())}
                    </div>
                  )}
                </div>
                <div className="font-mono text-xs text-[var(--muted)]">
                  {d.shared_count} shared
                </div>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-[10px] uppercase tracking-wider text-[var(--muted)]/70 font-mono">
            Source: cra.cra_directors latest filing per BN (2.87M rows)
          </p>
        </div>
      )}
    </Section>
  );
}
