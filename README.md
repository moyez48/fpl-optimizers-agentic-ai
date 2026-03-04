# FPL Optimizer - Agentic AI Edition

> **A multi-agent AI system for the 2025-26 Fantasy Premier League season.**
> Built by a team of 5 developers across 9 structured weeks, progressing from statistical modelling through autonomous agents to a deployed product.

---

## Project Vision

The FPL Optimizer is not a static prediction tool. The end goal is a **network of specialised AI agents** that autonomously reason about transfers, captaincy, squad selection, and fixture difficulty, informed by live data and a continuously improving ML backbone.

Each agent has a defined role:

| Agent | Responsibility |
|-------|---------------|
| **Statistician** | Predicts GW points using XGBoost and feature-engineered historical data |
| **Sporting Director** | Evaluates transfer options against budget and fixture run |
| **Manager** | Selects the optimal armband based on predicted ceiling and consistency |

We are currently in **Weeks 1-2** - building and evaluating the Statistician Agent's ML foundation.

---

## Current Goal - Phase 1: The ML Duel

> Each team member trains their own model variant independently. We then compare results on the same held-out test set (2024-25 GW 38) and select the best architecture to carry forward into the agent layer.

**Baseline already established:**

| Model | MAE | RMSE | R2 |
|-------|-----|------|----|
| XGBoost (our baseline) | 0.917 pts | 1.882 pts | 0.289 |

Candidates being explored: Random Forest, LightGBM, Neural Net (MLP), Linear Ridge.

---

## 9-Week Syllabus

The team is split into two parallel tracks that converge at weekly sync points.

| Week | Team A: ML & Agents | Team B: App & Deployment | Joint Sync Point |
|------|---------------------|--------------------------|-----------------|
| **1-2** | **Baseline ML** - Train V0 model & set up data pipeline | **UI Scaffold** - Build the Pitch View with mock data | **Contract**: Agree on the JSON structure for a "Lineup" |
| **3-4** | **Orchestration** - Connect 3 agents via LangGraph | **Integration** - Connect the frontend to the Agent API | **First Demo**: See a real "AI suggestion" appear in the UI |
| **5-6** | **Optimisation** - Add "Cost-Benefit" and "Chip" logic | **User Features** - Build the "History" and "Compare" views | **Deploy**: Push a working Alpha to Vercel / AWS |
| **7-8** | **Fine-Tuning** - Improve ML accuracy (V1) & add explainability | **Edge Cases** - Handle blank gameweeks & injury flags | **Audit**: Compare AI suggestions vs. actual GW results |
| **9** | **System Polish** - Optimise for latency & API speed | **Final UI/UX** - Polish animations and mobile responsiveness | **Handover**: Final presentation of the FPL Optimizer |

### Where we are now - Weeks 1-2 (Team A)
- Data ingestion, cleaning, and feature engineering pipeline complete
- EDA notebook fully executed (distributions, correlations, position breakdowns)
- XGBoost baseline model trained - MAE 0.917 pts on GW 38 holdout
- ML Duel in progress - each member trains a challenger model; best architecture carries forward

---

## Folder Map

```
fpl-optimizers-agentic-ai/
|
+-- analysis/                        # ML logic - Statistician Agent
|   +-- __init__.py
|   +-- data_ingestion.py            # Loads raw GW CSVs from Vaastav folder structure
|   +-- data_cleaning.py             # Type casting, missing-value strategy, encoding
|   +-- feature_engineering.py       # Rolling averages, form index, fixture difficulty
|   +-- fpl_pipeline.py              # End-to-end orchestrator: ingest > clean > engineer > save
|   +-- fpl_eda_analysis.ipynb       # Exploratory Data Analysis (fully executed)
|   +-- fpl_model_training.ipynb     # XGBoost GW38 predictor - baseline model
|
+-- data/
|   +-- processed_fpl_data.csv       # Cleaned & feature-engineered (2024-25 + 2025-26)
|
+-- reports/                         # Performance charts (saved by notebooks)
|   +-- feature_importance.png
|   +-- gw38_predicted_vs_actual.png
|   +-- learning_curve.png
|   +-- top20_gw38.png
|
+-- requirements.txt
+-- .gitignore
+-- README.md
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

# Activate - Windows
.venv\Scripts\activate

# Activate - macOS / Linux
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
# Outputs > data/processed_fpl_data.csv
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

*FPL Optimizer - Agentic AI Edition - Team Project - 2025-26*
