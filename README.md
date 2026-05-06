# FPL Optimizer

An end-to-end Fantasy Premier League optimizer built as a **3-agent LangGraph pipeline** on top of an **XGBoost points predictor**. Give it your FPL team ID — it pulls your live squad, projects every player's next-GW score, picks the optimal Starting XI + captain, and ranks single- and multi-transfer options under the real FPL price-lock and budget rules.

Trained on six seasons of historical data (94,975 player-GW rows). Walk-forward CV across GW10–38 of 2024-25: **MAE 1.03, Spearman 0.71, Top-30 precision 27%**.

---

## Components

| Component | Status | Where |
|---|---|---|
| Stats Agent (8-node LangGraph) | wired | `agents/stats_agent/` |
| Sporting Director (8-node pipeline + LangGraph node) | wired | `agents/sporting_director/` |
| Manager Agent (6-node LangGraph) | wired | `agents/manager_agent.py` |
| XGBoost predictor | trained | `models/xgb_history_v2.pkl` |
| FastAPI backend | running | `backend/main.py` |
| React + Vite frontend | running | `app/` |
| Weekly data refresh | scheduled | `update_data.py` + GitHub Action |

The system runs end-to-end today. The remaining open work is **empirical calibration** of placeholder thresholds inside the agents (VORP replacement percentile, rotation/volatility flag triggers, wildcard trigger) — see the per-agent specs.

---

## Architecture

```
┌─────────────────────────────────────────────┐
│  FPL bootstrap-static API + 6-season CSVs   │
└────────────────────┬────────────────────────┘
                     │
                     ▼
            ┌──────────────────┐
            │   Stats Agent    │   8-node LangGraph
            │   (XGBoost xP)   │   batch over ~800 players
            └────────┬─────────┘
                     │  ranked players + form_stats + bootstrap
         ┌───────────┴───────────┐
         ▼                       ▼
┌─────────────────┐     ┌──────────────────┐
│ Sporting        │     │ Manager Agent    │
│ Director        │     │                  │
│ (transfers, $)  │     │ (XI, captain,    │
│                 │     │  bench, chips)   │
└────────┬────────┘     └─────────┬────────┘
         │                        │
         │  squad_health,         │  starting_xi, captain,
         │  recommended_transfers │  bench, chip_recommendation
         └───────────┬────────────┘
                     ▼
            ┌──────────────────┐
            │  FastAPI server  │  /api/stats, /api/predict
            │      ▲           │  caches Stats output per (season, GW)
            │      │           │
            │  React + Vite    │  player cards, agent-progress UI,
            │  frontend        │  CSV/JSON export
            └──────────────────┘
```

**Why three agents?** Splits are by **decision domain, not data flow**: Stats predicts and never decides; Sporting Director owns money and the 15-player squad; Manager owns the 11-player XI, captain, and chip activation. Each agent owns its own slice of the shared `FPLOptimizerState`, so any of them can be replaced or tested in isolation without touching the others. The LangGraph node-with-error-exit pattern means a failure inside one agent surfaces cleanly without corrupting downstream state.

### Frontend (gameweek state & pre-deadline scores)

- **Single gameweek display**: Nav badge, Statistician header, and “View gameweek” all use **`selectedGw`** from the last successful stats response (`App.jsx` passes it to Stats / Dashboard / Manager).
- **Planning round**: Before official FPL **`/event/{gw}/live/`** scores exist for that gameweek, **Actual** and **+/-** columns show **—** so CSV placeholder zeros never produce bogus negative deltas vs xPts.

**Calibration TODO.** Several agent thresholds are placeholders awaiting empirical tuning — `vorp_replacement_pct`, `rotation_risk` minutes/start-prob cutoffs, `form_declining` and `high_volatility` deltas, the wildcard 5-player / 2-flag trigger, and the chip-floor constants in the Manager. The specs in `agents/` flag each one explicitly.

---

## Model performance

XGBoost regressor on 51 engineered features (form, minutes, xG/xA, ICT, fixture difficulty, transfer momentum, position dummies, interaction terms). Walk-forward cross-validation: for each test gameweek, the model is **re-trained from scratch** on all prior data — no future leakage.

