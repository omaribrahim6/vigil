import Link from "next/link";
import { ChevronRight, Network } from "lucide-react";
import type { RelatedEntity } from "../lib/types";
import { EmptyPanel, Section } from "./Section";

export function RelatedEntities({ related }: { related: RelatedEntity[] }) {
  return (
    <Section
      title="Related entities"
      subtitle="LLM-authored relationships from entity-resolution pipeline"
      right={
        <span className="inline-flex items-center gap-1.5">
          <Network size={12} /> {related.length} {related.length === 1 ? "link" : "links"}
        </span>
      }
    >
      {related.length === 0 ? (
        <EmptyPanel message="No related entities resolved by the goldens pipeline." />
      ) : (
        <ul className="divide-y divide-[var(--border)]">
          {related.slice(0, 12).map((r) => {
            const href = r.related_id ? `/orgs/${r.related_id}` : null;
            const Wrap: React.ElementType = href ? Link : "div";
            return (
              <li key={`${r.related_id ?? ""}-${r.name}`}>
                <Wrap
                  {...(href ? { href } : {})}
                  className="py-3 flex items-start justify-between gap-3 group"
                >
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium leading-tight group-hover:underline">
                      {r.name}
                    </div>
                    {r.relationship && (
                      <div className="text-xs text-[var(--muted)] mt-0.5 font-mono uppercase tracking-wider">
                        {r.relationship}
                      </div>
                    )}
                    {r.reasoning && (
                      <p className="mt-1 text-xs text-[var(--foreground)]/80 leading-snug line-clamp-2">
                        {r.reasoning}
                      </p>
                    )}
                  </div>
                  {href && <ChevronRight size={14} className="text-[var(--muted)] mt-1.5 flex-shrink-0" />}
                </Wrap>
              </li>
            );
          })}
        </ul>
      )}
    </Section>
  );
}
