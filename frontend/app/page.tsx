import { Suspense } from "react";
import { ShieldAlert, Database, Activity } from "lucide-react";
import { getPortfolioStats, getTopOrgs } from "../lib/api";
import { OrgTable } from "../components/OrgTable";
import { SearchBar } from "../components/SearchBar";
import { StatTile } from "../components/StatTile";
import { fmtMoney } from "../lib/format";

async function PortfolioBanner() {
  const stats = await getPortfolioStats().catch(() => null);
  if (!stats) {
    return (
      <div className="rounded-md border border-[var(--accent)] bg-[var(--accent)] text-white px-6 py-5">
        <div className="text-xs uppercase tracking-[0.2em] opacity-70 font-mono mb-1">
          Portfolio screening
        </div>
        <div className="text-lg leading-snug">
          Run <span className="font-mono">python -m scripts.precache</span> to compute the
          portfolio headline number across the demo orgs.
        </div>
      </div>
    );
  }
  return (
    <div className="rounded-md border border-[var(--accent)] bg-[var(--accent)] text-white px-6 py-5">
      <div className="text-xs uppercase tracking-[0.2em] opacity-70 font-mono mb-1">
        Portfolio headline
      </div>
      <div className="text-2xl leading-snug font-semibold">{stats.headline}</div>
      <div className="mt-3 grid sm:grid-cols-4 gap-3 text-sm">
        <PortfolioStat
          label="Orgs screened"
          value={stats.total_orgs_screened.toString()}
        />
        <PortfolioStat
          label="Flagged"
          value={`${stats.flagged_org_count} / ${stats.total_orgs_screened}`}
        />
        <PortfolioStat
          label="Flagged exposure"
          value={fmtMoney(stats.flagged_total_funding, { compact: true })}
        />
        <PortfolioStat
          label="Total exposure"
          value={fmtMoney(stats.portfolio_total_funding, { compact: true })}
        />
      </div>
    </div>
  );
}

function PortfolioStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] font-mono uppercase tracking-wider opacity-60">{label}</div>
      <div className="text-lg font-semibold tabular-nums">{value}</div>
    </div>
  );
}

async function TopOrgs() {
  let rows = [] as Awaited<ReturnType<typeof getTopOrgs>>;
  try {
    rows = await getTopOrgs(200);
  } catch (e) {
    console.error("getTopOrgs failed", e);
  }
  return <OrgTable rows={rows} />;
}

export default function Home() {
  return (
    <div className="space-y-8">
      <section>
        <div className="flex items-start gap-2 mb-4">
          <ShieldAlert size={18} className="text-[var(--accent)] mt-1" />
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              Adverse-media + forensic-signals screening
            </h1>
            <p className="text-sm text-[var(--muted)] mt-1 max-w-2xl">
              For any organization receiving Canadian government funding, Vigil checks sanctions
              lists, court records, recent media, and pre-computed accountability signals — and
              shows it on a counterfactual funding-vs-adverse-event timeline.
            </p>
          </div>
        </div>
        <SearchBar />
      </section>

      <section>
        <Suspense
          fallback={
            <div className="h-28 rounded-md border border-[var(--border)] bg-white animate-pulse" />
          }
        >
          <PortfolioBanner />
        </Suspense>
      </section>

      <section className="grid sm:grid-cols-3 gap-4">
        <StatTile
          label="Funding sources"
          value={
            <span className="flex items-center gap-2">
              <Database size={20} className="text-[var(--accent)]" />4 schemas
            </span>
          }
          hint="Federal G&C · CRA T3010 · Alberta · Goldens"
        />
        <StatTile
          label="External signal sources"
          value={
            <span className="flex items-center gap-2">
              <Activity size={20} className="text-[var(--accent)]" />4 live
            </span>
          }
          hint="OpenSanctions · CanLII · Tavily · GDELT v2"
        />
        <StatTile
          label="Forensic-layer tables"
          value={<span className="text-[var(--accent)]">5 pre-computed</span>}
          hint="loop_universe · t3010_impossibilities · overhead · sole-source · directors"
        />
      </section>

      <section>
        <Suspense
          fallback={
            <div className="h-96 rounded-md border border-[var(--border)] bg-white animate-pulse" />
          }
        >
          <TopOrgs />
        </Suspense>
      </section>
    </div>
  );
}
