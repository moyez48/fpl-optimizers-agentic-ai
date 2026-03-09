# Stats Agent — Reference Document

> This document is the Stats Agent's source of truth. It describes what the agent does, how every metric is calculated, what each output field means, and how to interpret the results. The Sporting Director Agent and Manager Agent should treat this as the authoritative data contract.

---

## Role

The Stats Agent is the **data engine** of the FPL Optimizer. It is responsible for:

1. Fetching live player status from the FPL API before each gameweek
2. Running the XGBoost prediction model to estimate each player's points
3. Computing last-5 gameweek form stats
4. Estimating start probability per player
5. Ranking players overall and by position
6. Delivering a structured payload to the Sporting Director Agent

The Stats Agent does **not** make transfer or team selection decisions. It produces data — the downstream agents decide.

---

## Graph Architecture

```
fetch_live_data
      │
load_player_data
      │
engineer_features
      │
run_model
      │
compute_form_stats
      │
compute_start_probability
      │
rank_players
      │
format_output
      │
     END
```

Each node has a **conditional error exit** — if any node fails, the graph routes to END with an `error` field set, preserving whatever state was computed so far.

---

## State Schema

```python
StatsAgentState = {
    # Inputs
    "gameweek": int | None,     # Target GW (None = latest in data)
    "season":   str,            # e.g. "2024-25"

    # Intermediate
    "bootstrap":  dict,         # Raw FPL bootstrap-static JSON
    "player_df":  DataFrame,    # All player-GW rows (raw)
    "feature_df": DataFrame,    # After master feature engineering

    # Outputs
    "predictions":       list[PlayerPrediction],
    "form_stats":        list[FormStat],
    "start_probs":       dict[name -> float],
    "ranked":            dict[position -> list[RankedPlayer]],
    "captain_shortlist": list[RankedPlayer],

    # Control
    "error": str | None,
    "log":   list[str],
}
```

---

## Node Reference

### Node 1 — `fetch_live_data`

**What it does:** Hits `https://fantasy.premierleague.com/api/bootstrap-static/` to get the current state of all players. Falls back to the cached `data/bootstrap_static.json` if the API is unreachable.

**Key fields extracted:**
| Field | Meaning |
|---|---|
| `status` | `a`=available, `d`=doubtful, `i`=injured, `s`=suspended, `u`=unavailable |
| `chance_of_playing_next_round` | FPL's injury probability 0-100 |
| `ep_next` | FPL's own expected points for next GW |
| `penalties_order` | 1 = designated penalty taker |
| `direct_freekicks_order` | 1 = first-choice free kick taker |
| `corners_and_indirect_freekicks_order` | 1 or 2 = corner/indirect FK taker |

---

### Node 2 — `load_player_data`

**What it does:** Loads `data/processed_fpl_data.csv` (all seasons 2024-25+) and merges bootstrap availability fields onto current-season rows by `element` (player ID).

**Columns added from bootstrap:**
- `status_encoded` — numeric: a=1.0, d=0.75, i/s/u=0.0
- `is_pen_taker` — binary: 1 if penalties_order == 1
- `is_fk_taker` — binary: 1 if direct_freekicks_order == 1
- `is_corner_taker` — binary: 1 if corners_order in [1, 2]
- `ep_next` — FPL's internal prediction (informational only, not a model feature)

---

### Node 3 — `engineer_features`

**What it does:** Runs `MasterFPLFeatureEngineer.create_all_master_features()` — the 14-step feature pipeline that produces all model inputs.

**All features are lag-safe:** every rolling computation uses `.shift(1)` to ensure GW N's feature only uses data from GW N-1 and earlier. No future data leaks into predictions.

**Key feature categories:**
| Category | Examples |
|---|---|
| Form (rolling avg) | `last_3_avg_points`, `last_5_avg_points`, `ewm_points` |
| Rotation risk | `avg_minutes_last_3`, `blank_rate_last_5`, `minutes_trend` |
| Expected stats | `xP_last_3`, `expected_goals_last_3`, `xGI_last_3` |
| Per-90 rates (lagged) | `goals_per_90_last_3`, `assists_per_90_last_3` |
| ICT / creativity | `ict_index_last_3`, `creativity_last_3`, `threat_last_3` |
| Team / defensive | `team_goals_last_3`, `cs_rate_last_3`, `goals_conceded_last_3` |
| Fixture | `opponent_strength`, `was_home`, `pos_x_opp_strength` |
| Availability | `availability_weight` |
| Position | `position_GK`, `position_DEF`, `position_MID`, `position_FWD` |

