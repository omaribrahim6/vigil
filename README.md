# Vigil

**Adverse-media + forensic-signals screening for Canadian government-funding recipients.**
Built for **Agency 2026 Ottawa Hackathon — Challenge #10**, April 29 2026.

> Type any organization receiving Canadian government funding. In ~8 seconds, Vigil
> tells you (a) whether to disburse, (b) what to do if not, and (c) shows the
> primary-source citation behind every flag.

---

## The single thing it produces

For each organization screened, Vigil emits an **action list** — the prescriptive
"what should the funder do" answer:

- `IMMEDIATE` — Suspend disbursements; refer to RCMP; flag as ineligible.
- `SCHEDULED` — Open enhanced due-diligence; request CRA records; review historical grants.
- `MONITOR` — Add to watchlist; verify next reporting period.
- `CLEAR` — No concerning signals; proceed.

Every action carries its **rationale** and **evidence** (linkable to the underlying
BigQuery row or external source URL).

The portfolio dashboard rolls these up into a single headline:

> **3 immediate actions outstanding across 1 flagged organization in the screened portfolio.**

---

## How it works

For any org, Vigil:

1. Loads the **funding profile** from BigQuery — the entity-resolution gold records
   already produced by the hackathon repo (`general.entity_golden_records`,
   `fed.grants_contributions`, `cra.cra_identification`, `ab.ab_payments`).
2. Runs **external adverse-signal sweeps** in parallel:
   - **OpenSanctions** — UN, OFAC, EU, Interpol, federal debarment.
   - **CanLII** — Canadian court decisions (degrades gracefully without an API key).
   - **Tavily** — Canadian-source-biased news with raw-content extraction.
   - **GDELT v2** (free BigQuery public dataset) — historical adverse-event frequency
     for the "first adverse signal" annotation on the timeline.
3. Layers in **pre-computed forensic signals** from the agency-26-hackathon
   accountability pipelines (this is the differentiator — Vigil reads the books,
   not just the news):
   - `cra.loop_universe` — circular-gifting risk score (Tarjan SCC + 2–6-hop cycle detection).
   - `cra.t3010_impossibilities` — T3010 form-arithmetic violations across 10 rule types.
   - `cra.overhead_by_charity` — high-overhead pass-through indicator.
   - `ab.ab_sole_source` — non-competitive Alberta contracts.
   - `cra.cra_directors` — shared-director graph (2.87M-row director registry).
4. Asks **Claude (Bedrock Sonnet 4.5)** to classify each adverse hit
   (`CRITICAL/HIGH/MEDIUM/NOISE`) and author both a 4-sentence Minister-ready
   briefing memo and the prescriptive action list.
5. Computes a 0–100 **risk score** (graceful degradation: each signal is
   independently optional; missing signal = 0 contribution).
6. Materializes a **provenance trail** of every BigQuery row and external URL
   that contributed to the dossier.
7. Caches everything to disk so the demo runs offline if Wi-Fi dies.

---

## Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3.11 + FastAPI + `google-cloud-bigquery` + `anthropic` (Bedrock) + `httpx` |
| Frontend | Next.js 16 (App Router) + Tailwind 4 + Recharts + lucide-react |
| LLM | Claude Sonnet 4.5 via AWS Bedrock (`us.anthropic.claude-sonnet-4-5-20250929-v1:0`) |
| Data | BigQuery (`agency2026ot-data-1776775157`) + GDELT public dataset (`gdelt-bq.gdeltv2.gkg_partitioned`) |
| External | OpenSanctions, CanLII, Tavily |

---

## Quick start

```powershell
# 1. Auth to BigQuery
gcloud auth application-default login

# 2. Configure
copy .env.example .env
# … fill in AWS_BEARER_TOKEN_BEDROCK, OPENSANCTIONS_API_KEY, TAVILY_API_KEY (CANLII optional)

# 3. Backend
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000

# 4. Frontend (new terminal)
cd frontend
npm install --legacy-peer-deps
npm run dev

# 5. Pre-cache the demo dossiers (new terminal, ~4 minutes)
cd backend
.venv\Scripts\python.exe -m scripts.precache
```

Open http://localhost:3000.

---

## Demo orgs (pre-cached)

| Org | Story |
|-----|-------|
| **Canada Charity Partners** (id `50517`) | The "system catches non-headline cases" win. CRA revoked status Feb 2026; **YELLOW 32**, 4 prescribed actions including *"Suspend disbursements"* and *"Initiate grant recovery process"*. |
| **WE Charity Foundation** (id `42406`) | $543M federal exposure across the WE entities. Shows the timeline + briefing for the largest funded entity. |
| **WE Charity** (id `72807`) | Network-propagation partner of the Foundation. |
| **United Way of Greater Toronto** (id `22616`) | Forensic kill-shot — pre-computed circular-gifting score 21/30 + 6-cluster shared-director graph. |
| **GC Strategies / Dalian / Coradix / McKinsey / AtkinsRéalis** (adhoc) | Live-search demo — ArriveCAN-cluster + procurement-misconduct stories beyond the goldens. |

---

## Mentor-driven design

> *"Data provided is just a starting point — use external sources smartly. The single
> thing that comes out of all the work has to be clear. Surface data, then action items.
> Everything must be traceable back to a row or a source — no assumptions without proof."*

Vigil maps that 1:1 onto the dossier panels:

- **External sweeps** (OpenSanctions / Tavily / CanLII / GDELT) — take the BQ data
  beyond what the pipeline alone can know.
- **Action items panel** ("What should the funder do") — the single, prescriptive
  output the user takes back to their workflow.
- **Source provenance panel** — every BigQuery row identifier and every external
  URL that contributed to this dossier, listed and clickable.

---

## Architecture

```
vigil/
├─ backend/
│  ├─ app/
│  │  ├─ main.py              # FastAPI + CORS + routes
│  │  ├─ config.py            # env / feature flags / Bedrock vs direct Anthropic
│  │  ├─ bigquery_client.py   # BQ goldens + funding lookups
│  │  ├─ sources/             # opensanctions, tavily, canlii, gdelt
│  │  ├─ classifier.py        # Claude-via-Bedrock per-article + briefing + actions
│  │  ├─ forensics.py         # BQ joins for loop_universe, t3010, overhead, sole-source, directors
│  │  ├─ risk_scorer.py       # 0-100 score with graceful degradation per signal
│  │  ├─ pipeline.py          # screen-by-id + screen-by-name orchestrator
│  │  └─ models.py            # pydantic dossier schema
│  └─ scripts/precache.py     # warm the demo dossiers + portfolio stats
├─ frontend/
│  ├─ app/
│  │  ├─ page.tsx             # dashboard (search, headline, top-orgs, featured)
│  │  └─ orgs/[id]/page.tsx   # dossier (timeline, actions, briefing, panels, provenance)
│  └─ components/             # RiskBadge · Timeline · ActionItems · ProvenancePanel · …
├─ cache/                     # gitignored disk JSON; rebuilt by precache
└─ .env.example
```

---

## API surface

- `GET /api/health` — feature-flag report
- `GET /api/orgs/top?limit=200` — dashboard table (cached)
- `GET /api/orgs/{id}` — full dossier (cached)
- `POST /api/orgs/screen-by-name` — live screen for any org name (caches as `adhoc-<slug>`)
- `GET /api/orgs/search?q=…` — BigQuery name + alias lookup
- `GET /api/portfolio/stats` — headline numbers