| CV slice | Folds | MAE | RMSE | R² | Spearman | Top-10 | Top-30 |
|---|---|---|---|---|---|---|---|
| 2024-25 GW10–38 (multi-season train) | 29 | 1.03 | 1.96 | 0.32 | 0.71 | 14% | 27% |
| 2025-26 GW1–30 (processed-only) | 29 | 0.98 | 1.94 | 0.33 | 0.72 | 10% | 20% |

Plots produced by the training run live in `reports/`:

- `feature_importance.png` — top features by gain
- `learning_curve.png` — train / val MAE vs. boosting rounds
- `gw38_predicted_vs_actual.png` — calibration scatter on the final test GW
- `top20_gw38.png` — projected vs. actual top-20 for GW38

Reproduce the metrics yourself:

```bash
# Multi-season retrain + walk-forward CV (writes models/xgb_history_v2.{pkl,json})
python train_with_history.py

# Single-CSV walk-forward CV (no Vaastav downloads required)
python analysis/compute_cv_metrics.py

# 2025-26 GW1–30 walk-forward
python analysis/compute_cv_metrics.py --test-season 2025-26 --gw-min 1 --gw-max 30 --prior-season 2024-25

# Single-GW snapshot from the Stats Agent's predicted_pts vs. actuals
python analysis/gw_prediction_metrics.py --gameweek 38 --season 2024-25
```

Full training metadata (features, hyperparameters, per-GW metrics) is in `models/xgb_history_v2_metadata.json`, `models/cv_metrics_processed_only.json`, and `models/cv_metrics_2025-26_gw1_30.json`.

---

## Repo layout

```
fpl-optimizers-agentic-ai/
├── agents/
│   ├── stats_agent/            # Stats Agent — LangGraph, batched XGBoost inference
│   ├── sporting_director/      # Sporting Director — VORP, multi-transfer, squad health
│   ├── manager_agent.py        # Manager Agent — XI, captain, chips
│   ├── STATS_AGENT.md          # Stats Agent spec
│   ├── SPORTING_DIRECTOR.md    # Sporting Director spec
│   └── manager_agent.md        # Manager Agent spec
├── analysis/                   # Feature engineering pipeline + EDA notebooks
│   ├── data_ingestion.py       # FPL CSV + bootstrap loaders
│   ├── data_cleaning.py
│   ├── feature_engineering.py  # base rolling features
│   ├── master_feature_engineering.py  # advanced features (xP, xGI, team/opponent, ELO)
│   ├── fpl_pipeline.py         # orchestrates ingestion → cleaning → features
│   ├── compute_cv_metrics.py   # walk-forward CV → models/cv_metrics_*.json
│   ├── gw_prediction_metrics.py  # single-GW snapshot vs actuals
│   ├── fpl_eda_analysis.ipynb
│   └── fpl_model_training.ipynb
├── app/                        # React + Vite + Tailwind + Recharts frontend
│   ├── src/components/         # screens + UI (PlayerCard, AgentProgressBar, …)
│   ├── src/data/               # fake-data prototype dataset
│   ├── src/utils/              # CSV/JSON export, formation rules
│   └── CLAUDE.md               # frontend implementation rules + design tokens
├── backend/
│   ├── main.py                 # FastAPI server, caches Stats Agent output per GW
│   └── requirements.txt        # canonical Python deps
├── data/
│   ├── bootstrap_static.json   # cached FPL bootstrap snapshot
│   └── processed_fpl_data.csv  # master player-GW dataset (overwritten weekly; includes is_next preview rows flagged `is_planning_gw`)
├── models/                     # trained XGBoost artifacts + CV metrics
├── reports/                    # evaluation plots
├── scripts/
│   └── run_optimizer.py        # end-to-end runner: team ID → Stats → SD + Manager
├── train_with_history.py       # train XGBoost on 6 seasons + walk-forward CV
├── update_data.py              # weekly data refresh (+ FPL `is_next` skeleton rows — see below)
└── requirements.txt            # forwards to backend/requirements.txt
```

---

## Quickstart

Tested on Python 3.10+ / Node 18+. Windows commands shown; on macOS/Linux use `source .venv/bin/activate`.