---

### Node 4 — `run_model`

**What it does:** Loads `models/xgb_history_v2.pkl` (XGBoost trained on 5 seasons: 2020-24 historical + 2024-25 current) and calls `model.predict()` on the target GW rows.

**Model summary:**
| Property | Value |
|---|---|
| Algorithm | XGBoost Regressor |
| Training data | 2020-21 through 2024-25 (~94k rows) |
| Features | 51 (see metadata JSON) |
| Validation method | Walk-forward CV, GW10-38 of 2024-25 |
| MAE (CV) | 1.030 ± 0.075 pts |
| Spearman (CV) | 0.710 ± 0.026 |
| Top-10 precision | 14% (of predicted top-10, 14% are actually top-10) |
| Top-30 precision | 27% |

**Output field:** `predicted_pts` — the model's raw point estimate (regression output). This is **not** a probability; it is a continuous score. Players should be ranked by this score, not treated as exact point counts.

**Honest limitations:**
- Top-5 precision is ~6% — the model cannot reliably predict who hauls (10+ pts)
- Best used to identify the top-30 pool, not to pinpoint the top-5
- Does not incorporate pre-match lineups (not known until ~1hr before kick-off)
- Does not parse press conference team news (plain text, not structured)

---

### Node 5 — `compute_form_stats`

**What it does:** For each player in the prediction set, summarises their last 5 completed GWs before the target GW.

**Output fields per player:**
| Field | Description |
|---|---|
| `form_gws` | List of the 5 GW numbers used |
| `pts_last5` | Raw points in each of those 5 GWs |
| `avg_pts_last5` | Mean points over last 5 GWs |
| `total_pts_last5` | Sum of points over last 5 GWs |
| `goals_last5` | Goals scored in last 5 GWs |
| `assists_last5` | Assists in last 5 GWs |
| `avg_minutes_last5` | Average minutes played (proxy for rotation risk) |
| `form_trend` | Last 2 GWs avg minus first 3 GWs avg (positive = improving form) |

---

### Node 6 — `compute_start_probability`

**What it does:** Estimates the probability a player starts the target GW. This is a blended signal, not a model output.

**Formula:**
```
start_probability = (
    0.60 × recent_start_rate      # starts or minutes≥45 in last 3 GWs
  + 0.25 × fpl_availability       # chance_of_playing_next_round / 100
  + 0.15 × avg_minutes_last5_rate # avg_minutes_last5 / 90, capped at 1.0
).clip(0, 1)
```

**Accuracy by player type:**
| Type | Typical accuracy | Notes |
|---|---|---|
| Nailed starters (Salah, Haaland) | ~90% | Consistent minutes, no rotation |
| Rotation risks (squad players) | ~65-70% | Manager-dependent |
| Returning from injury | ~50-60% | Needs team news override |
| Confirmed injured/suspended | ~95% (correctly = 0%) | status=i/s drives this |

**Important:** Start probability is a **statistical estimate**, not a guarantee. It does not know if a player is rested, if a manager changes formation, or if a last-minute injury occurs. The Manager Agent should override this with any confirmed lineup information available before the deadline.

---

### Node 7 — `rank_players`

**What it does:** Merges predictions, form, and start probability into one enriched record per player. Ranks by **expected points** = `predicted_pts × start_probability`.

**Why expected points, not raw predicted points?**
A player predicted 8 pts but with 50% start probability has the same expected value as a player predicted 4 pts with 100% start probability. The Sporting Director Agent needs this risk-adjusted figure for VORP and budget allocation.

