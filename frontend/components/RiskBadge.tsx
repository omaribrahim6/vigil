import type { RiskTier } from "../lib/types";
import { tierLabel } from "../lib/format";

const STYLES: Record<RiskTier, { bg: string; fg: string }> = {
  RED: { bg: "var(--risk-red-bg)", fg: "var(--risk-red)" },
  ORANGE: { bg: "var(--risk-orange-bg)", fg: "var(--risk-orange)" },
  YELLOW: { bg: "var(--risk-yellow-bg)", fg: "var(--risk-yellow)" },
  GREEN: { bg: "var(--risk-green-bg)", fg: "var(--risk-green)" },
  UNRATED: { bg: "var(--risk-grey-bg)", fg: "var(--risk-grey)" },
};

interface Props {
  tier: RiskTier;
  score?: number | null;
  size?: "sm" | "md" | "lg";
  showScore?: boolean;
}

export function RiskBadge({ tier, score, size = "md", showScore = true }: Props) {
  const s = STYLES[tier];
  const padding =
    size === "lg" ? "px-3 py-1.5 text-sm" : size === "sm" ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-1 text-xs";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-sm font-mono uppercase tracking-wider font-semibold ${padding}`}
      style={{ background: s.bg, color: s.fg }}
    >
      <span>{tierLabel(tier)}</span>
      {showScore && score !== null && score !== undefined && (
        <span className="opacity-70 font-normal">{score}</span>
      )}
    </span>
  );
}
