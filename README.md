# FPL Optimizer: Agentic AI Edition

> A multi-phase, team-built project that applies Machine Learning, Agentic AI, and cloud deployment to the Fantasy Premier League domain. Built by a team of 5 developers over 9 weeks.

---

## 9-Week Syllabus

### Phase 1 — Statistician Agent (ML Foundation) · Weeks 1–3
> **Goal:** Build a data pipeline and train a baseline predictive model for player points.

| Week | Focus |
|------|-------|
| 1 | Data ingestion, cleaning, feature engineering pipeline |
| 2 | Exploratory Data Analysis (EDA) — distributions, correlations, position breakdowns |
| 3 | XGBoost baseline model — GW38 point prediction (player-only, MAE 0.917 pts) |

### Phase 2 — Agentic AI Layer · Weeks 4–6
> **Goal:** Wrap the ML pipeline in an autonomous agent that reasons about transfers, captaincy, and squad selection.

| Week | Focus |
|------|-------|
| 4 | LLM integration — tool-use, prompt engineering for FPL decisions |
| 5 | Multi-agent orchestration — Statistician, Transfer, and Captain agents |
| 6 | RAG (Retrieval-Augmented Generation) — inject live fixture + injury context |

### Phase 3 — Deployment · Weeks 7–9
> **Goal:** Expose the optimizer as a usable product.

| Week | Focus |
|------|-------|
| 7 | REST API (FastAPI) — serve predictions and agent recommendations |
| 8 | Dashboard (Streamlit / Power BI) — visualise picks, form, and fixture difficulty |
| 9 | CI/CD, containerisation (Docker), and final demo |

---

## Repository Map

```
fpl-optimizers-agentic-ai/
│
├── analysis/                        # ★ Statistician Agent — ML logic
│   ├── __init__.py                  # Package exports
│   ├── data_ingestion.py            # Loads raw GW data from Vaastav folder structure
│   ├── data_cleaning.py             # Type fixes, missing-value strategy, encoding
│   ├── feature_engineering.py       # Rolling averages, form, fixture difficulty features
│   ├── fpl_pipeline.py              # End-to-end orchestrator (ingest → clean → engineer → save)
│   ├── fpl_eda_analysis.ipynb       # Exploratory Data Analysis notebook (fully executed)
│   └── fpl_model_training.ipynb     # XGBoost GW38 predictor notebook (MAE 0.917, R² 0.289)
│
├── data/
│   └── processed_fpl_data.csv       # Cleaned + feature-engineered dataset (2024-25 & 2025-26)
│
├── reports/                         # ★ Performance charts (auto-saved by notebooks)
│   ├── feature_importance.png       # XGBoost feature gain chart
│   ├── gw38_predicted_vs_actual.png # Scatter — predicted vs actual GW38 points
│   ├── learning_curve.png           # Train / validation MAE per boosting round
│   └── top20_gw38.png               # Top 20 model picks vs actual hauls
│
├── requirements.txt                 # Python dependencies
├── .gitignore                       # Excludes raw season folders and venv
└── README.md                        # This file
```

---

## Model Results (Phase 1 Baseline)

| Metric | Value |
|--------|-------|
| Algorithm | XGBoost Regressor |
| Training data | 2024-25, GW 1–37 (players only: GK / DEF / MID / FWD) |
| Test data | 2024-25, GW 38 (temporal holdout — no shuffle) |
| **MAE** | **0.917 pts** |
| **RMSE** | **1.882 pts** |
| **R²** | **0.289** |
| Naive baseline MAE | 1.420 pts |
| Improvement | +34.7% over mean baseline |

Key finding: `last_3_avg_points` is the dominant feature (~44% of gain), confirming that recent form is the strongest short-term signal.

---

## Getting Started

### Prerequisites
- Python 3.10+
- Raw FPL season data from [Vaastav's FPL Dataset](https://github.com/vaastav/Fantasy-Premier-League) placed at `data/` (see Data Credit below)

### Setup

```bash
# 1. Clone the repo
git clone https://github.com/moyez48/fpl-optimizers-agentic-ai.git
cd fpl-optimizers-agentic-ai

# 2. Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

### Run the Pipeline

```python
from analysis.fpl_pipeline import FPLPipeline

pipeline = FPLPipeline(base_path='data')
pipeline.run_full_pipeline()
# → saves data/processed_fpl_data.csv
```

### Open the Notebooks

```bash
# EDA
jupyter notebook analysis/fpl_eda_analysis.ipynb

# Model training
jupyter notebook analysis/fpl_model_training.ipynb
```

---

## Team

Built by a team of 5 developers as part of a structured 9-week learning project.

---

## Data Credit

Raw match and player data sourced from the **Vaastav FPL Historical Dataset**:

> Anand, V. (2022). *FPL Historical Dataset*. Retrieved from https://github.com/vaastav/Fantasy-Premier-League/

This project does not redistribute the raw season CSVs. Download them directly from the link above and place them under `data/` following the folder structure described in that repository.
