import type { ReactNode } from "react";

export function StatTile({
  label,
  value,
  hint,
  emphasis,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  emphasis?: "red" | "orange" | "accent";
}) {
  const valueColor =
    emphasis === "red"
      ? "text-[var(--risk-red)]"
      : emphasis === "orange"
      ? "text-[var(--risk-orange)]"
      : emphasis === "accent"
      ? "text-[var(--accent)]"
      : "text-[var(--foreground)]";
  return (
    <div className="rounded-md border border-[var(--border)] bg-white px-5 py-4">
      <div className="text-xs font-mono uppercase tracking-wider text-[var(--muted)]">
        {label}
      </div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${valueColor}`}>{value}</div>
      {hint && <div className="mt-1 text-xs text-[var(--muted)]">{hint}</div>}
    </div>
  );
}
