import { ShieldCheck, ExternalLink } from "lucide-react";
import type { RemediationContext } from "../lib/types";
import { Section, EmptyPanel } from "./Section";

function fmtDate(d?: string | null) {
  if (!d) return null;
  try {
    return new Date(d).toLocaleDateString("en-CA", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return d;
  }
}

export function RemediationPanel({ remediation }: { remediation: RemediationContext }) {
  const hasSignals = remediation && remediation.signal_count > 0;

  return (
    <Section
      title="Remediation context"
      subtitle="Positive-integrity signals that dampen historic adverse findings"
      right={
        hasSignals ? (
          <span className="inline-flex items-center gap-1.5 font-mono uppercase tracking-wider text-[10px]">
            <ShieldCheck size={12} className="text-[var(--risk-green)]" />
            {remediation.signal_count} signal{remediation.signal_count === 1 ? "" : "s"}
            {remediation.recent_signal_count > 0 && (
              <span className="text-[var(--risk-green)]">
                · {remediation.recent_signal_count} in last 24mo
              </span>
            )}
          </span>
        ) : null
      }
    >
      {!hasSignals ? (
        <EmptyPanel message="No documented remediation signals in the current sweep — historic adverse findings are not dampened." />
      ) : (
        <div className="space-y-3">
          <div
            className="rounded-md p-3 text-sm leading-snug"
            style={{
              background: "var(--risk-green-bg)",
              borderLeft: "4px solid var(--risk-green)",
            }}
          >
            <div className="font-semibold text-[var(--risk-green)] mb-1">
              Risk score dampened by{" "}
              {Math.round((1 - remediation.dampening_factor) * 100)}%
            </div>
            <p className="text-[var(--foreground)]/85">
              {remediation.recent_signal_count > 0
                ? `${remediation.recent_signal_count} corrective action${
                    remediation.recent_signal_count === 1 ? "" : "s"
                  } documented in the last 24 months. Historic adverse findings are weighted down accordingly; an active sanctions hit (if any) is never dampened.`
                : "Remediation signals were detected, but none are recent (≤24 months). Historic findings retain full weight."}
            </p>
          </div>

          <ol className="space-y-2">
            {remediation.articles.map((a, i) => (
              <li
                key={i}
                className="flex items-start gap-3 rounded-md border border-[var(--border)] bg-white p-3"
              >
                <span
                  className="mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full"
                  style={{
                    background: "var(--risk-green-bg)",
                    color: "var(--risk-green)",
                  }}
                >
                  <ShieldCheck size={14} />
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-wider font-mono text-[var(--muted)]">
                    {a.source_name && <span>{a.source_name}</span>}
                    {a.published_at && <span>· {fmtDate(a.published_at)}</span>}
                    {a.category && a.category !== "remediation" && (
                      <span>· {a.category}</span>
                    )}
                  </div>
                  <a
                    href={a.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-0.5 inline-flex items-start gap-1 font-medium text-[var(--foreground)] hover:text-[var(--accent)]"
                  >
                    <span className="text-sm leading-snug">{a.title}</span>
                    <ExternalLink
                      size={12}
                      className="mt-1 flex-shrink-0 opacity-60"
                    />
                  </a>
                  {a.summary && (
                    <p className="mt-1 text-xs text-[var(--foreground)]/75 leading-snug">
                      {a.summary}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}
    </Section>
  );
}
