"""
Reproducible walk-forward CV on 2024-25 GW10-38 using only data/processed_fpl_data.csv.

Uses the same feature list and XGBoost hyperparameters as train_with_history.py, but with
no external Vaastav seasons (hist_base is empty). Mean metrics approximate a single-season
validation; the deployed xgb_history_v2 model was trained with additional historical seasons
— see models/xgb_history_v2_metadata.json for that run.

Usage (repo root):
  python analysis/compute_cv_metrics.py
"""

from __future__ import annotations

import json
import os
import sys
import warnings

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PROCESSED = os.path.join(ROOT, "data", "processed_fpl_data.csv")
META_OUT = os.path.join(ROOT, "models", "cv_metrics_processed_only.json")

XGB_PARAMS = dict(
    n_estimators=500,
    learning_rate=0.02,
    max_depth=4,
    subsample=0.7,
    colsample_bytree=0.7,
    min_child_weight=5,
    reg_alpha=0.5,
    reg_lambda=2.0,
    gamma=0.1,
    random_state=42,
    verbosity=0,
    early_stopping_rounds=30,
    eval_metric="mae",
)

CANDIDATE_FEATURES = [
    "last_3_avg_points",
    "last_5_avg_points",
    "last_10_avg_points",
    "last_3_avg_minutes",
    "ewm_points",
    "season_avg_points",
    "form_vs_average",
    "points_std_last_5",
    "avg_minutes_last_3",
    "avg_minutes_last_5",
    "minutes_trend",
    "blank_gw_last",
    "blank_rate_last_5",
    "starts_per_90",
    "xP_last_3",
    "xP_last_5",
    "xP_ewm",
    "expected_goals_last_3",
    "expected_assists_last_3",
    "expected_goals_last_5",
    "expected_assists_last_5",
    "expected_goal_involvements_last_3",
    "xGI_last_3",
    "goals_per_90_last_3",
    "goals_per_90_last_5",
    "assists_per_90_last_3",
    "bonus_per_90_last_3",
    "ict_index_last_3",
    "ict_index_last_5",
    "creativity_last_3",
    "threat_last_3",
    "bps_last_3",
    "team_goals_last_3",
    "cs_rate_last_3",
    "goals_conceded_last_3",
    "team_cs_rate_last_3",
    "position_GK",
    "position_DEF",
    "position_MID",
    "position_FWD",
    "is_attacker",
    "was_home",
    "value",
    "games_played",
    "opponent_strength",
    "pos_x_opp_strength",
    "transfer_momentum",
    "attacker_x_xP",
    "home_x_xP",
    "team_total_points_last_gw",
    "cs_per_game",
    "availability_weight",
]


def build_feature_matrix(combined: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    from analysis.master_feature_engineering import MasterFPLFeatureEngineer

    combined = combined.sort_values(["name", "season", "GW"]).reset_index(drop=True)
    me = MasterFPLFeatureEngineer(combined)
    combined = me.create_all_master_features()

    for pos in ["GK", "DEF", "MID", "FWD"]:
        combined[f"position_{pos}"] = (combined["position"] == pos).astype(int)

    alias_map = {
        "total_points_last_3_avg": "last_3_avg_points",
        "total_points_last_5_avg": "last_5_avg_points",
        "total_points_last_10_avg": "last_10_avg_points",
        "minutes_last_3_avg": "last_3_avg_minutes",
        "ict_index_last_3_avg": "ict_index_last_3",
        "ict_index_last_5_avg": "ict_index_last_5",
        "creativity_last_3_avg": "creativity_last_3",
        "threat_last_3_avg": "threat_last_3",
        "clean_sheets_last_3_avg": "cs_rate_last_3",
        "goals_conceded_last_3_avg": "goals_conceded_last_3",
    }
    for src, dst in alias_map.items():
        if src in combined.columns:
            combined[dst] = combined[src]
    if "clean_sheets_last_3_avg" in combined.columns:
        combined["cs_per_game"] = combined["clean_sheets_last_3_avg"]

    if "last_5_avg_points" in combined.columns and "season_avg_points" in combined.columns:
        combined["form_vs_average"] = combined["last_5_avg_points"] - combined["season_avg_points"]

    _enc = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3, "AM": 2}
    if "opponent_strength" in combined.columns:
        combined["pos_x_opp_strength"] = (
            combined["position"].map(_enc) * combined["opponent_strength"].fillna(0)
        )
    combined["is_attacker"] = combined["position"].isin(["MID", "FWD", "AM"]).astype(int)
    if "xP_last_3" in combined.columns:
        combined["attacker_x_xP"] = combined["is_attacker"] * combined["xP_last_3"].fillna(0)
        combined["home_x_xP"] = combined["was_home"].astype(float) * combined["xP_last_3"].fillna(0)

    features = [f for f in CANDIDATE_FEATURES if f in combined.columns]
    return combined, features


