# Vigil

Adverse-media + forensic-signals screening for Canadian government-funding recipients.

Built for **Agency 2026 Ottawa Hackathon — Challenge #10 (Adverse Media Screening)**, April 29, 2026.

## What it does

For any organization that has received federal, Alberta, or CRA-charity funding, Vigil:

1. Loads its **funding profile** from BigQuery (gold-record entity resolution across CRA / fed / AB).
2. Runs **adverse signal sweeps** in parallel:
   - **OpenSanctions** — sanctions / PEP / debarment lists
   - **CanLII** — Canadian court decisions (fraud, regulatory, criminal)
   - **Tavily** — recent adverse media from Canadian outlets
   - **GDELT v2** (BigQuery public dataset) — historical adverse-event frequency
3. Layers in **pre-computed forensic signals** from the hackathon repo's accountability pipelines:
   - Circular-gifting risk score (Tarjan SCC + 2–6-hop cycle detection)
   - T3010 form-arithmetic violations
   - Sole-source contract preference (Alberta)
   - High-overhead pass-through indicators
   - Shared-director network propagation
4. Asks **Claude** to classify each adverse hit and author a 4-sentence Minister-ready briefing memo.
5. Computes a 0–100 **risk score**, caches the dossier to disk, and renders it in a Next.js UI with a counterfactual **funding-vs-adverse-event timeline**.

## Project layout

```
vigil/
├─ backend/        FastAPI + BigQuery + adverse-signal sources + Claude
├─ frontend/       Next.js 15 + Tailwind + Recharts
├─ cache/          Disk-cached screening dossiers (gitignored)
├─ .env.example    Required env vars
└─ README.md
```

## Quick start

### 1. Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend

```powershell
cd frontend
npm install
npm run dev
```

### 3. Pre-cache the demo orgs (run after both servers are up)

```powershell
cd backend
python -m scripts.precache
```

## Auth

- **BigQuery**: Application Default Credentials (`gcloud auth application-default login`).
- **API keys**: drop into `.env` (see `.env.example`). Each source independently degrades — if a key isn't set, that panel shows "not configured" and the risk score absorbs the missing signal as zero.

## Demo orgs (pre-cached)

| Org | BQ id | Why |
|-----|-------|-----|
| WE Charity Foundation | 42406 | $912M CSSG announcement; nine-week scandal arc in 2020 |
| WE Charity | 72807 | Network-propagation partner of WE Charity Foundation |
| Canada Charity Partners | 50517 | CRA-revoked early 2026; $55,772 in federal grants |
| Top circular-gifting flag | TBD | Pre-computed `cra.loop_universe` highest-score with federal grants |
| (live-search demo) | n/a | "GC Strategies" — illustrates coverage beyond goldens |
