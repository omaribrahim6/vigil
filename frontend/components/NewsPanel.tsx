import { ExternalLink, Newspaper } from "lucide-react";
import type { NewsArticle, Severity } from "../lib/types";
import { fmtDate, severityLabel } from "../lib/format";
import { EmptyPanel, Section } from "./Section";

const SEVERITY_STYLE: Record<Severity, { bg: string; fg: string }> = {
  CRITICAL: { bg: "var(--risk-red-bg)", fg: "var(--risk-red)" },
  HIGH: { bg: "var(--risk-orange-bg)", fg: "var(--risk-orange)" },
  MEDIUM: { bg: "var(--risk-yellow-bg)", fg: "var(--risk-yellow)" },
  NOISE: { bg: "var(--risk-grey-bg)", fg: "var(--risk-grey)" },
};

export function NewsPanel({
  articles,
  configured,
}: {
  articles: NewsArticle[];
  configured: boolean;
}) {
  const flagged = articles.filter((a) => a.severity && a.severity !== "NOISE");
  const noise = articles.filter((a) => !a.severity || a.severity === "NOISE");

  return (
    <Section
      title="Adverse media"
      subtitle="Tavily search · Claude-classified · Canadian-bias"
      right={
        <span className="inline-flex items-center gap-1.5">
          <Newspaper size={12} /> {flagged.length} flagged · {articles.length} total
        </span>
      }
    >
      {!configured ? (
        <EmptyPanel message="Tavily API key not configured." />
      ) : articles.length === 0 ? (
        <EmptyPanel message="No adverse-media hits returned for this entity." />
      ) : (
        <div className="space-y-4">
          <ul className="divide-y divide-[var(--border)]">
            {flagged.map((a) => (
              <li key={a.url} className="py-3 flex items-start gap-3">
                {a.severity && (
                  <span
                    className="flex-shrink-0 mt-1 px-1.5 py-0.5 rounded-sm font-mono text-[10px] uppercase tracking-wider"
                    style={{
                      background: SEVERITY_STYLE[a.severity].bg,
                      color: SEVERITY_STYLE[a.severity].fg,
                    }}
                  >
                    {severityLabel(a.severity)}
                  </span>
                )}
                <div className="min-w-0 flex-1">
                  <a
                    href={a.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm font-medium hover:underline leading-tight"
                  >
                    {a.title}
                  </a>
                  <div className="text-xs text-[var(--muted)] mt-0.5 flex flex-wrap gap-x-3">
                    {a.source_name && <span className="font-mono">{a.source_name}</span>}
                    {a.published_at && <span>{fmtDate(a.published_at)}</span>}
                    {a.category && <span className="italic">{a.category}</span>}
                  </div>
                  {a.summary && (
                    <p className="mt-1 text-xs text-[var(--foreground)]/80 leading-snug line-clamp-3">
                      {a.summary}
                    </p>
                  )}
                </div>
                <a
                  href={a.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex-shrink-0 mt-1 text-xs text-[var(--accent)] hover:underline inline-flex items-center gap-1"
                >
                  Open <ExternalLink size={12} />
                </a>
              </li>
            ))}
          </ul>
          {noise.length > 0 && (
            <details className="text-xs text-[var(--muted)]">
              <summary className="cursor-pointer">
                {noise.length} noise / unrelated result(s) suppressed
              </summary>
              <ul className="mt-2 space-y-1.5 pl-3 border-l border-[var(--border)]">
                {noise.map((a) => (
                  <li key={a.url}>
                    <a href={a.url} target="_blank" rel="noopener noreferrer" className="hover:underline">
                      {a.title}
                    </a>
                    {a.source_name && <span className="font-mono"> · {a.source_name}</span>}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </Section>
  );
}
