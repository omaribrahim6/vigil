import type { ReactNode } from "react";

export function Section({
  title,
  subtitle,
  right,
  children,
  emphasis,
}: {
  title: string;
  subtitle?: string;
  right?: ReactNode;
  children: ReactNode;
  emphasis?: boolean;
}) {
  return (
    <section
      className={`rounded-md border bg-white ${
        emphasis ? "border-[var(--accent)]" : "border-[var(--border)]"
      }`}
    >
      <header className="flex items-start justify-between gap-3 px-5 py-3.5 border-b border-[var(--border)]">
        <div>
          <h3 className="text-sm font-semibold tracking-wide uppercase text-[var(--accent)]">
            {title}
          </h3>
          {subtitle && (
            <p className="mt-0.5 text-xs text-[var(--muted)]">{subtitle}</p>
          )}
        </div>
        {right && <div className="text-xs text-[var(--muted)]">{right}</div>}
      </header>
      <div className="p-5">{children}</div>
    </section>
  );
}

export function EmptyPanel({ message }: { message: string }) {
  return (
    <div className="text-sm text-[var(--muted)] italic">{message}</div>
  );
}
