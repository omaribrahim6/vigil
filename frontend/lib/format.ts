import type { RiskTier, Severity } from "./types";

export function fmtMoney(n: number | null | undefined, opts?: { compact?: boolean }): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  if (opts?.compact) {
    if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
    if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
    if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  }
  return n.toLocaleString("en-CA", {
    style: "currency",
    currency: "CAD",
    maximumFractionDigits: 0,
  });
}

export function fmtDate(d: string | null | undefined): string {
  if (!d) return "—";
  const date = new Date(d);
  if (Number.isNaN(date.getTime())) return d;
  return date.toLocaleDateString("en-CA", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function tierLabel(t: RiskTier): string {
  switch (t) {
    case "RED":
      return "Critical";
    case "ORANGE":
      return "High";
    case "YELLOW":
      return "Moderate";
    case "GREEN":
      return "Clean";
    default:
      return "Unrated";
  }
}

export function severityLabel(s: Severity | null | undefined): string {
  if (!s) return "—";
  return s.charAt(0) + s.slice(1).toLowerCase();
}
