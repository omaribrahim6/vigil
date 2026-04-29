"use client";

import { useMemo } from "react";
import {
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import type {
  AdverseEvent,
  FundingEvent,
  RemediationEvent,
} from "../lib/types";
import { fmtDate, fmtMoney, severityLabel } from "../lib/format";

type Marker = {
  ts: number;
  band: number;
  amount: number | null;
  label: string;
  detail: string;
  date: string | null;
  kind: "funding-fed" | "funding-ab" | "remediation" | "adverse";
  severity?: string;
  url?: string | null;
  source_name?: string | null;
  is_independent?: boolean;
};

interface Props {
  funding: FundingEvent[];
  adverse: AdverseEvent[];
  remediation?: RemediationEvent[];
  firstAdverse?: string | null;
}

// Three lanes top-down: Federal funding, Provincial (AB) funding, Remediation,
// Adverse. We collapse the two funding sources into a single "Funding" band
// (color-encoded) so the chart stays compact at three rows.
const FUNDING_BAND = 2;
const REMEDIATION_BAND = 1;
const ADVERSE_BAND = 0;

export function Timeline({ funding, adverse, remediation = [], firstAdverse }: Props) {
  const {
    fundingFed,
    fundingAb,
    remediationPoints,
    adversePoints,
    firstAdverseTs,
    hasAny,
    xMin,
    xMax,
  } = useMemo(() => {
    const fundingFed: Marker[] = [];
    const fundingAb: Marker[] = [];
    for (const e of funding) {
      if (!e.date) continue;
      const ts = Date.parse(e.date);
      if (Number.isNaN(ts)) continue;
      const m: Marker = {
        ts,
        band: FUNDING_BAND,
        amount: e.amount,
        label: e.title || e.department_or_program || "Government grant",
        detail: e.department_or_program || "Government",
        date: e.date,
        kind: e.source === "ab" ? "funding-ab" : "funding-fed",
      };
      if (e.source === "ab") fundingAb.push(m);
      else fundingFed.push(m);
    }
    const remPts: Marker[] = [];
    for (const r of remediation) {
      if (!r.date) continue;
      const ts = Date.parse(r.date);
      if (Number.isNaN(ts)) continue;
      remPts.push({
        ts,
        band: REMEDIATION_BAND,
        amount: null,
        label: r.title,
        detail: r.summary || (r.is_independent ? "Independent verification" : "Remediation signal"),
        date: r.date,
        kind: "remediation",
        url: r.url,
        source_name: r.source_name,
        is_independent: r.is_independent,
      });
    }
    const adversePts: Marker[] = [];
    for (const a of adverse) {
      if (!a.date) continue;
      const ts = Date.parse(a.date);
      if (Number.isNaN(ts)) continue;
      adversePts.push({
        ts,
        band: ADVERSE_BAND,
        amount: null,
        label: a.title,
        detail: a.summary || a.category || "",
        date: a.date,
        kind: "adverse",
        severity: a.severity || undefined,
        url: a.url,
      });
    }
    const allTs = [
      ...fundingFed,
      ...fundingAb,
      ...remPts,
      ...adversePts,
    ].map((p) => p.ts);
    if (firstAdverse) {
      const ts = Date.parse(firstAdverse);
      if (!Number.isNaN(ts)) allTs.push(ts);
    }
    const xMin = allTs.length ? Math.min(...allTs) : Date.now() - 5 * 365 * 86400 * 1000;
    const xMax = allTs.length ? Math.max(...allTs) : Date.now();
    const padding = Math.max((xMax - xMin) * 0.05, 30 * 86400 * 1000);
    const firstAdverseTs = firstAdverse ? Date.parse(firstAdverse) : null;
    return {
      fundingFed,
      fundingAb,
      remediationPoints: remPts,
      adversePoints: adversePts,
      firstAdverseTs:
        firstAdverseTs !== null && !Number.isNaN(firstAdverseTs) ? firstAdverseTs : null,
      hasAny:
        fundingFed.length + fundingAb.length + remPts.length + adversePts.length > 0,
      xMin: xMin - padding,
      xMax: xMax + padding,
    };
  }, [funding, adverse, remediation, firstAdverse]);

  if (!hasAny) {
    return (
      <div className="text-sm text-[var(--muted)] italic py-8 text-center">
        No dated funding, remediation, or adverse events to plot.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-5 flex-wrap text-xs text-[var(--muted)]">
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: "var(--funding)" }} />
          Federal funding
        </span>
        {fundingAb.length > 0 && (
          <span className="flex items-center gap-1.5">
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ background: "#0891b2" }}
            />
            Alberta funding
          </span>
        )}
        {remediationPoints.length > 0 && (
          <span className="flex items-center gap-1.5">
            <span
              className="inline-block h-2.5 w-2.5 rotate-45"
              style={{ background: "var(--risk-green)" }}
            />
            Remediation signal
          </span>
        )}
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block h-2.5 w-2.5 rotate-45"
            style={{ background: "var(--adverse)" }}
          />
          Adverse signal
        </span>
        {firstAdverseTs && (
          <span className="ml-auto font-mono uppercase tracking-wider text-[10px]">
            First adverse signal: {fmtDate(firstAdverse)}
          </span>
        )}
      </div>
      <div style={{ width: "100%", height: 260 }}>
        <ResponsiveContainer>
          <ScatterChart margin={{ top: 20, right: 30, bottom: 28, left: 20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis
              type="number"
              dataKey="ts"
              domain={[xMin, xMax]}
              tickFormatter={(v) => new Date(v).getFullYear().toString()}
              stroke="var(--muted)"
              tick={{ fontSize: 11 }}
            />
            <YAxis
              type="number"
              dataKey="band"
              domain={[-0.5, 2.5]}
              ticks={[0, 1, 2]}
              tickFormatter={(v) =>
                v === FUNDING_BAND
                  ? "Funding"
                  : v === REMEDIATION_BAND
                  ? "Remediation"
                  : "Adverse"
              }
              stroke="var(--muted)"
              tick={{ fontSize: 11 }}
              width={88}
            />
            <ZAxis type="number" range={[60, 320]} dataKey="amount" />
            <Tooltip
              cursor={{ stroke: "var(--accent)", strokeDasharray: "3 3" }}
              content={<MarkerTooltip />}
            />
            {firstAdverseTs && (
              <ReferenceLine
                x={firstAdverseTs}
                stroke="var(--adverse)"
                strokeDasharray="4 4"
                label={{
                  value: "First adverse signal",
                  position: "top",
                  fill: "var(--adverse)",
                  fontSize: 10,
                }}
              />
            )}
            <Scatter name="Federal funding" data={fundingFed} fill="var(--funding)" />
            <Scatter name="Alberta funding" data={fundingAb} fill="#0891b2" />
            <Scatter
              name="Remediation"
              data={remediationPoints}
              fill="var(--risk-green)"
              shape="diamond"
            />
            <Scatter
              name="Adverse"
              data={adversePoints}
              fill="var(--adverse)"
              shape="diamond"
            />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function MarkerTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: Marker }> }) {
  if (!active || !payload || !payload.length) return null;
  const m = payload[0].payload;
  const swatch =
    m.kind === "funding-fed"
      ? "var(--funding)"
      : m.kind === "funding-ab"
      ? "#0891b2"
      : m.kind === "remediation"
      ? "var(--risk-green)"
      : "var(--adverse)";
  const tag =
    m.kind === "funding-fed"
      ? "Federal funding"
      : m.kind === "funding-ab"
      ? "Alberta sole-source"
      : m.kind === "remediation"
      ? m.is_independent
        ? "Remediation · independent"
        : "Remediation"
      : `Adverse / ${severityLabel(m.severity as never)}`;
  return (
    <div className="rounded-md border border-[var(--border)] bg-white shadow-lg p-3 max-w-xs text-xs">
      <div className="flex items-center gap-2 mb-1">
        <span
          className="inline-block h-2 w-2 rounded-full"
          style={{ background: swatch }}
        />
        <span className="font-mono uppercase tracking-wider text-[10px] text-[var(--muted)]">
          {tag}
        </span>
        <span className="ml-auto font-mono text-[10px] text-[var(--muted)]">
          {fmtDate(m.date)}
        </span>
      </div>
      <div className="font-semibold text-sm leading-tight">{m.label}</div>
      {m.detail && (
        <div className="mt-1 text-[var(--muted)] leading-snug">{m.detail.slice(0, 220)}</div>
      )}
      {m.amount !== null && m.amount !== undefined && (
        <div className="mt-1.5 font-mono text-sm">{fmtMoney(m.amount)}</div>
      )}
      {m.source_name && (
        <div className="mt-1.5 text-[10px] truncate text-[var(--muted)] font-mono">
          {m.source_name}
        </div>
      )}
      {m.url && (
        <div className="mt-1.5 text-[10px] truncate text-[var(--muted)]">{m.url}</div>
      )}
    </div>
  );
}
