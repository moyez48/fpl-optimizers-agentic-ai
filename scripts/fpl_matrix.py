"""
fpl_matrix.py
=============
Single feature-matrix builder shared by the GW8 retrain
(scripts/train_gw8_update.py) and the GW8 prediction script
(scripts/predict_gw8.py).

It mirrors the repo's established path —

    add_base_rolling_features  (train_with_history.py)
    MasterFPLFeatureEngineer   (analysis/master_feature_engineering.py)
    alias map + interactions   (same block in train_with_history.py,
                                analysis/compute_cv_metrics.py and
                                agents/stats_agent/stats_agent.py)

— with one deliberate difference: every *derived* column already stored in
the input frame is dropped first and recomputed from the raw stats. The
shipped processed CSV carries stale/all-NaN rolling columns for its most
recent season (see the workaround comment in compute_cv_metrics.py), and
MasterFPLFeatureEngineer keeps pre-existing alias columns as-is, so
rebuilding from raw is the only way to guarantee one consistent matrix
for training, CV and inference.
"""

from __future__ import annotations

import re
import sys, os

import numpy as np
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (REPO_ROOT, os.path.join(REPO_ROOT, "analysis")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Candidate features: the repo's 52 (compute_cv_metrics.CANDIDATE_FEATURES)
# plus the six defensive-contribution features added to MasterFE.
CANDIDATE_FEATURES = [
    "last_3_avg_points", "last_5_avg_points", "last_10_avg_points",
    "last_3_avg_minutes", "ewm_points",
    "season_avg_points", "form_vs_average", "points_std_last_5",
    "avg_minutes_last_3", "avg_minutes_last_5", "minutes_trend",
    "blank_gw_last", "blank_rate_last_5",
    "starts_per_90",
    "xP_last_3", "xP_last_5", "xP_ewm",
    "expected_goals_last_3", "expected_assists_last_3",
    "expected_goals_last_5", "expected_assists_last_5",
    "expected_goal_involvements_last_3", "xGI_last_3",
    "goals_per_90_last_3", "goals_per_90_last_5",
    "assists_per_90_last_3", "bonus_per_90_last_3",
    "ict_index_last_3", "ict_index_last_5",
    "creativity_last_3", "threat_last_3", "bps_last_3",
    "team_goals_last_3",
    "cs_rate_last_3", "goals_conceded_last_3", "team_cs_rate_last_3",
    "defensive_contribution_last_3", "defensive_contribution_last_5",
    "defensive_contribution_per_90_last_3",
    "tackles_last_3", "recoveries_last_3",
    "clearances_blocks_interceptions_last_3",
    "position_GK", "position_DEF", "position_MID", "position_FWD",
    "is_attacker",
    "was_home", "value", "games_played",
    "opponent_strength", "pos_x_opp_strength",
    "transfer_momentum", "attacker_x_xP", "home_x_xP",
    "team_total_points_last_gw", "cs_per_game", "availability_weight",
]

# Columns MasterFE creates via merges (dropped pre-FE, as update_data.py does).
_MERGE_CREATED = [
    "opponent_strength", "opponent_team_name",
    "opponent_xGC_last_3", "opponent_xGC_last_5",
    "team_total_points_last_gw", "team_goals_last_3", "team_xG_last_3",
    "team_cs_rate_last_3", "team_cs_rate_last_5",
]

# Stored derived columns to drop and recompute from raw stats.
_DERIVED_EXACT = {
    "season_avg_points", "points_std_last_5", "games_played",
    "ewm_points", "minutes_trend", "blank_gw_last", "blank_rate_last_5",
    "xGI_last_3", "home_attack_boost", "transfer_momentum", "price_momentum",
    "availability_weight", "form_vs_average", "pos_x_opp_strength",
    "is_attacker", "attacker_x_xP", "home_x_xP", "cs_per_game",
    "position_GK", "position_DEF", "position_MID", "position_FWD",
    "last_3_avg_points", "last_5_avg_points", "last_10_avg_points",
    "last_3_avg_minutes",
    "position_encoded", "team_encoded", "was_home_numeric", "fdr",
    *_MERGE_CREATED,
}
_DERIVED_PATTERNS = [
    re.compile(r"_last_\d+(_avg|_sum)?$"),          # *_last_3, *_last_5_avg, ...
    re.compile(r"^(avg_minutes_last_\d+)$"),
    re.compile(r"_per_90_last_\d+$"),
    re.compile(r"_ewm$"),                            # ewm_points, xP_ewm
]


def drop_derived(df: pd.DataFrame) -> pd.DataFrame:
    drop = [
        c for c in df.columns
        if c in _DERIVED_EXACT or any(p.search(c) for p in _DERIVED_PATTERNS)
    ]
    return df.drop(columns=drop)


def build_feature_matrix(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """
    Raw player-GW frame → (frame with all model features, feature list).

    Features with <50% coverage on non-planning rows are pruned (and printed),
    matching the spirit of compute_cv_metrics' coverage filter.
    """
    from train_with_history import add_base_rolling_features
    from master_feature_engineering import MasterFPLFeatureEngineer

    df = drop_derived(df)
    df = df.sort_values(["name", "season", "GW"]).reset_index(drop=True)
    df = add_base_rolling_features(df)

    df = df.drop(columns=[c for c in _MERGE_CREATED if c in df.columns])
    me = MasterFPLFeatureEngineer(df)
    df = me.create_all_master_features()

    # Aliases + interactions — identical block to train_with_history.py.
    for pos in ["GK", "DEF", "MID", "FWD"]:
        df[f"position_{pos}"] = (df["position"] == pos).astype(int)

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
        if src in df.columns:
            df[dst] = df[src]
    if "clean_sheets_last_3_avg" in df.columns:
        df["cs_per_game"] = df["clean_sheets_last_3_avg"]

    if "last_5_avg_points" in df.columns and "season_avg_points" in df.columns:
        df["form_vs_average"] = df["last_5_avg_points"] - df["season_avg_points"]

    _enc = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3, "AM": 2}
    if "opponent_strength" in df.columns:
        df["pos_x_opp_strength"] = (
            df["position"].map(_enc) * df["opponent_strength"].fillna(0)
        )
    df["is_attacker"] = df["position"].isin(["MID", "FWD", "AM"]).astype(int)
    if "xP_last_3" in df.columns:
        df["attacker_x_xP"] = df["is_attacker"] * df["xP_last_3"].fillna(0)
        df["home_x_xP"] = df["was_home"].astype(float) * df["xP_last_3"].fillna(0)

    features = [f for f in CANDIDATE_FEATURES if f in df.columns]

    # Coverage pruning on real (non-planning) rows.
    real = df
    if "is_planning_gw" in df.columns:
        real = df[~df["is_planning_gw"].fillna(False).astype(bool)]
    pruned = []
    for f in list(features):
        cov = real[f].notna().mean() if len(real) else 0.0
        if cov < 0.5:
            pruned.append((f, round(float(cov), 3)))
            features.remove(f)
    if pruned:
        print(f"  [matrix] pruned low-coverage features: {pruned}")

    return df, features


def season_year(season: str) -> int:
    return int(str(season).split("-")[0])
