import {
  AlertOctagon,
  Calendar,
  CircleCheck,
  Eye,
  ListChecks,
} from "lucide-react";
import type { ActionItem } from "../lib/types";
import { Section } from "./Section";

const URGENCY_STYLE: Record<
  ActionItem["urgency"],
  { bg: string; fg: string; label: string; Icon: typeof AlertOctagon }
> = {
  immediate: {
    bg: "var(--risk-red-bg)",
    fg: "var(--risk-red)",
    label: "Immediate",
    Icon: AlertOctagon,
  },
  scheduled: {
    bg: "var(--risk-orange-bg)",
    fg: "var(--risk-orange)",
    label: "Scheduled",
    Icon: Calendar,
  },
  monitor: {
    bg: "var(--risk-yellow-bg)",
    fg: "var(--risk-yellow)",
    label: "Monitor",
    Icon: Eye,
  },
  none: {
    bg: "var(--risk-green-bg)",
    fg: "var(--risk-green)",
    label: "Clear",
    Icon: CircleCheck,
  },
};

export function ActionItems({ actions }: { actions: ActionItem[] }) {
  if (!actions || actions.length === 0) return null;

  // Sort by urgency: immediate first, then scheduled, monitor, none
  const order = { immediate: 0, scheduled: 1, monitor: 2, none: 3 } as const;
  const sorted = [...actions].sort((a, b) => order[a.urgency] - order[b.urgency]);

  return (
    <Section
      title="What should the funder do"
      subtitle="Prescriptive next-steps generated from this dossier"
      emphasis
      right={
        <span className="inline-flex items-center gap-1.5 font-mono uppercase tracking-wider text-[10px]">
          <ListChecks size={12} /> {actions.length} {actions.length === 1 ? "action" : "actions"}
        </span>
      }
    >
      <ol className="space-y-3">
        {sorted.map((a, i) => {
          const s = URGENCY_STYLE[a.urgency];
          const Icon = s.Icon;
          return (
            <li
              key={i}
              className="flex items-start gap-4 rounded-md border-l-4 px-4 py-3"
              style={{ borderLeftColor: s.fg, background: `${s.bg}55` }}
            >
              <span
                className="flex-shrink-0 mt-0.5 inline-flex items-center justify-center h-8 w-8 rounded-full"
                style={{ background: s.bg, color: s.fg }}
              >
                <Icon size={16} />
              </span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className="font-mono text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-sm"
                    style={{ background: s.bg, color: s.fg }}
                  >
                    {s.label}
                  </span>
                  <span className="text-[10px] text-[var(--muted)] font-mono">
                    Action {i + 1} / {sorted.length}
                  </span>
                </div>
                <h4 className="font-semibold text-base leading-tight">{a.title}</h4>
                <p className="mt-1 text-sm text-[var(--foreground)]/85 leading-snug">
                  {a.rationale}
                </p>
                {a.evidence.length > 0 && (
                  <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px] text-[var(--muted)] font-mono">
                    <span className="uppercase tracking-wider">Evidence:</span>
                    {a.evidence.map((e, j) => {
                      const isUrl = /^https?:\/\//.test(e);
                      const label = isUrl
                        ? e.replace(/^https?:\/\/(www\.)?/, "").slice(0, 50)
                        : e.length > 60
                        ? e.slice(0, 60) + "…"
                        : e;
                      return isUrl ? (
                        <a
                          key={j}
                          href={e}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="px-1.5 py-0.5 rounded-sm bg-white border border-[var(--border)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
                        >
                          {label}
                        </a>
                      ) : (
                        <span
                          key={j}
                          className="px-1.5 py-0.5 rounded-sm bg-white border border-[var(--border)]"
                        >
                          {label}
                        </span>
                      );
                    })}
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </Section>
  );
}
