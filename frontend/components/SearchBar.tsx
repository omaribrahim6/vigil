"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Search, Loader2 } from "lucide-react";
import { searchOrgs, screenByName } from "../lib/api";
import type { TopOrgRow } from "../lib/types";
import { fmtMoney } from "../lib/format";
import { RiskBadge } from "./RiskBadge";

export function SearchBar() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<TopOrgRow[]>([]);
  const [searching, setSearching] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (q.trim().length < 2) {
      setResults([]);
      return;
    }
    let cancelled = false;
    const t = setTimeout(async () => {
      setSearching(true);
      try {
        const rows = await searchOrgs(q.trim());
        if (!cancelled) setResults(rows);
      } catch {
        if (!cancelled) setResults([]);
      } finally {
        if (!cancelled) setSearching(false);
      }
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [q]);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  async function liveScreen() {
    if (!q.trim()) return;
    setSubmitting(true);
    try {
      const dossier = await screenByName(q.trim());
      router.push(`/orgs/${encodeURIComponent(dossier.org.id)}`);
    } catch (e) {
      console.error(e);
      setSubmitting(false);
    }
  }

  return (
    <div ref={ref} className="relative">
      <div className="flex items-center gap-3 rounded-md border border-[var(--border)] bg-white px-4 py-3 shadow-sm focus-within:border-[var(--accent)]">
        <Search size={18} className="text-[var(--muted)]" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => setOpen(true)}
          placeholder="Search any organization receiving Canadian government funding…"
          className="flex-1 bg-transparent outline-none text-base placeholder:text-[var(--muted)]"
          onKeyDown={(e) => {
            if (e.key === "Enter") liveScreen();
          }}
        />
        {searching && <Loader2 size={16} className="animate-spin text-[var(--muted)]" />}
        <button
          onClick={liveScreen}
          disabled={!q.trim() || submitting}
          className="rounded-sm bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-xs font-semibold uppercase tracking-wider px-3 py-1.5 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
        >
          {submitting ? (
            <>
              <Loader2 size={14} className="animate-spin" /> Screening
            </>
          ) : (
            "Run live screen"
          )}
        </button>
      </div>
      {open && q.trim().length >= 2 && (
        <div className="absolute z-30 mt-2 w-full rounded-md border border-[var(--border)] bg-white shadow-lg max-h-96 overflow-y-auto">
          {results.length === 0 && !searching && (
            <div className="px-4 py-6 text-sm text-[var(--muted)]">
              No matches in goldens — pressing <span className="font-mono">Run live screen</span> still
              checks OpenSanctions, news, and forensic sources.
            </div>
          )}
          {results.map((row) => (
            <a
              key={row.id}
              href={`/orgs/${row.id}`}
              className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-[var(--background)] border-b border-[var(--border)] last:border-b-0"
            >
              <div className="min-w-0">
                <div className="font-medium text-sm truncate">{row.canonical_name}</div>
                <div className="text-xs text-[var(--muted)] mt-0.5 flex gap-3">
                  {row.province && <span>{row.province}</span>}
                  <span>{fmtMoney(row.fed_total, { compact: true })} federal</span>
                </div>
              </div>
              <RiskBadge tier={row.risk_tier} score={row.risk_score} size="sm" />
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
