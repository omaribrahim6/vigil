import { Ban, ExternalLink } from "lucide-react";
import type { SanctionsHit } from "../lib/types";
import { EmptyPanel, Section } from "./Section";

export function SanctionsPanel({
  hits,
  configured,
}: {
  hits: SanctionsHit[];
  configured: boolean;
}) {
  return (
    <Section
      title="Sanctions / debarment"
      subtitle="OpenSanctions — UN, OFAC, EU, Interpol, federal debarment"
      right={
        <span className="inline-flex items-center gap-1.5">
          <Ban size={12} /> {hits.length} {hits.length === 1 ? "match" : "matches"}
        </span>
      }
    >
      {!configured ? (
        <EmptyPanel message="OpenSanctions API key not configured." />
      ) : hits.length === 0 ? (
        <EmptyPanel message="No sanctions or debarment matches across 332 government source lists." />
      ) : (
        <ul className="divide-y divide-[var(--border)]">
          {hits.map((h, i) => (
            <li key={i} className="py-3 flex items-start gap-3">
              <div className="flex-shrink-0 mt-1 inline-flex items-center justify-center h-6 w-6 rounded-sm bg-[var(--risk-red-bg)] text-[var(--risk-red)]">
                <Ban size={12} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium leading-tight">{h.list_name}</div>
                <div className="text-xs text-[var(--muted)] mt-0.5 flex flex-wrap gap-x-3 gap-y-1">
                  <span className="font-mono">match {h.score.toFixed(2)}</span>
                  <span>{h.schema}</span>
                  {h.countries.length > 0 && (
                    <span>{h.countries.slice(0, 3).join(" · ").toUpperCase()}</span>
                  )}
                </div>
              </div>
              {h.entity_url && (
                <a
                  href={h.entity_url}
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
