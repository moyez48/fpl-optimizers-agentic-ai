# FPL Optimizer - Agentic AI Edition

> **A multi-agent AI system for the 2025-26 Fantasy Premier League season.**  
> Built by a team of 5 developers across 9 structured weeks, progressing from statistical modelling through autonomous agents to a deployed product.

---

## Project Vision

The FPL Optimizer is not a static prediction tool. The end goal is a **network of specialised AI agents** that autonomously reason about transfers, captaincy, squad selection, and fixture difficulty, informed by live data and a continuously improving ML backbone.

Each agent has a defined role:

| Agent | Responsibility |
|-------|----------------|
| **Statistician** | Predicts GW points using XGBoost and feature-engineered historical data (LangGraph pipeline) |
| **Sporting Director** | Evaluates transfer options against budget, squad constraints, and fixture outlook |
| **Manager** | Selects captaincy and armband logic from predictions and squad context |

---

## Current Status

- **ML & data**: Ingestion, cleaning, feature engineering, and baseline **XGBoost** training on a GW 38 holdout; optional **history-aware** training (`train_with_history.py`) and serialized models under `models/`.
- **Agents**: **LangGraph** Stats Agent batch-predicts per gameweek; **Sporting Director** and **Manager** agents run over squad and prediction state (see `agents/`).
- **Product**: **React (Vite)** frontend in `app/` and **FastAPI** backend in `backend/` exposing stats, predictions, and agent orchestration endpoints.

### Model evaluation (XGBoost)

**Production model — `xgb_history_v2`** (`models/xgb_history_v2.pkl`):

Walk-forward validation on **2024-25 GW10–38** (29 folds), trained with multi-season history (see `models/xgb_history_v2_metadata.json`).

| Metric | Mean |
|--------|------|
| MAE | 1.030 pts |
| RMSE | 1.957 pts |
| R² | 0.318 |
| Spearman ρ | 0.710 |
| Top-10 precision | 0.145 |
| Top-30 precision | 0.272 |

RMSE is reported alongside the other metrics in metadata; it is aligned with the same MAE scaling as the reproducible single-CSV CV below (see `rmse_mean_note` in the JSON).

**Reproducible walk-forward CV** (no Vaastav downloads — only `data/processed_fpl_data.csv`, `hist_base` empty):

```bash
python analysis/compute_cv_metrics.py
```

Writes `models/cv_metrics_processed_only.json`. Latest run: **MAE 1.063**, **RMSE 2.030**, **R² 0.304**, **Spearman 0.703** (29 folds, 2024-25 GW10–38).

**2025-26 season — walk-forward on GW1–30 request** (processed CSV only; train = all **2024-25** + **2025-26** rows with GW &lt; test GW):

```bash
python analysis/compute_cv_metrics.py --test-season 2025-26 --gw-min 1 --gw-max 30 --prior-season 2024-25
```

Writes `models/cv_metrics_2025-26_gw1_30.json`. Latest run (means over **29 folds: GW2–30**; **GW1** has no test rows that pass the same feature `dropna` gate as later weeks, so it is omitted):

| Metric | Mean |
|--------|------|
| MAE | 0.981 pts |
| RMSE | 1.936 pts |
| R² | 0.329 |
| Spearman ρ | 0.724 |
| Top-10 precision | 0.100 |
| Top-30 precision | 0.200 |

**Single-GW snapshot (Stats Agent, 2024-25 GW38)** — `predicted_pts` vs sanitised actuals, ~804 assets:

| MAE | RMSE | R² |
|-----|------|-----|
| 0.987 pts | 1.998 pts | 0.373 |

```bash
python analysis/gw_prediction_metrics.py --gameweek 38 --season 2024-25
```

**Notebook V0 baseline** (2024-25 train GW1–37 → test GW38, master features, notebook output): MAE **0.917** pts, RMSE **1.882** pts, R² **0.289** — used as the original “ML duel” reference.

Further model variants (Random Forest, LightGBM, MLP, Ridge) remain part of the ML comparison track.

---

## 9-Week Syllabus

The team is split into two parallel tracks that converge at weekly sync points.

