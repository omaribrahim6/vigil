import Link from "next/link";
import { ChevronRight, AlertOctagon } from "lucide-react";
import type { TopOrgRow } from "../lib/types";
import { fmtMoney } from "../lib/format";
import { RiskBadge } from "./RiskBadge";

interface Props {
  rows: TopOrgRow[];
}

const TIER_RANK = {
  RED: 4,
  ORANGE: 3,
  YELLOW: 2,
  GREEN: 1,
  UNRATED: 0,
} as const;

export function FeaturedScreenings({ rows }: Props) {
  const screened = rows
    .filter((r) => r.risk_tier !== "UNRATED")
    .sort((a, b) => {
      const cmp = TIER_RANK[b.risk_tier] - TIER_RANK[a.risk_tier];
      if (cmp !== 0) return cmp;
      return (b.risk_score ?? 0) - (a.risk_score ?? 0);
    })
    .slice(0, 6);

  if (screened.length === 0) return null;

  return (
    <section>
      <div className="flex items-center gap-2 mb-3">
        <AlertOctagon size={16} className="text-[var(--accent)]" />
        <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--accent)]">
          Featured screenings
        </h2>
        <span className="text-xs text-[var(--muted)] ml-2">
          Pre-screened with all signal layers ·{" "}
          <span className="font-mono">click any card to open the dossier</span>
        </span>
      </div>
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {screened.map((r) => (
          <Link
            key={r.id}
            href={`/orgs/${r.id}`}
            className="group rounded-md border border-[var(--border)] bg-white p-4 hover:border-[var(--accent)] hover:shadow-sm transition-all"
          >
            <div className="flex items-start justify-between gap-2 mb-2">
              <RiskBadge tier={r.risk_tier} score={r.risk_score} size="sm" />
              <ChevronRight
                size={14}
                className="text-[var(--muted)] group-hover:text-[var(--accent)] mt-0.5 flex-shrink-0"
              />
            </div>
            <div className="font-semibold text-sm leading-tight group-hover:underline decoration-[var(--accent)]">
              {r.canonical_name}
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-[var(--muted)]">
                  Federal
                </div>
                <div className="font-mono tabular-nums">
                  {fmtMoney(r.fed_total, { compact: true })}
                </div>
              </div>
              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-[var(--muted)]">
                  Top flag
                </div>
                <div className="text-[var(--foreground)]/90 truncate">
                  {r.top_flag || "—"}
                </div>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}
