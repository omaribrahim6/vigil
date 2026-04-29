import { Database, ExternalLink, Link2 } from "lucide-react";
import type { ProvenanceTrail } from "../lib/types";
import { Section } from "./Section";

export function ProvenancePanel({ provenance }: { provenance: ProvenanceTrail }) {
  const hasBq = provenance.bigquery_rows.length > 0;
  const hasUrls = provenance.external_urls.length > 0;
  if (!hasBq && !hasUrls) return null;

  return (
    <Section
      title="Source provenance"
      subtitle="Every signal in this dossier traces back to one of these rows or URLs"
      right={
        <span className="inline-flex items-center gap-1.5 font-mono uppercase tracking-wider text-[10px]">
          <Link2 size={12} /> {provenance.bigquery_rows.length + provenance.external_urls.length}{" "}
          citations
        </span>
      }
    >
      <div className="grid md:grid-cols-2 gap-5 text-xs">
        {hasBq && (
          <div>
            <div className="flex items-center gap-2 mb-2 font-mono uppercase tracking-wider text-[10px] text-[var(--muted)]">
              <Database size={12} />
              BigQuery rows ({provenance.bigquery_rows.length})
            </div>
            <ul className="space-y-1.5 font-mono text-[11px] text-[var(--foreground)]/80">
              {provenance.bigquery_rows.map((row, i) => (
                <li
                  key={i}
                  className="rounded-sm bg-[var(--surface)] border border-[var(--border)] px-2 py-1.5 break-all"
                  title={row}
                >
                  {row}
                </li>
              ))}
            </ul>
          </div>
        )}
        {hasUrls && (
          <div>
            <div className="flex items-center gap-2 mb-2 font-mono uppercase tracking-wider text-[10px] text-[var(--muted)]">
              <ExternalLink size={12} />
              External sources ({provenance.external_urls.length})
            </div>
            <ul className="space-y-1.5 max-h-72 overflow-auto pr-1">
              {provenance.external_urls.map((entry, i) => (
                <li key={i}>
                  <a
                    href={entry.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block rounded-sm bg-[var(--surface)] border border-[var(--border)] px-2 py-1.5 hover:border-[var(--accent)] hover:text-[var(--accent)]"
                    title={entry.url}
                  >
                    <div className="text-[11px] font-medium leading-tight">
                      {entry.label}
                    </div>
                    <div className="text-[10px] text-[var(--muted)] truncate">
                      {entry.url}
                    </div>
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Section>
  );
}
