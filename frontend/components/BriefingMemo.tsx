import { Section } from "./Section";

export function BriefingMemo({ memo }: { memo?: string | null }) {
  if (!memo) return null;
  return (
    <Section
      title="Briefing memo"
      subtitle="Minister-ready summary"
      emphasis
      right={<span className="font-mono uppercase text-[10px]">Claude-authored</span>}
    >
      <p className="font-serif text-base leading-relaxed text-[var(--foreground)]">
        {memo}
      </p>
    </Section>
  );
}
