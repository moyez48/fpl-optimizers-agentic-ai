"""
train_gw8_update.py
===================
Retrain the production XGBoost model for the 2026-27 season (GW8 update).

Route (mirrors train_with_history.py):
  * Vaastav historical seasons 2020-21..2023-24 from data/<season>/gws/
    (load_season from train_with_history.py; BASIC-era seasons are skipped
    automatically when their files are absent).
  * data/processed_fpl_data.csv — 2024-25, 2025-26 and the newly ingested
    2026-27 GW1-7 (planning-GW skeleton rows are excluded from training).
  * Feature matrix from scripts/fpl_matrix.build_feature_matrix — the repo's
    add_base_rolling_features + MasterFPLFeatureEngineer + alias block,
    rebuilt from raw stats so no stored stale columns leak in. Includes the
    six new defensive-contribution features.

Evaluation (walk-forward, honest):
  * Test folds: 2026-27 GW3..GW7. Each fold trains on every earlier season
    plus 2026-27 GWs before the test GW.
  * Early stopping inside each fold uses a TIME-BASED holdout (the latest
    gameweeks present in that fold's training data) — not a row-order slice.

Final model:
  * Trained on all real rows from all seasons.
  * Early stopping holdout = 2026-27 GW6-7 (most recent finished GWs),
    the time-based split that replaces the old name-sorted iloc 90/10.
  * Writes models/xgb_history_v2.pkl, models/xgb_history_v2.json and an
    honest models/xgb_history_v2_metadata.json (actual seasons, actual
    row count, metrics measured by the walk-forward above — nothing
    derived or scaled), plus models/cv_metrics_2026-27_gw3_7.json.

Run from repo root:
    python scripts/train_gw8_update.py
"""

from __future__ import annotations

import datetime
import json
import os
import pickle
import sys
import warnings

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

warnings.filterwarnings("ignore")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from train_with_history import load_season  # noqa: E402
from fpl_matrix import build_feature_matrix, season_year  # noqa: E402

PROCESSED = os.path.join(REPO_ROOT, "data", "processed_fpl_data.csv")
HIST_SEASONS = ["2020-21", "2021-22", "2022-23", "2023-24"]
TEST_SEASON = "2026-27"
TEST_GWS = [3, 4, 5, 6, 7]

XGB_PARAMS = dict(
    n_estimators=500, learning_rate=0.02, max_depth=4,
    subsample=0.7, colsample_bytree=0.7, min_child_weight=5,
    reg_alpha=0.5, reg_lambda=2.0, gamma=0.1,
    random_state=42, verbosity=0,
    early_stopping_rounds=30, eval_metric="mae",
)


def time_based_split(train_df: pd.DataFrame, features: list[str]):
    """
    Split a training frame into (core, validation) where validation is the
    latest gameweeks of the most recent season present — genuinely future
    data relative to the core. Falls back to a chronological 10% tail.
    """
    df = train_df.copy()
    df["_sy"] = df["season"].map(season_year)
    df = df.sort_values(["_sy", "GW"]).reset_index(drop=True)
    latest_year = df["_sy"].max()
    latest = df[df["_sy"] == latest_year]
    latest_gws = sorted(latest["GW"].unique())
    val_gws = latest_gws[-2:] if len(latest_gws) >= 2 else latest_gws
    val_mask = (df["_sy"] == latest_year) & (df["GW"].isin(val_gws))
    if val_mask.sum() < 100 or val_mask.sum() > 0.3 * len(df):
        cut = int(len(df) * 0.9)
        val_mask = pd.Series(False, index=df.index)
        val_mask.iloc[cut:] = True
    core = df[~val_mask].drop(columns=["_sy"])
    val = df[val_mask].drop(columns=["_sy"])
    return core, val


def fold_metrics(test_df: pd.DataFrame, preds: np.ndarray) -> dict:
    out = {
        "mae": float(mean_absolute_error(test_df["total_points"], preds)),
        "rmse": float(np.sqrt(mean_squared_error(test_df["total_points"], preds))),
        "r2": float(r2_score(test_df["total_points"], preds)),
        "spearman": float(spearmanr(test_df["total_points"], preds).statistic),
    }
    t = test_df.copy()
    t["pred"] = preds
    for k in (10, 30):
        top_pred = set(t.nlargest(k, "pred").index)
        top_actual = set(t.nlargest(k, "total_points").index)
        out[f"top{k}"] = len(top_pred & top_actual) / k
    return out