def main() -> None:
    np.random.seed(42)

    if not os.path.isfile(PROCESSED):
        print(f"Missing {PROCESSED}")
        sys.exit(1)

    print("Loading processed_fpl_data.csv …")
    raw = pd.read_csv(PROCESSED)
    # Drop columns that MasterFE recomputes (avoids merge suffix conflicts on dirty CSVs).
    _drop_opp = [
        c
        for c in raw.columns
        if c == "opponent_strength"
        or c.startswith("opponent_xGC_last_")
    ]
    if _drop_opp:
        raw = raw.drop(columns=_drop_opp)
    combined, FEATURES = build_feature_matrix(raw)
    # Some optional columns (e.g. starts_per_90) can be all-NaN for 2024-25 when no hist seasons.
    s24 = combined["season"] == "2024-25"
    FEATURES = [f for f in FEATURES if combined.loc[s24, f].notna().any()]
    print(f"Rows: {len(combined):,}  Features: {len(FEATURES)}")

    hist_base = combined.iloc[0:0].copy()
    test_season = "2024-25"
    test_gws = list(range(10, 39))

    results = []
    topk_rows = []

    print(f"\nWalk-forward CV: {test_season} GW {test_gws[0]}–{test_gws[-1]} (hist_base empty)")

    for test_gw in test_gws:
        cur_train = combined[
            (combined["season"] == test_season) & (combined["GW"] < test_gw)
        ].dropna(subset=FEATURES + ["total_points"])

        test_df = combined[
            (combined["season"] == test_season) & (combined["GW"] == test_gw)
        ].dropna(subset=FEATURES + ["total_points"]).copy()

        if test_df.empty:
            continue

        train_df = pd.concat([hist_base, cur_train], ignore_index=True)
        if train_df.empty:
            continue

        split = int(len(train_df) * 0.9)
        X_tr, y_tr = train_df[FEATURES].iloc[:split], train_df["total_points"].iloc[:split]
        X_val, y_val = train_df[FEATURES].iloc[split:], train_df["total_points"].iloc[split:]

        mdl = XGBRegressor(**XGB_PARAMS)
        mdl.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)

        preds = mdl.predict(test_df[FEATURES])

        mae = mean_absolute_error(test_df["total_points"], preds)
        rmse = float(np.sqrt(mean_squared_error(test_df["total_points"], preds)))
        r2 = r2_score(test_df["total_points"], preds)
        sp = spearmanr(test_df["total_points"], preds).statistic

        topk = {}
        test_df = test_df.copy()
        test_df["pred"] = preds
        for k in [5, 10, 15, 20, 30]:
            top_pred = set(test_df.nlargest(k, "pred").index)
            top_actual = set(test_df.nlargest(k, "total_points").index)
            topk[k] = len(top_pred & top_actual) / k
        topk_rows.append(topk)

        results.append(
            {
                "gw": test_gw,
                "mae": mae,
                "rmse": rmse,
                "r2": r2,
                "spearman": sp,
                **{f"top{k}": topk[k] for k in [5, 10, 15, 20, 30]},
            }
        )

    if not results:
        print("No CV folds produced.")
        sys.exit(1)

    avg_mae = float(np.mean([r["mae"] for r in results]))
    avg_rmse = float(np.mean([r["rmse"] for r in results]))
    avg_r2 = float(np.mean([r["r2"] for r in results]))
    avg_sp = float(np.mean([r["spearman"] for r in results]))
    avg_t10 = float(np.mean([r["top10"] for r in results]))
    avg_t30 = float(np.mean([r["top30"] for r in results]))

    print("\n" + "=" * 60)
    print("SUMMARY (mean ± std across folds)")
    print("=" * 60)
    for key, label in [
        ("mae", "MAE"),
        ("rmse", "RMSE"),
        ("r2", "R²"),
        ("spearman", "Spearman"),
    ]:
        vals = [r[key] for r in results]
        print(f"  {label:<10} {np.mean(vals):.4f} ± {np.std(vals):.4f}")
    print(f"  Top-10 prec  {avg_t10:.4f}")
    print(f"  Top-30 prec  {avg_t30:.4f}")

    payload = {
        "description": "Walk-forward CV on 2024-25 GW10-38, processed_fpl_data.csv only (no Vaastav seasons).",
        "n_folds": len(results),
        "method": "Same XGBoost params as train_with_history; hist_base empty.",
        "mae_mean": round(avg_mae, 4),
        "rmse_mean": round(avg_rmse, 4),
        "r2_mean": round(avg_r2, 4),
        "spearman_mean": round(avg_sp, 4),
        "top10_precision_mean": round(avg_t10, 4),
        "top30_precision_mean": round(avg_t30, 4),
    }

    os.makedirs(os.path.dirname(META_OUT), exist_ok=True)
    with open(META_OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"\nWrote {META_OUT}")


if __name__ == "__main__":
    main()
