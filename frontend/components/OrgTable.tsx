"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, Play } from "lucide-react";
import type { RiskTier, TopOrgRow } from "../lib/types";
import { fmtMoney } from "../lib/format";
import { RiskBadge } from "./RiskBadge";

type SortKey = "risk" | "fed" | "name";

const TIER_RANK: Record<RiskTier, number> = {
  RED: 4,
  ORANGE: 3,
  YELLOW: 2,
  GREEN: 1,
  UNRATED: 0,
};

function SortIcon({ active, dir }: { active: boolean; dir: "asc" | "desc" }) {
  if (!active) return <ArrowUpDown size={12} className="opacity-40" />;
  return dir === "asc" ? <ArrowUp size={12} /> : <ArrowDown size={12} />;
}

export function OrgTable({ rows }: { rows: TopOrgRow[] }) {
  const [sort, setSort] = useState<{ key: SortKey; dir: "asc" | "desc" }>({
    key: "risk",
    dir: "desc",
  });
  const [tierFilter, setTierFilter] = useState<RiskTier | "ALL">("ALL");

  const sorted = useMemo(() => {
    const out = rows.filter((r) => tierFilter === "ALL" || r.risk_tier === tierFilter);
    out.sort((a, b) => {
      let cmp = 0;
      if (sort.key === "risk") {
        cmp =
          TIER_RANK[a.risk_tier] - TIER_RANK[b.risk_tier] ||
          (a.risk_score ?? -1) - (b.risk_score ?? -1);
      } else if (sort.key === "fed") {
        cmp = (a.fed_total ?? 0) - (b.fed_total ?? 0);
      } else {
        cmp = a.canonical_name.localeCompare(b.canonical_name);
      }
      return sort.dir === "asc" ? cmp : -cmp;
    });
    return out;
  }, [rows, sort, tierFilter]);

  function toggleSort(key: SortKey) {
    setSort((s) =>
      s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "desc" }
    );
  }

  return (
    <div className="rounded-md border border-[var(--border)] bg-white">
      <div className="flex items-center gap-2 px-5 py-3 border-b border-[var(--border)]">
        <h3 className="text-sm font-semibold tracking-wide uppercase text-[var(--accent)] mr-auto">
          Top federal-funded organizations
        </h3>
        <span className="text-xs text-[var(--muted)] mr-2">filter:</span>
        {(["ALL", "RED", "ORANGE", "YELLOW", "GREEN", "UNRATED"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTierFilter(t)}
            className={`text-xs font-mono uppercase tracking-wider px-2 py-1 rounded-sm border transition-colors ${
              tierFilter === t
                ? "bg-[var(--accent)] border-[var(--accent)] text-white"
                : "border-[var(--border)] text-[var(--muted)] hover:text-[var(--accent)]"
            }`}
          >
            {t}
          </button>
        ))}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wider text-[var(--muted)] border-b border-[var(--border)] bg-[var(--background)]">
              <th className="px-5 py-2.5 font-medium">
                <button onClick={() => toggleSort("name")} className="flex items-center gap-1.5">
                  Organization
                  <SortIcon active={sort.key === "name"} dir={sort.dir} />
                </button>
              </th>
              <th className="px-5 py-2.5 font-medium">Province</th>
              <th className="px-5 py-2.5 font-medium text-right">
                <button onClick={() => toggleSort("fed")} className="flex items-center gap-1.5 ml-auto">
                  Federal funding
                  <SortIcon active={sort.key === "fed"} dir={sort.dir} />
                </button>
              </th>
              <th className="px-5 py-2.5 font-medium">
                <button onClick={() => toggleSort("risk")} className="flex items-center gap-1.5">
                  Risk
                  <SortIcon active={sort.key === "risk"} dir={sort.dir} />
                </button>
              </th>
              <th className="px-5 py-2.5 font-medium">Top flag</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => {
              const unrated = row.risk_tier === "UNRATED";
              const href = unrated
                ? `/orgs/${encodeURIComponent(row.id)}?name=${encodeURIComponent(row.canonical_name)}`
                : `/orgs/${encodeURIComponent(row.id)}`;
              return (
                <tr
                  key={row.id}
                  className="border-b border-[var(--border)] last:border-b-0 hover:bg-[var(--background)]"
                >
                  <td className="px-5 py-3">
                    <Link
                      href={href}
                      className="font-medium hover:underline decoration-[var(--accent)]"
                    >
                      {row.canonical_name}
                    </Link>
                    {row.cra_designation && (
                      <span className="ml-2 text-[10px] font-mono uppercase tracking-wider text-[var(--muted)]">
                        CRA-{row.cra_designation}
                      </span>
                    )}
                  </td>
                  <td className="px-5 py-3 text-[var(--muted)]">{row.province ?? "—"}</td>
                  <td className="px-5 py-3 text-right font-mono tabular-nums">
                    {fmtMoney(row.fed_total, { compact: true })}
                  </td>
                  <td className="px-5 py-3">
                    {unrated ? (
                      <Link
                        href={href}
                        className="inline-flex items-center gap-1.5 text-xs font-mono uppercase tracking-wider px-2 py-1 rounded-sm border border-[var(--border)] text-[var(--accent)] hover:bg-[var(--accent)] hover:!text-white focus-visible:bg-[var(--accent)] focus-visible:!text-white transition-colors"
                      >
                        <Play size={11} fill="currentColor" /> Screen now
                      </Link>
                    ) : (
                      <RiskBadge tier={row.risk_tier} score={row.risk_score} size="sm" />
                    )}
                  </td>
                  <td className="px-5 py-3 text-[var(--muted)]">{row.top_flag ?? "—"}</td>
                </tr>
              );
            })}
            {sorted.length === 0 && (
              <tr>
                <td colSpan={5} className="px-5 py-12 text-center text-sm text-[var(--muted)]">
                  No organizations match this filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