def main() -> None:
    np.random.seed(42)
    os.chdir(REPO_ROOT)

    # ── Load ──────────────────────────────────────────────────────────────
    print("=" * 62)
    print("LOADING DATA")
    print("=" * 62)
    frames = []
    used_hist = []
    for s in HIST_SEASONS:
        df_s = load_season(s)
        if df_s is not None:
            frames.append(df_s)
            used_hist.append(s)

    current = pd.read_csv(PROCESSED, low_memory=False)
    if "is_planning_gw" in current.columns:
        n_plan = int(current["is_planning_gw"].fillna(False).astype(bool).sum())
        current = current[~current["is_planning_gw"].fillna(False).astype(bool)]
        print(f"Processed CSV: excluded {n_plan} planning-GW rows from training")
    frames.append(current)
    combined_raw = pd.concat(frames, ignore_index=True, sort=False)
    print(f"Combined raw: {len(combined_raw):,} rows | "
          f"seasons: {sorted(combined_raw['season'].astype(str).unique())}")

    # ── Feature matrix ────────────────────────────────────────────────────
    print("\nBuilding feature matrix (base rolling + MasterFE)...")
    combined, FEATURES = build_feature_matrix(combined_raw)
    print(f"Features ({len(FEATURES)}): {FEATURES}")

    data = combined.dropna(subset=FEATURES + ["total_points"]).copy()
    print(f"Trainable rows after dropna: {len(data):,}")
    print("Rows by season:")
    print(data.groupby("season").size().to_string())

    # ── Walk-forward CV on 2026-27 GW3-7 ──────────────────────────────────
    print("\n" + "=" * 62)
    print(f"WALK-FORWARD CV — test {TEST_SEASON} GW{TEST_GWS[0]}-{TEST_GWS[-1]}")
    print("=" * 62)
    results = []
    for test_gw in TEST_GWS:
        train_df = data[
            (data["season"] != TEST_SEASON)
            | ((data["season"] == TEST_SEASON) & (data["GW"] < test_gw))
        ]
        # strictly-earlier guard across seasons is inherent: all other
        # seasons precede 2026-27 chronologically.
        test_df = data[(data["season"] == TEST_SEASON) & (data["GW"] == test_gw)].copy()
        if test_df.empty or train_df.empty:
            print(f"  GW{test_gw}: skipped (empty)")
            continue
        core, val = time_based_split(train_df, FEATURES)
        mdl = XGBRegressor(**XGB_PARAMS)
        mdl.fit(core[FEATURES], core["total_points"],
                eval_set=[(val[FEATURES], val["total_points"])], verbose=False)
        preds = mdl.predict(test_df[FEATURES])
        m = fold_metrics(test_df, preds)
        m["gw"] = test_gw
        m["n_train"] = len(core)
        m["n_test"] = len(test_df)
        results.append(m)
        print(f"  GW{test_gw}: train={len(core):,} test={len(test_df)} "
              f"MAE={m['mae']:.3f} RMSE={m['rmse']:.3f} R2={m['r2']:.3f} "
              f"Sp={m['spearman']:.3f} T10={m['top10']:.0%} T30={m['top30']:.0%}")

    if not results:
        raise SystemExit("No CV folds produced — aborting.")

    means = {k: float(np.mean([r[k] for r in results]))
             for k in ("mae", "rmse", "r2", "spearman", "top10", "top30")}
    print(f"\n  MEAN ({len(results)} folds): MAE={means['mae']:.4f} "
          f"RMSE={means['rmse']:.4f} R2={means['r2']:.4f} "
          f"Spearman={means['spearman']:.4f} "
          f"Top10={means['top10']:.3f} Top30={means['top30']:.3f}")

    cv_payload = {
        "description": (
            f"Walk-forward CV on {TEST_SEASON} GW{TEST_GWS[0]}-{TEST_GWS[-1]}; "
            "train = all prior seasons (vaastav 2020-24 + processed 2024-25, "
            f"2025-26) + {TEST_SEASON} GW < test GW. Time-based early-stopping "
            "holdout inside each fold."
        ),
        "test_season": TEST_SEASON,
        "gw_range": [TEST_GWS[0], TEST_GWS[-1]],
        "n_folds": len(results),
        "features": FEATURES,
        "n_features": len(FEATURES),
        "mae_mean": round(means["mae"], 4),
        "rmse_mean": round(means["rmse"], 4),
        "r2_mean": round(means["r2"], 4),
        "spearman_mean": round(means["spearman"], 4),
        "top10_precision_mean": round(means["top10"], 4),
        "top30_precision_mean": round(means["top30"], 4),
        "per_gw": [
            {"gw": r["gw"], "mae": round(r["mae"], 4), "rmse": round(r["rmse"], 4),
             "r2": round(r["r2"], 4), "spearman": round(r["spearman"], 4),
             "top10": round(r["top10"], 4), "top30": round(r["top30"], 4),
             "n_train": r["n_train"], "n_test": r["n_test"]}
            for r in results
        ],
    }
    cv_path = os.path.join(REPO_ROOT, "models", "cv_metrics_2026-27_gw3_7.json")
    with open(cv_path, "w") as f:
        json.dump(cv_payload, f, indent=2)
    print(f"  Wrote {cv_path}")

    # ── Final model on all data ───────────────────────────────────────────
    print("\n" + "=" * 62)
    print("TRAINING FINAL MODEL ON ALL DATA")
    print("=" * 62)
    core, val = time_based_split(data, FEATURES)
    print(f"  Core: {len(core):,} rows | early-stopping holdout "
          f"(latest GWs): {len(val):,} rows "
          f"({sorted(val['season'].unique())} GW{sorted(val['GW'].unique())})")
    final_model = XGBRegressor(**XGB_PARAMS)
    final_model.fit(core[FEATURES], core["total_points"],
                    eval_set=[(val[FEATURES], val["total_points"])], verbose=False)
    print(f"  Best iteration: {final_model.best_iteration}")

    model_dir = os.path.join(REPO_ROOT, "models")
    pkl_path = os.path.join(model_dir, "xgb_history_v2.pkl")
    json_path = os.path.join(model_dir, "xgb_history_v2.json")
    meta_path = os.path.join(model_dir, "xgb_history_v2_metadata.json")
    with open(pkl_path, "wb") as f:
        pickle.dump(final_model, f)
    final_model.save_model(json_path)

    actual_seasons = sorted(data["season"].astype(str).unique().tolist())
    metadata = {
        "model": {
            "name": "xgb_history_v2",
            "version": "2.1",
            "created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": "XGBRegressor",
            "description": (
                f"XGBoost FPL points predictor retrained for 2026-27 (GW8) on "
                f"{len(actual_seasons)} seasons ({actual_seasons[0]} to "
                f"{actual_seasons[-1]}), including defensive-contribution "
                f"features. Walk-forward CV validated on 2026-27 GW3-7."
            ),
        },
        "training": {
            "seasons": actual_seasons,
            "total_rows": int(len(data)),
            "features": FEATURES,
            "n_features": len(FEATURES),
            "target": "total_points",
            "params": {k: v for k, v in XGB_PARAMS.items()},
            "early_stopping_holdout": (
                "time-based: latest gameweeks of the most recent season "
                "in the training frame"
            ),
        },
        "cv_performance": {
            "method": (f"walk-forward CV, {TEST_SEASON} GW{TEST_GWS[0]}-"
                       f"{TEST_GWS[-1]}; train = all prior seasons + "
                       f"{TEST_SEASON} GW < test GW"),
            "n_folds": len(results),
            "mae_mean": round(means["mae"], 4),
            "rmse_mean": round(means["rmse"], 4),
            "r2_mean": round(means["r2"], 4),
            "spearman_mean": round(means["spearman"], 4),
            "top10_precision_mean": round(means["top10"], 4),
            "top30_precision_mean": round(means["top30"], 4),
        },
        "usage": {
            "load": "import pickle; model = pickle.load(open('models/xgb_history_v2.pkl','rb'))",
            "predict": "model.predict(feature_df[FEATURES])",
            "features": "See training.features list above",
            "preprocessing": "Apply MasterFPLFeatureEngineer.create_all_master_features()",
        },
    }
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"  Saved {pkl_path}, {json_path}, {meta_path}")
    print(f"  Training rows: {len(data):,} | seasons: {actual_seasons}")


if __name__ == "__main__":
    main()
