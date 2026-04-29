import { ExternalLink, Gavel } from "lucide-react";
import type { CourtCase } from "../lib/types";
import { fmtDate } from "../lib/format";
import { EmptyPanel, Section } from "./Section";

export function CourtCasesPanel({
  cases,
  configured,
}: {
  cases: CourtCase[];
  configured: boolean;
}) {
  return (
    <Section
      title="Court records"
      subtitle="CanLII — primary legal sources"
      right={
        <span className="inline-flex items-center gap-1.5">
          <Gavel size={12} /> {cases.length} {cases.length === 1 ? "decision" : "decisions"}
        </span>
      }
    >
      {!configured ? (
        <EmptyPanel message="CanLII API key not configured. (Free key on request — toggles a court-records panel.)" />
      ) : cases.length === 0 ? (
        <EmptyPanel message="No matching court decisions found across CA / ON / QC / AB / BC databases." />
      ) : (
        <ul className="divide-y divide-[var(--border)]">
          {cases.map((c) => (
            <li key={c.case_id || c.citation} className="py-3 flex items-start gap-3">
              <div className="flex-shrink-0 mt-1 inline-flex items-center justify-center h-6 w-6 rounded-sm bg-[var(--accent)]/10 text-[var(--accent)]">
                <Gavel size={12} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium leading-tight">{c.title}</div>
                <div className="text-xs text-[var(--muted)] mt-0.5 flex flex-wrap gap-x-3 gap-y-1">
                  <span className="font-mono">{c.citation}</span>
                  {c.jurisdiction && <span>{c.jurisdiction}</span>}
                  {c.decision_date && <span>{fmtDate(c.decision_date)}</span>}
                </div>
                {c.snippet && (
                  <p className="mt-2 text-xs text-[var(--foreground)]/80 leading-snug line-clamp-3">
                    {c.snippet}
                  </p>
                )}
              </div>
              {c.url && (
                <a
                  href={c.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex-shrink-0 mt-1 text-xs text-[var(--accent)] hover:underline inline-flex items-center gap-1"
                >
                  Open <ExternalLink size={12} />
                </a>
              )}
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}