**Output fields per player (RankedPlayer schema):**
| Field | Type | Description |
|---|---|---|
| `rank` | int | Overall rank by expected_pts |
| `name` | str | Player name |
| `team` | str | Club name |
| `position` | str | GK / DEF / MID / FWD |
| `value_m` | float | Player price in £m (value / 10) |
| `predicted_pts` | float | Raw XGBoost prediction |
| `start_prob` | float | Start probability (0.0–1.0) |
| `expected_pts` | float | predicted_pts × start_prob |
| `avg_pts_last5` | float | Last-5 GW average (form signal) |
| `form_trend` | float | Form direction (positive = rising) |
| `goals_last5` | int | Goals in last 5 GWs |
| `assists_last5` | int | Assists in last 5 GWs |

**Ranked output keys:**
- `ALL` — top 50 overall
- `GK` — top 10 goalkeepers
- `DEF` — top 15 defenders
- `MID` — top 15 midfielders
- `FWD` — top 10 forwards

---

### Node 8 — `format_output`

**What it does:** Final assembly and logging. No data transformation — just confirms completion and writes the final log entry. The Sporting Director Agent consumes the state directly after this node.

---

## Output Payload (for Sporting Director Agent)

```python
{
    "gameweek": 35,
    "season": "2024-25",
    "ranked": {
        "ALL": [ RankedPlayer, ... ],   # top 50
        "GK":  [ RankedPlayer, ... ],   # top 10
        "DEF": [ RankedPlayer, ... ],   # top 15
        "MID": [ RankedPlayer, ... ],   # top 15
        "FWD": [ RankedPlayer, ... ],   # top 10
    },
    "captain_shortlist": [ RankedPlayer, ... ],   # top 5, start_prob >= 0.70
    "form_stats": [ FormStat, ... ],
    "start_probs": { "M.Salah": 0.97, "Haaland": 0.95, ... },
    "log": [ "fetch_live_data: ...", "run_model: predicted 801 players", ... ],
    "error": None,
}
```

---

## How to Call the Stats Agent

```python
from agents.stats_agent import run_stats_agent

# Predict for a specific GW
result = run_stats_agent(gameweek=35, season="2024-25")

# Check for errors
if result["error"]:
    print(f"Agent failed: {result['error']}")
else:
    top_10 = result["ranked"]["ALL"][:10]
    captains = result["captain_shortlist"]
    salah_start_prob = result["start_probs"].get("M.Salah")
```

---

## Interpreting Predictions

| predicted_pts range | Interpretation |
|---|---|
| > 7.0 | Model is very bullish — elite fixture or exceptional recent form |
| 4.0 – 7.0 | Strong pick — consistent performer in good situation |
| 2.0 – 4.0 | Solid floor — likely to contribute but unlikely to haul |
| 0.5 – 2.0 | Average expectation — bench / differential territory |
| < 0.5 | Model expects minimal contribution — rotation risk or tough fixture |

**Do not read predicted_pts as exact.** The model's MAE is ~1.03 pts, meaning the actual score will typically differ by about 1 point. Use rankings and relative ordering, not absolute values.

---

## Known Limitations

1. **No lineup data** — the model doesn't know who starts until ~1hr before kick-off. Late team news is the single biggest blind spot.
2. **Haul prediction** — Top-5 precision is ~6%. Players who score 12+ pts typically did something exceptional (brace, pen, CS). These events are genuinely hard to predict.
3. **Historical fill** — Set-piece roles (pen taker, FK taker) are filled with 0 for pre-2024 training data, limiting the model's ability to learn from them.
4. **Single-model output** — There is no ensemble or uncertainty estimate. `predicted_pts` is a point estimate, not a distribution.

---

## Files

| File | Purpose |
|---|---|
| `agents/stats_agent.py` | LangGraph agent definition |
| `agents/STATS_AGENT.md` | This document |
| `models/xgb_history_v2.pkl` | Trained XGBoost model (pickle) |
| `models/xgb_history_v2.json` | Trained XGBoost model (XGBoost format) |
| `models/xgb_history_v2_metadata.json` | CV results, feature list, training config |
| `data/processed_fpl_data.csv` | Current-season processed data |
| `data/bootstrap_static.json` | Cached FPL API snapshot |
| `analysis/master_feature_engineering.py` | Feature engineering pipeline |
| `train_with_history.py` | Model training script (re-run to retrain) |