```powershell
# 1. Clone + Python env
git clone https://github.com/moyez48/fpl-optimizers-agentic-ai.git
cd fpl-optimizers-agentic-ai
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 2. (Optional) Re-train the XGBoost model
#    The trained model is committed under models/, so this is only needed
#    if you change features or retrain from fresh historical CSVs.
#    Requires raw Vaastav season CSVs under data/<season>/gws/merged_gw.csv —
#    see "Data" below.
python train_with_history.py

# 3. Run the full pipeline for any FPL team ID
python scripts/run_optimizer.py 5858754
#    → fetches your live squad from the FPL API
#    → runs Stats Agent (~60s on first call), then Manager + Sporting Director
#    → prints formation, captain, transfer recommendations to stdout

# 4. (Optional) Run the FastAPI backend
uvicorn backend.main:app --host 0.0.0.0 --port 8006 --reload
#    → POST /api/stats         — full ranked player list for a GW
#    → GET  /api/predict/{id}  — single-player prediction
#    → API docs: http://127.0.0.1:8006/docs
#    → first request per GW runs the graph (~60s); subsequent ones are <1ms

# 5. (Optional) Run the React frontend
cd app
npm install
npm run dev   # default Vite port 5173 — backend CORS is pre-configured
```

The standalone runner in step 3 is the fastest way to verify everything works. It needs network access to `fantasy.premierleague.com`.

---

## Weekly data refresh

`update_data.py` runs the five-step pipeline **fetch → load → merge → engineer → save**, refreshing `data/processed_fpl_data.csv` so the model and Stats Agent always see the latest finished gameweek.

- **Source:** FPL bootstrap-static (for the latest finished GW number) + the [olbauday/FPL-Core-Insights](https://github.com/olbauday/FPL-Core-Insights) repo for that GW's player-level CSV.
- **Upcoming gameweek (`is_next`):** after merging the latest finished GW, the pipeline appends preview rows for FPL's **`is_next`** event (CSV column **`is_planning_gw: true`**). Those rows carry fixtures and live **`ep_next`** from the official API, with realised stats cleared to **0**, so inference can run for every player before kickoff without dropping blanks.
- **Staleness / skip logic:** freshness uses **finished** GWs only (planning preview rows never block re-ingest). If finished data is current but the **`is_next`** preview is missing, the script still runs to add it.
- **Re-engineering:** all rolling features (last-3/5/10 averages, EWM, xP windows, team/opponent strength, transfer momentum) are recomputed across the full updated dataset — `MasterFPLFeatureEngineer` is idempotent for existing rows.
- **Safe write:** `.tmp` → `.bak` → atomic rename. The Stats Agent reads the CSV fresh on each invocation, so no backend restart is needed after a refresh.
- **Schedule:** runs every Thursday 00:00 UTC via GitHub Action; also exposes a manual `workflow_dispatch` trigger.

Run locally with `python update_data.py`. Force a full rebuild with `python update_data.py --force` or `FORCE_FPL_CSV_UPDATE=1`.

---

## Agent specs

The README is intentionally a top-level overview. The authoritative contracts live alongside the code:

- **`agents/STATS_AGENT.md`** — Stats Agent: graph nodes, output schema, per-feature semantics. Treat as the data contract for downstream agents.
- **`agents/SPORTING_DIRECTOR.md`** — Sporting Director: VORP scoring, sell-price lock, multi-transfer evaluation, squad health flags, full LangGraph state contract for `FPLOptimizerState`.
- **`agents/manager_agent.md`** — Manager Agent: formation enumeration, bench-ordering rule (GK always slot 4), dynamic median-based chip thresholds with floor.
- **`app/CLAUDE.md`** — Frontend implementation rules: agent-pipeline UI contract, fake-data schema, formation/FDR rendering rules, design tokens.

---

## Data

Historical seasons are not redistributed in this repo. To rebuild `data/processed_fpl_data.csv` from raw, download the [Vaastav FPL Historical Dataset](https://github.com/vaastav/Fantasy-Premier-League/) and place each season under `data/<season>/gws/merged_gw.csv`, then run the feature pipeline:

```python
from analysis.fpl_pipeline import FPLPipeline
FPLPipeline(base_path="data").run_full_pipeline()
```

> Anand, V. (2022). *FPL Historical Dataset*. https://github.com/vaastav/Fantasy-Premier-League/
