---
 
title: Pitchcraft API
emoji: ⚽
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
---

# Pitchcraft — FPL Optimizer (Agentic AI)

> **A multi-agent Fantasy Premier League assistant for the 2025-26 season.**  
> XGBoost point predictions, LangGraph agents for XI/captaincy/transfers, and a **Pitchcraft** React UI for live squad management, transfer simulation, and optimization.

**Live deployments**

| Layer | Host | Notes |
|-------|------|--------|
| Frontend | [Vercel](https://pitchcraft.vercel.app) | Vite app in `app/` — root directory set to `app` in Vercel project settings |
| Backend API | [Hugging Face Space](https://moyez48-pitchcraft-api.hf.space) | Docker Space — FastAPI on port **7860** |

---

## What it does

Pitchcraft loads a manager's real FPL squad (by entry ID), enriches every player with model **xPts** for the selected gameweek, and lets you:

- **View & edit** formation, captain, vice, and bench order on an interactive pitch
- **Simulate transfers** in a sandbox (`displaySquad` / `actualSquad` split — revert restores the real squad)
- **Run optimization** — Manager Agent (XI + captaincy + chips) and Sporting Director (transfer recommendations) in one `/api/optimize` call
- **Poll live GW scores** during the active gameweek

Under the hood, three specialised agents share a cached Stats Agent batch run per gameweek:

| Agent | Role | Implementation |
|-------|------|----------------|
| **Statistician** | Batch GW point predictions for ~800 players | LangGraph pipeline in `agents/stats_agent/` → XGBoost `xgb_history_v2.pkl` |
| **Manager** | Optimal XI, captain/vice, chip recommendation | `agents/manager_agent.py` |
| **Sporting Director** | Transfer scoring, squad health, fixture outlook | `agents/sporting_director/` |

---

## Architecture

```
Browser (Pitchcraft UI — app/)
    │  VITE_API_BASE → HF Space  (prod)  or  Vite /api proxy → localhost:8006 (dev)
    ▼
FastAPI (backend/main.py)
    │  POST /api/stats  →  LangGraph Stats Agent  →  in-memory GW cache
    │  GET  /api/squad?entry=<id>  →  FPL API picks + cached predictions
    │  POST /api/optimize  →  Manager + Sporting Director
    ▼
data/processed_fpl_data.csv  +  models/xgb_history_v2.pkl
```

**Latency (measured locally, cold start):** Stats Agent full graph ~**47–60 s** per gameweek; Manager Agent XI selection **< 1 ms** once predictions are cached. Subsequent API calls for the same `(season, gameweek)` reuse the cache (~1 hour TTL).

---

## Model evaluation

Production model: **`models/xgb_history_v2.pkl`** (51 features, target = `total_points`).

All walk-forward numbers below come from `analysis/compute_cv_metrics.py` on `data/processed_fpl_data.csv`. Re-run anytime to regenerate JSON under `models/`.

### How metrics are defined

- **MAE** — mean absolute error between predicted and actual GW points, averaged over all player-rows in the test GW, then averaged across folds:  
  `mean(|actual_points − predicted_points|)`
- **Top-K precision** — overlap of model's predicted top-K scorers with actual top-K scorers **across the full player pool** that GW:  
  `|top_K(pred) ∩ top_K(actual)| / K`  
  This measures **pick identification quality**, not end-to-end squad selection from a fixed 15-man team (that backtest is not stored).

### 2024-25 — GW10–38 (29 folds, processed CSV only)

```bash
python analysis/compute_cv_metrics.py
# → models/cv_metrics_processed_only.json
```

| Metric | Mean |
|--------|-----:|
| MAE | **1.063** pts |
| RMSE | **2.030** pts |
| R² | **0.304** |
| Spearman ρ | **0.703** |
| Top-10 precision | **17.6%** |
| Top-30 precision | **30.5%** |

### 2025-26 — GW2–30 (29 folds; GW1 skipped — no test rows after feature `dropna`)

Train = all **2024-25** + **2025-26** rows with `GW < test_GW`.

```bash
python analysis/compute_cv_metrics.py --test-season 2025-26 --gw-min 1 --gw-max 30 --prior-season 2024-25
# → models/cv_metrics_2025-26_gw1_30.json
```

| Metric | Mean |
|--------|-----:|
| MAE | **0.981** pts |
| RMSE | **1.936** pts |
| R² | **0.329** |
| Spearman ρ | **0.724** |
| Top-10 precision | **10.0%** |
| Top-30 precision | **20.0%** |

Per-gameweek breakdowns are in `models/cv_metrics_2025-26_gw1_30.json` (`per_gw` array).

### Single-GW live check (Stats Agent output)

```bash
python analysis/gw_prediction_metrics.py --gameweek 38 --season 2024-25
```

Optional flags: `--played-only` (exclude 0-minute assets), `--precision-k 5`.

### Training entrypoints

| Script | Purpose |
|--------|---------|
| `train_with_history.py` | Multi-season history-aware training → `xgb_history_v2.pkl` + metadata |
| `analysis/compute_cv_metrics.py` | Reproducible walk-forward CV (no extra downloads) |
| `update_data.py` | Merge latest GW into `processed_fpl_data.csv` (also runs on GitHub Actions schedule) |

---

## Repository layout

```
fpl-optimizers-agentic-ai/
├── app/                         # Pitchcraft UI — React + Vite + Tailwind
│   ├── src/App.jsx              # Main dashboard, squad state, GW selector
│   ├── src/pitchcraft/          # Pitch, transfers panel, player chips
│   ├── src/lib/pitchcraftApi.js # API URL helper (VITE_API_BASE)
│   └── src/utils/               # optimalXI, squadEdit, transferApply, gameweekDisplay
├── backend/
│   ├── main.py                  # FastAPI — all /api/* routes
│   └── requirements.txt
├── agents/
│   ├── stats_agent/             # LangGraph batch prediction pipeline
│   ├── sporting_director/       # Transfers, VORP, fixtures, squad validation
│   └── manager_agent.py         # XI, captaincy, chips
├── analysis/                    # Feature engineering, CV, notebooks
├── models/                      # xgb_history_v2.pkl + cv_metrics_*.json
├── data/                        # processed_fpl_data.csv (LFS), fixtures cache
├── Dockerfile                   # Hugging Face Space (port 7860)
├── vercel.json                  # Vercel build (root dir = app/ in project settings)
├── middleware.js                # Vercel edge proxy for /fpl-api/* → FPL official API
├── update_data.py               # Weekly CSV refresh pipeline
├── deploy.py                    # Manual HF upload helper (optional)
└── .github/workflows/
    ├── hf-sync.yml              # Push main → Hugging Face Space
    └── weekly_update.yml        # Scheduled data refresh
```

Large artifacts (`.pkl`, `.png`, `.csv`) are tracked with **Git LFS** (see `.gitattributes`).

---

## Getting started (local)

### 1. Clone & Python env

```bash
git clone https://github.com/moyez48/fpl-optimizers-agentic-ai.git
cd fpl-optimizers-agentic-ai
git lfs pull

python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Backend

From the **repository root**:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8006 --reload
```

- Docs: http://127.0.0.1:8006/docs  
- Health: http://127.0.0.1:8006/health  

Requires `data/processed_fpl_data.csv` and `models/xgb_history_v2.pkl` (pull LFS after clone).

### 3. Frontend

```bash
cd app
npm install
npm run dev
```

Open http://localhost:5173 — Vite proxies `/api/*` to `http://127.0.0.1:8006` (override with `VITE_API_PROXY` in `app/.env.local`).

### 4. Load a squad

Enter your FPL **manager entry ID** in the UI and click **Load Team**, or set `VITE_FPL_ENTRY_ID` in `app/.env.local` for auto-bootstrap.

### 5. CLI (no HTTP)

```bash
python scripts/run_optimizer.py <FPL_MANAGER_ID>
```

---

## API overview

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness |
| POST | `/api/stats` | Full ranked player list for a GW (runs Stats Agent if not cached) |
| GET | `/api/predict/{player_id}` | Single-player prediction (uses GW cache) |
| GET | `/api/players?gw=` | All players with xPts for a GW |
| GET | `/api/squad?entry=<fpl_id>` | Pitchcraft bootstrap — squad layout + enriched players |
| GET | `/api/squad/{fpl_id}` | Path-param alias for the above |
| POST | `/api/optimize` | Manager XI + Sporting Director transfers |
| POST | `/api/manager` | Manager Agent only |
| POST | `/api/transfers` | Sporting Director only |
| GET | `/api/event/{gw}/live-points` | Live element scores (active GW polling) |
| GET | `/api/data/meta` | CSV freshness / GW range snapshot |

---

## Deployment

### Frontend — Vercel

1. Import repo; set **Root Directory** to **`app`**
2. Build settings are in [`vercel.json`](./vercel.json) at repo root (install/build/output paths assume `app` is cwd)
3. Production API origin is baked in via [`app/.env.production`](./app/.env.production):

   ```
   VITE_API_BASE=https://moyez48-pitchcraft-api.hf.space
   ```

   Routes in code append `/api/...` — do **not** include `/api` in the base URL.

4. [`middleware.js`](./middleware.js) proxies `/fpl-api/*` to the official FPL API on Vercel (browser-like headers).

### Backend — Hugging Face Spaces

- Space: **moyez48/pitchcraft-api** (Docker SDK)
- [`Dockerfile`](./Dockerfile) at repo root — `uvicorn backend.main:app --host 0.0.0.0 --port 7860`
- Pushes to `main` sync via [`.github/workflows/hf-sync.yml`](./.github/workflows/hf-sync.yml) (`hf upload` + `PITCHCRAFT_AI` secret)
- **CORS** in `backend/main.py`: `https://pitchcraft.vercel.app`, `https://*.vercel.app`, localhost Vite ports; extend with `CORS_ALLOWED_ORIGINS` env var

### Data refresh (CI)

[`.github/workflows/weekly_update.yml`](./.github/workflows/weekly_update.yml) runs `update_data.py` on a schedule and commits updated `processed_fpl_data.csv` when new gameweeks are available.

---

## Environment variables

| Variable | Where | Purpose |
|----------|-------|---------|
| `VITE_API_BASE` | Vercel / `app/.env.production` | Public FastAPI origin (no trailing slash) |
| `VITE_API_PROXY` | `app/.env.local` | Local dev proxy target (default `http://127.0.0.1:8006`) |
| `VITE_FPL_ENTRY_ID` | `app/.env.local` | Optional auto-load squad on startup |
| `CORS_ALLOWED_ORIGINS` | HF Space / backend host | Extra comma-separated allowed origins |
| `SKIP_FPL_CSV_REFRESH` | Backend | Skip pre-request CSV refresh |
| `AUTO_REFRESH_FPL_DATA` | Backend | Enable periodic CSV sweep in lifespan |
| `PITCHCRAFT_AI` | GitHub Actions secret | HF upload token for `hf-sync.yml` |

---

## Data credit

Raw historical season CSVs: [Vaastav FPL Historical Dataset](https://github.com/vaastav/Fantasy-Premier-League/) — not redistributed here; download separately if rebuilding from scratch.

Live picks, bootstrap, and fixtures: [Fantasy Premier League API](https://fantasy.premierleague.com/api/).

> Anand, V. (2022). *FPL Historical Dataset*. https://github.com/vaastav/Fantasy-Premier-League/

---

*Pitchcraft / FPL Optimizer — Agentic AI — 2025-26*
