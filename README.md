# FPL Optimizer — Agentic AI Edition

> **A multi-agent AI system for the 2025-26 Fantasy Premier League season.**
> Built by a team of 5 developers across 9 structured weeks, progressing from statistical modelling through autonomous agents to a deployed product.

---

## Project Vision

The FPL Optimizer is not a static prediction tool. The end goal is a **network of specialised AI agents** that autonomously reason about transfers, captaincy, squad selection, and fixture difficulty — informed by live data and a continuously improving ML backbone.

Each agent has a defined role:

| Agent | Responsibility |
|-------|---------------|
| **Statistician** | Predicts GW points using XGBoost and feature-engineered historical data |
| **Transfer** | Evaluates transfer options against budget and fixture run |
| **Captain** | Selects the optimal armband based on predicted ceiling and consistency |
| **Scout** | Surfaces differential picks and injured / rotating player alerts |

We are currently in **Phase 1** — building and evaluating the Statistician Agent's ML foundation.

---

## Current Goal — Phase 1: The ML Duel

> Each team member trains their own model variant independently. We then compare results on the same held-out test set (2024-25 GW 38) and select the best architecture to carry forward into the agent layer.

**Baseline already established:**

| Model | MAE | RMSE | R² |
|-------|-----|------|----|
| XGBoost (our baseline) | 0.917 pts | 1.882 pts | 0.289 |

Candidates being explored: Random Forest, LightGBM, Neural Net (MLP), Linear Ridge.

---

## 9-Week Syllabus

### Phase 1 — Statistician Agent · Weeks 1–3
*ML foundation: build a reliable point-prediction pipeline.*

| Week | Deliverable |
|------|-------------|
| 1 | Data ingestion, cleaning, feature engineering pipeline |
| 2 | Exploratory Data Analysis — distributions, correlations, position breakdowns |
| 3 | XGBoost baseline + ML Duel (each member trains a model, best one wins) |

### Phase 2 — Agentic AI Layer · Weeks 4–6
*Wrap the ML model in autonomous reasoning agents.*

| Week | Deliverable |
|------|-------------|
| 4 | LLM integration — tool-use, prompt engineering for FPL decisions |
| 5 | Multi-agent orchestration — Statistician, Transfer, and Captain agents |
| 6 | RAG pipeline — inject live fixture difficulty and injury feed as context |

### Phase 3 — Deployment · Weeks 7–9
*Ship it.*

| Week | Deliverable |
|------|-------------|
| 7 | REST API (FastAPI) — serve predictions and agent recommendations |
| 8 | Dashboard (Streamlit) — visualise picks, form, and fixture ratings |
| 9 | CI/CD, Docker containerisation, final demo |

---

## Folder Map

```
fpl-optimizers-agentic-ai/
│
├── analysis/                        # ML logic — Statistician Agent
│   ├── __init__.py
│   ├── data_ingestion.py            # Loads raw GW CSVs from Vaastav folder structure
│   ├── data_cleaning.py             # Type casting, missing-value strategy, encoding
│   ├── feature_engineering.py       # Rolling averages, form index, fixture difficulty
│   ├── fpl_pipeline.py              # End-to-end orchestrator: ingest → clean → engineer → save
│   ├── fpl_eda_analysis.ipynb       # Exploratory Data Analysis (fully executed)
│   └── fpl_model_training.ipynb     # XGBoost GW38 predictor — baseline model
│
├── data/
│   └── processed_fpl_data.csv       # Cleaned & feature-engineered (2024-25 + 2025-26)
│
├── reports/                         # Performance charts (saved by notebooks)
│   ├── feature_importance.png
│   ├── gw38_predicted_vs_actual.png
│   ├── learning_curve.png
│   └── top20_gw38.png
│
├── requirements.txt
├── .gitignore
└── README.md
```

---

## Getting Started

### 1. Clone

```bash
git clone https://github.com/moyez48/fpl-optimizers-agentic-ai.git
cd fpl-optimizers-agentic-ai
```

### 2. Virtual Environment

```bash
# Create
python -m venv .venv

# Activate — Windows
.venv\Scripts\activate

# Activate — macOS / Linux
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Add Raw Data

Download the Vaastav FPL dataset (see Data Credit) and place the season folders under `data/` so the structure matches:

```
data/
  2024-25/gws/merged_gw.csv
  2025-26/gws/merged_gw.csv
```

### 5. Run the Pipeline

```python
from analysis.fpl_pipeline import FPLPipeline

pipeline = FPLPipeline(base_path='data')
pipeline.run_full_pipeline()
# Outputs → data/processed_fpl_data.csv
```

### 6. Open the Notebooks

```bash
jupyter notebook analysis/fpl_eda_analysis.ipynb
jupyter notebook analysis/fpl_model_training.ipynb
```

---

## Data Credit

All raw match and player data is sourced from the **Vaastav FPL Historical Dataset**.

> Anand, V. (2022). *FPL Historical Dataset*. https://github.com/vaastav/Fantasy-Premier-League/

This repository does not redistribute raw season CSV files. Please download them directly from the link above.

---

*FPL Optimizer — Agentic AI Edition · Team Project · 2025-26*