| Week | Team A: ML & Agents | Team B: App & Deployment | Joint Sync Point |
|------|---------------------|--------------------------|------------------|
| **1-2** | **Baseline ML** — Train V0 model & set up data pipeline | **UI Scaffold** — Pitch view with mock data | **Contract**: JSON shape for a "Lineup" |
| **3-4** | **Orchestration** — Connect agents via LangGraph | **Integration** — Frontend ↔ Agent API | **First Demo**: Real AI suggestion in the UI |
| **5-6** | **Optimisation** — Cost-benefit & chip logic | **User Features** — History & compare views | **Deploy**: Alpha to Vercel / AWS |
| **7-8** | **Fine-tuning** — ML V1 & explainability | **Edge cases** — Blank GWs & injuries | **Audit** vs actual GW results |
| **9** | **Polish** — Latency & API speed | **UI/UX** — Motion & mobile | **Handover** |

---

## Repository layout

```
fpl-optimizers-agentic-ai/
|
+-- analysis/                    # ML pipeline — Statistician / features
|   +-- data_ingestion.py
|   +-- data_cleaning.py
|   +-- feature_engineering.py
|   +-- master_feature_engineering.py
|   +-- fpl_pipeline.py
|   +-- gw_prediction_metrics.py
|   +-- compute_cv_metrics.py    # Walk-forward CV → models/cv_metrics_*.json
|   +-- *.ipynb                  # EDA & model training notebooks
|
+-- agents/                      # LangGraph & agent logic
|   +-- stats_agent/             # GW batch predictions
|   +-- sporting_director/       # Transfers, squad, fixtures
|   +-- manager_agent.py         # Captaincy / armband
|
+-- app/                         # React + Vite + Tailwind frontend
+-- backend/                     # FastAPI — bridges UI to agents
+-- models/                      # Trained model artifacts + CV metric JSON
|   +-- xgb_history_v2_metadata.json
|   +-- cv_metrics_processed_only.json
|   +-- cv_metrics_2025-26_gw1_30.json     # 2025-26 GW2–30 walk-forward (see README)
+-- data/                        # Processed CSV + API/cache JSON (raw seasons not committed)
+-- scripts/                     # CLI helpers (e.g. full optimizer run)
+-- reports/                     # Notebook-generated charts
+-- .github/workflows/           # Scheduled / CI workflows
+-- train_with_history.py        # Optional history-aware training entrypoint
+-- update_data.py               # Data refresh helper
+-- requirements.txt             # Includes backend/requirements.txt
+-- README.md
```

---

## Getting Started

### 1. Clone

```bash
git clone https://github.com/moyez48/fpl-optimizers-agentic-ai.git
cd fpl-optimizers-agentic-ai
```

### 2. Python environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Raw FPL season data (for rebuilding `processed_fpl_data.csv`)

Download the [Vaastav FPL Historical Dataset](https://github.com/vaastav/Fantasy-Premier-League/) and place seasons under `data/`:

```
data/
  2024-25/gws/merged_gw.csv
  2025-26/gws/merged_gw.csv
```

### 4. Run the feature pipeline

```python
from analysis.fpl_pipeline import FPLPipeline

pipeline = FPLPipeline(base_path="data")
pipeline.run_full_pipeline()
# Writes data/processed_fpl_data.csv
```

### 5. Jupyter notebooks

```bash
jupyter notebook analysis/fpl_eda_analysis.ipynb
jupyter notebook analysis/fpl_model_training.ipynb
```

### 6. Backend (FastAPI)

From the **repository root**:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8006 --reload
```

- API docs: `http://127.0.0.1:8006/docs`  
- First stats request per gameweek may take ~minute while the LangGraph batch run completes; results are cached per (season, gameweek).

### 7. Frontend (Vite)

```bash
cd app
npm install
npm run dev
```

Default dev server: `http://localhost:5173` (CORS is configured for common Vite ports in `backend/main.py`).

### 8. CLI — full pipeline without HTTP

From the repo root (requires network access to the FPL API for live squad data):

```bash
python scripts/run_optimizer.py <FPL_MANAGER_ID>
```

---

## Data Credit

All raw match and player data is sourced from the **Vaastav FPL Historical Dataset**.

> Anand, V. (2022). *FPL Historical Dataset*. https://github.com/vaastav/Fantasy-Premier-League/

This repository does not redistribute raw season CSV files; download them from the link above.

---

*FPL Optimizer — Agentic AI Edition — Team project — 2025-26*
