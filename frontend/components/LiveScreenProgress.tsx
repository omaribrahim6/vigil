"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  CheckCircle2,
  Database,
  FileSearch,
  Gavel,
  Newspaper,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { API_BASE_URL } from "../lib/api";
import { Section } from "./Section";

type Stage = {
  id: string;
  label: string;
  hint: string;
  Icon: typeof Database;
  /** Approx seconds until this stage is "done" (purely UX — backend runs in
   *  parallel). Stages light up sequentially while the real screen runs. */
  doneAt: number;
};

const STAGES: Stage[] = [
  {
    id: "bq",
    label: "BigQuery profile",
    hint: "entity_golden_records · fed.grants_contributions",
    Icon: Database,
    doneAt: 4,
  },
  {
    id: "sanctions",
    label: "OpenSanctions",
    hint: "UN · OFAC · EU · Interpol · federal debarment",
    Icon: ShieldAlert,
    doneAt: 8,
  },
  {
    id: "news",
    label: "Tavily adverse + remediation",
    hint: "Canadian-bias · two queries · raw content",
    Icon: Newspaper,
    doneAt: 22,
  },
  {
    id: "court",
    label: "CanLII / forensic signals",
    hint: "court records + cra.loop_universe + ab.ab_sole_source",
    Icon: Gavel,
    doneAt: 26,
  },
  {
    id: "claude",
    label: "Claude classification",
    hint: "severity · category · is_remediation · event_date",
    Icon: Sparkles,
    doneAt: 38,
  },
  {
    id: "actions",
    label: "Action items + briefing memo",
    hint: "prescriptive next-steps with provenance",
    Icon: FileSearch,
    doneAt: 50,
  },
];

export function LiveScreenProgress({
  orgId,
  orgName,
}: {
  orgId?: string;
  orgName?: string;
}) {
  const router = useRouter();
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!orgId && !orgName) return;
    const url = orgId
      ? `${API_BASE_URL}/api/orgs/${encodeURIComponent(orgId)}/screen`
      : `${API_BASE_URL}/api/screen/by-name`;
    const init: RequestInit = orgId
      ? { method: "POST" }
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: orgName }),
        };

    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(url, init);
        if (!res.ok) {
          const text = await res.text();
          throw new Error(`${res.status}: ${text || res.statusText}`);
        }
        const dossier = await res.json();
        if (cancelled) return;
        setDone(true);
        setTimeout(() => {
          const targetId = dossier?.org?.id || orgId;
          if (targetId) {
            router.push(`/orgs/${encodeURIComponent(targetId)}`);
            router.refresh();
          }
        }, 600);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [orgId, orgName, router]);

  useEffect(() => {
    if (done || error) return;
    const t = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(t);
  }, [done, error]);

  return (
    <div className="space-y-6">
      <header className="rounded-md border border-[var(--accent)] bg-white px-6 py-5">
        <div className="flex items-center gap-3 text-xs uppercase tracking-[0.2em] text-[var(--accent)] font-mono">
          <span className="relative inline-flex h-2.5 w-2.5">
            <span className="absolute inset-0 inline-flex h-full w-full animate-ping rounded-full bg-[var(--accent)] opacity-50"></span>
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-[var(--accent)]"></span>
          </span>
          {done ? "Screen complete" : "Live screening"}
        </div>
        <h1 className="mt-1.5 text-2xl font-semibold tracking-tight">
          {orgName || orgId}
        </h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Running the full Vigil pipeline — sanctions, court records, adverse media,
          remediation signals, forensic joins, and Claude-authored briefing/actions.
        </p>
      </header>

      <Section
        title="Pipeline progress"
        subtitle={`${elapsed}s elapsed · expected ~30-60s`}
        emphasis
      >
        <ol className="space-y-2.5">
          {STAGES.map((s, i) => {
            const stageDone = elapsed >= s.doneAt || done;
            const active =
              !stageDone &&
              (i === 0 || elapsed >= STAGES[i - 1].doneAt);
            const Icon = s.Icon;
            return (
              <li
                key={s.id}
                className={`flex items-start gap-3 rounded-md border px-3.5 py-2.5 transition-colors ${
                  stageDone
                    ? "border-[var(--risk-green)] bg-[var(--risk-green-bg)]/40"
                    : active
                    ? "border-[var(--accent)] bg-[var(--accent)]/5"
                    : "border-[var(--border)] bg-white"
                }`}
              >
                <span
                  className={`mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full ${
                    stageDone
                      ? "bg-[var(--risk-green)] text-white"
                      : active
                      ? "bg-[var(--accent)] text-white"
                      : "bg-[var(--background)] text-[var(--muted)]"
                  }`}
                >
                  {stageDone ? (
                    <CheckCircle2 size={14} />
                  ) : (
                    <Icon
                      size={14}
                      className={active ? "animate-pulse" : ""}
                    />
                  )}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm">{s.label}</span>
                    {active && (
                      <span className="text-[10px] font-mono uppercase tracking-wider text-[var(--accent)]">
                        running…
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-[var(--muted)] font-mono mt-0.5">
                    {s.hint}
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
      </Section>

      {error && (
        <div className="rounded-md border border-[var(--risk-red)] bg-[var(--risk-red-bg)] px-4 py-3 text-sm flex items-start gap-3">
          <AlertCircle
            size={16}
            className="mt-0.5 flex-shrink-0 text-[var(--risk-red)]"
          />
          <div>
            <div className="font-semibold text-[var(--risk-red)]">
              Screening failed
            </div>
            <div className="mt-0.5 text-xs font-mono break-all">{error}</div>
          </div>
        </div>
      )}
    </div>
  );
}
