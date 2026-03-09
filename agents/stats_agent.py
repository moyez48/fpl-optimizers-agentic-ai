"""
stats_agent.py
==============
LangGraph-powered Stats Agent for the FPL Optimizer.

Responsibilities:
  - Fetch live FPL bootstrap data (player status, availability)
  - Load processed historical + current season player data
  - Run Master Feature Engineering pipeline
  - Run XGBoost inference (predicted GW points)
  - Compute last-5 form stats per player
  - Compute start probability per player
  - Rank players overall and by position
  - Output a structured payload for the Sporting Director Agent

Graph structure:
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

Reference: agents/STATS_AGENT.md
"""

from __future__ import annotations

import os
import sys
import json
import pickle
import warnings
import requests
from typing import TypedDict, Optional, Any

import numpy as np
import pandas as pd
from langgraph.graph import StateGraph, END

warnings.filterwarnings("ignore")

# ── Paths (relative to repo root) ────────────────────────────────────────────
REPO_ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH      = os.path.join(REPO_ROOT, "data", "processed_fpl_data.csv")
MODEL_PATH     = os.path.join(REPO_ROOT, "models", "xgb_history_v2.pkl")
META_PATH      = os.path.join(REPO_ROOT, "models", "xgb_history_v2_metadata.json")
BOOTSTRAP_PATH = os.path.join(REPO_ROOT, "data", "bootstrap_static.json")
ANALYSIS_DIR   = os.path.join(REPO_ROOT, "analysis")

if ANALYSIS_DIR not in sys.path:
    sys.path.insert(0, ANALYSIS_DIR)

FPL_BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"

# ── Features (must match exactly what the model was trained on) ───────────────
with open(META_PATH) as f:
    _meta = json.load(f)
FEATURES = _meta["training"]["features"]


# ═══════════════════════════════════════════════════════════════════════════════
# STATE DEFINITION
# Every node reads from and writes to this shared dict.
# TypedDict gives us type safety and makes the schema explicit.
# ═══════════════════════════════════════════════════════════════════════════════

class StatsAgentState(TypedDict):
    # ── Inputs ────────────────────────────────────────────────────────────────
    gameweek: Optional[int]          # Target GW to predict (None = next GW)
    season:   str                    # e.g. "2024-25"

    # ── Intermediate ──────────────────────────────────────────────────────────
    bootstrap: Optional[dict]        # Raw bootstrap-static JSON
    player_df: Optional[Any]         # Raw loaded DataFrame (pd.DataFrame)
    feature_df: Optional[Any]        # Feature-engineered DataFrame

    # ── Outputs ───────────────────────────────────────────────────────────────
    predictions: Optional[list]      # [{name, team, position, predicted_pts, ...}]
    form_stats: Optional[list]       # [{name, form_last5, avg_last5, ...}]
    start_probs: Optional[dict]      # {player_name: float 0-1}
    ranked: Optional[dict]           # {GK: [...], DEF: [...], MID: [...], FWD: [...], ALL: [...]}
    captain_shortlist: Optional[list] # Top 5 captain candidates

    # ── Control ───────────────────────────────────────────────────────────────
    error: Optional[str]             # Set by any node on failure
    log: list                        # Append-only execution log


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 1 — fetch_live_data
# Hits the FPL API to get real-time player status, availability,
# set-piece roles, and ep_next (FPL's own expected points model).
# Falls back to the locally cached bootstrap_static.json if offline.
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_live_data(state: StatsAgentState) -> StatsAgentState:
    log = state.get("log", [])
    try:
        resp = requests.get(FPL_BOOTSTRAP_URL, timeout=10)
        resp.raise_for_status()
        bootstrap = resp.json()
        log.append("fetch_live_data: pulled fresh bootstrap-static from FPL API")
    except Exception as e:
        # Offline fallback — use cached file
        if os.path.exists(BOOTSTRAP_PATH):
            with open(BOOTSTRAP_PATH, encoding="utf-8") as f:
                bootstrap = json.load(f)
            log.append(f"fetch_live_data: API failed ({e}), loaded cached bootstrap")
        else:
            return {**state, "error": f"fetch_live_data: no data available — {e}", "log": log}

    return {**state, "bootstrap": bootstrap, "log": log}


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 2 — load_player_data
# Loads the processed CSV (all seasons) and the bootstrap player table.
# Merges availability / set-piece fields from bootstrap onto current rows.
# ═══════════════════════════════════════════════════════════════════════════════

def load_player_data(state: StatsAgentState) -> StatsAgentState:
    log = state.get("log", [])
    if state.get("error"):
        return state

    try:
        df = pd.read_csv(DATA_PATH, low_memory=False)

        # ── Enrich with live bootstrap fields ─────────────────────────────────
        bs_elements = pd.DataFrame(state["bootstrap"]["elements"])

        # Status encoding: a=fully available, d=doubtful, i=injured, s=suspended
        status_map = {"a": 1.0, "d": 0.75, "i": 0.0, "s": 0.0, "u": 0.0, "n": 0.0}
        bs_merge = bs_elements[[
            "id", "status", "chance_of_playing_next_round",
            "chance_of_playing_this_round", "ep_next",
            "penalties_order", "direct_freekicks_order",
            "corners_and_indirect_freekicks_order",
        ]].rename(columns={"id": "element"})

        bs_merge["status_encoded"]  = bs_merge["status"].map(status_map).fillna(1.0)
        bs_merge["is_pen_taker"]    = (bs_merge["penalties_order"] == 1).astype(int)
        bs_merge["is_fk_taker"]     = (bs_merge["direct_freekicks_order"] == 1).astype(int)
        bs_merge["is_corner_taker"] = bs_merge["corners_and_indirect_freekicks_order"].isin([1, 2]).astype(int)
        bs_merge["ep_next"]         = pd.to_numeric(bs_merge["ep_next"], errors="coerce")

        df = df.merge(
            bs_merge[["element", "status_encoded", "chance_of_playing_next_round",
                       "chance_of_playing_this_round", "ep_next",
                       "is_pen_taker", "is_fk_taker", "is_corner_taker"]],
            on="element", how="left", suffixes=("", "_bs")
        )

        log.append(f"load_player_data: loaded {len(df):,} rows across "
                   f"{df['season'].nunique()} seasons")

    except Exception as e:
        return {**state, "error": f"load_player_data: {e}", "log": log}

    return {**state, "player_df": df, "log": log}


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 3 — engineer_features
# Runs MasterFPLFeatureEngineer on the full combined DataFrame, then
# applies the same aliases and interaction terms as the training script.
# ═══════════════════════════════════════════════════════════════════════════════

def engineer_features(state: StatsAgentState) -> StatsAgentState:
    log = state.get("log", [])
    if state.get("error"):
        return state

    try:
        from master_feature_engineering import MasterFPLFeatureEngineer

        df = state["player_df"].copy()
        df = df.sort_values(["name", "season", "GW"]).reset_index(drop=True)

        me = MasterFPLFeatureEngineer(df)
        df = me.create_all_master_features()

        # ── Aliases (must match training) ──────────────────────────────────────
        alias_map = {
            "total_points_last_3_avg":   "last_3_avg_points",
            "total_points_last_5_avg":   "last_5_avg_points",
            "total_points_last_10_avg":  "last_10_avg_points",
            "minutes_last_3_avg":        "last_3_avg_minutes",
            "ict_index_last_3_avg":      "ict_index_last_3",
            "ict_index_last_5_avg":      "ict_index_last_5",
            "creativity_last_3_avg":     "creativity_last_3",
            "threat_last_3_avg":         "threat_last_3",
            "clean_sheets_last_3_avg":   "cs_rate_last_3",
            "goals_conceded_last_3_avg": "goals_conceded_last_3",
        }
        for src, dst in alias_map.items():
            if src in df.columns:
                df[dst] = df[src]
        if "clean_sheets_last_3_avg" in df.columns:
            df["cs_per_game"] = df["clean_sheets_last_3_avg"]
        if "last_5_avg_points" in df.columns and "season_avg_points" in df.columns:
            df["form_vs_average"] = df["last_5_avg_points"] - df["season_avg_points"]

        # ── Position one-hots ──────────────────────────────────────────────────
        for pos in ["GK", "DEF", "MID", "FWD"]:
            df[f"position_{pos}"] = (df["position"] == pos).astype(int)

        # ── Interaction terms ─────────────────────────────────────────────────
        _enc = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}
        if "opponent_strength" in df.columns:
            df["pos_x_opp_strength"] = (
                df["position"].map(_enc) * df["opponent_strength"].fillna(0)
            )
        df["is_attacker"] = df["position"].isin(["MID", "FWD"]).astype(int)
        if "xP_last_3" in df.columns:
            df["attacker_x_xP"] = df["is_attacker"] * df["xP_last_3"].fillna(0)
            df["home_x_xP"]     = df["was_home"].astype(float) * df["xP_last_3"].fillna(0)

        log.append(f"engineer_features: {df.shape[1]} columns after FE")

    except Exception as e:
        return {**state, "error": f"engineer_features: {e}", "log": log}

    return {**state, "feature_df": df, "log": log}


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 4 — run_model
# Loads the saved XGBoost model and runs predict() on the target GW rows.
# If gameweek is None it uses the most recent complete GW in the data.
# ═══════════════════════════════════════════════════════════════════════════════

def run_model(state: StatsAgentState) -> StatsAgentState:
    log = state.get("log", [])
    if state.get("error"):
        return state

    try:
        with open(MODEL_PATH, "rb") as f:
            model = pickle.load(f)

        df = state["feature_df"]
        season = state["season"]

        # Determine target GW
        season_df = df[df["season"] == season]
        if state["gameweek"] is not None:
            target_gw = state["gameweek"]
        else:
            target_gw = int(season_df["GW"].max())

        pred_df = season_df[season_df["GW"] == target_gw].copy()

        # Fill any missing features with 0 (conservative default)
        missing = [f for f in FEATURES if f not in pred_df.columns]
        for col in missing:
            pred_df[col] = 0.0
        if missing:
            log.append(f"run_model: filled {len(missing)} missing features with 0: {missing}")

        X = pred_df[FEATURES].fillna(0)
        pred_df["predicted_pts"] = model.predict(X)

        # Keep useful output columns
        keep = ["name", "team", "position", "value", "predicted_pts",
                "GW", "was_home", "element"]
        keep = [c for c in keep if c in pred_df.columns]
        predictions = pred_df[keep].sort_values("predicted_pts", ascending=False)

        log.append(f"run_model: predicted {len(predictions)} players for GW{target_gw}")

    except Exception as e:
        return {**state, "error": f"run_model: {e}", "log": log}

    return {
        **state,
        "gameweek": target_gw,
        "predictions": predictions.to_dict("records"),
        "log": log,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 5 — compute_form_stats
# For each player in the prediction set, computes last-5 GW stats:
# avg points, total points, goals, assists, minutes, form trend.
# ═══════════════════════════════════════════════════════════════════════════════

def compute_form_stats(state: StatsAgentState) -> StatsAgentState:
    log = state.get("log", [])
    if state.get("error"):
        return state

    try:
        df = state["feature_df"]
        season = state["season"]
        gw = state["gameweek"]

        # Last 5 GWs before the target GW
        season_df = df[(df["season"] == season) & (df["GW"] < gw)]
        players = {p["name"] for p in state["predictions"]}

        form_rows = []
        for name in players:
            p_df = season_df[season_df["name"] == name].sort_values("GW").tail(5)
            if p_df.empty:
                continue
            form_rows.append({
                "name":           name,
                "form_gws":       p_df["GW"].tolist(),
                "pts_last5":      p_df["total_points"].tolist(),
                "avg_pts_last5":  round(p_df["total_points"].mean(), 2),
                "total_pts_last5": int(p_df["total_points"].sum()),
                "goals_last5":    int(p_df["goals_scored"].sum()) if "goals_scored" in p_df else 0,
                "assists_last5":  int(p_df["assists"].sum()) if "assists" in p_df else 0,
                "avg_minutes_last5": round(p_df["minutes"].mean(), 1) if "minutes" in p_df else None,
                # Trend: last 2 GWs avg minus first 3 GWs avg (positive = improving)
                "form_trend": round(
                    p_df["total_points"].tail(2).mean() - p_df["total_points"].head(3).mean(), 2
                ) if len(p_df) >= 3 else 0.0,
            })

        log.append(f"compute_form_stats: computed form for {len(form_rows)} players")

    except Exception as e:
        return {**state, "error": f"compute_form_stats: {e}", "log": log}

    return {**state, "form_stats": form_rows, "log": log}


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 6 — compute_start_probability
# Estimates the probability a player starts the target GW.
# Formula blends:
#   60% — recent starts rate (last 3 GWs of minutes/90 or starts column)
#   25% — FPL availability (chance_of_playing_next_round)
#   15% — longer-term minutes average (last 5 GWs)
# ═══════════════════════════════════════════════════════════════════════════════

def compute_start_probability(state: StatsAgentState) -> StatsAgentState:
    log = state.get("log", [])
    if state.get("error"):
        return state

    try:
        df = state["feature_df"]
        season = state["season"]
        gw = state["gameweek"]

        season_df = df[(df["season"] == season) & (df["GW"] < gw)]
        players = {p["name"] for p in state["predictions"]}

        # Bootstrap availability lookup keyed by element
        bs_elements = pd.DataFrame(state["bootstrap"]["elements"])
        bs_avail = bs_elements.set_index("id")[[
            "chance_of_playing_next_round", "status"
        ]].to_dict("index")

        # Element lookup for predictions
        pred_elements = {p["name"]: p.get("element") for p in state["predictions"]}

        start_probs = {}
        for name in players:
            p_df = season_df[season_df["name"] == name].sort_values("GW").tail(5)

            # Recent start rate from starts column (2022+) or minutes proxy
            if "starts" in p_df.columns and not p_df["starts"].isna().all():
                recent_start_rate = p_df.tail(3)["starts"].mean() / 1.0
            else:
                # minutes >= 45 as proxy for starting
                recent_start_rate = (p_df.tail(3)["minutes"] >= 45).mean() if "minutes" in p_df.columns else 0.7

            # Longer-term minutes (last 5)
            avg_min_last5 = p_df["minutes"].mean() / 90 if "minutes" in p_df.columns else 0.7
            avg_min_last5 = min(avg_min_last5, 1.0)

            # FPL availability from bootstrap
            elem = pred_elements.get(name)
            if elem and elem in bs_avail:
                chance = bs_avail[elem].get("chance_of_playing_next_round")
                avail = (chance / 100.0) if chance is not None else 1.0
            else:
                avail = 1.0

            prob = (
                0.60 * min(recent_start_rate, 1.0) +
                0.25 * avail +
                0.15 * avg_min_last5
            )
            start_probs[name] = round(float(np.clip(prob, 0.0, 1.0)), 3)

        log.append(f"compute_start_probability: computed for {len(start_probs)} players")

    except Exception as e:
        return {**state, "error": f"compute_start_probability: {e}", "log": log}

    return {**state, "start_probs": start_probs, "log": log}


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 7 — rank_players
# Merges predictions, form, and start_probability into one enriched list.
# Ranks by:  predicted_pts × start_probability  (expected value)
# Splits into position groups and overall top-50.
# ═══════════════════════════════════════════════════════════════════════════════

def rank_players(state: StatsAgentState) -> StatsAgentState:
    log = state.get("log", [])
    if state.get("error"):
        return state

    try:
        preds  = pd.DataFrame(state["predictions"])
        form   = pd.DataFrame(state["form_stats"]) if state["form_stats"] else pd.DataFrame()
        probs  = state["start_probs"] or {}

        # Merge form stats
        if not form.empty:
            preds = preds.merge(form[["name", "avg_pts_last5", "form_trend",
                                      "goals_last5", "assists_last5"]], on="name", how="left")

        # Add start probability and expected value
        preds["start_prob"]    = preds["name"].map(probs).fillna(0.7)
        preds["expected_pts"]  = (preds["predicted_pts"] * preds["start_prob"]).round(3)
        preds["value_m"]       = (preds["value"] / 10).round(1) if "value" in preds.columns else None

        # Sort by expected_pts descending
        preds = preds.sort_values("expected_pts", ascending=False).reset_index(drop=True)
        preds["rank"] = preds.index + 1

        ranked = {
            "ALL": preds.head(50).to_dict("records"),
            "GK":  preds[preds["position"] == "GK"].head(10).to_dict("records"),
            "DEF": preds[preds["position"] == "DEF"].head(15).to_dict("records"),
            "MID": preds[preds["position"] == "MID"].head(15).to_dict("records"),
            "FWD": preds[preds["position"] == "FWD"].head(10).to_dict("records"),
        }

        # Captain shortlist — top 5 overall with high start probability
        captain_shortlist = (
            preds[preds["start_prob"] >= 0.7]
            .head(5)[["name", "team", "position", "predicted_pts",
                       "start_prob", "expected_pts"]]
            .to_dict("records")
        )

        log.append(f"rank_players: top player = {preds.iloc[0]['name']} "
                   f"({preds.iloc[0]['expected_pts']:.2f} exp pts)")

    except Exception as e:
        return {**state, "error": f"rank_players: {e}", "log": log}

    return {**state, "ranked": ranked, "captain_shortlist": captain_shortlist, "log": log}


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 8 — format_output
# Assembles the final payload the Sporting Director Agent will consume.
# Schema is documented in agents/STATS_AGENT.md
# ═══════════════════════════════════════════════════════════════════════════════

def format_output(state: StatsAgentState) -> StatsAgentState:
    log = state.get("log", [])
    if state.get("error"):
        return state

    log.append(
        f"format_output: Stats Agent complete for GW{state['gameweek']} "
        f"— {len(state['predictions'])} players ranked"
    )
    return {**state, "log": log}


# ═══════════════════════════════════════════════════════════════════════════════
# GRAPH ASSEMBLY
# ═══════════════════════════════════════════════════════════════════════════════

def _should_continue(state: StatsAgentState) -> str:
    """Conditional edge: route to END if any node set an error."""
    return "end" if state.get("error") else "continue"


def build_stats_agent() -> StateGraph:
    """
    Constructs and compiles the Stats Agent graph.

    Nodes (in execution order):
        fetch_live_data          → FPL API / cached bootstrap
        load_player_data         → CSV + bootstrap merge
        engineer_features        → MasterFPLFeatureEngineer pipeline
        run_model                → XGBoost inference
        compute_form_stats       → Last-5 GW rolling stats
        compute_start_probability→ Start % from minutes + availability
        rank_players             → Expected-value ranking by position
        format_output            → Final payload assembly

    Edges:
        Linear pipeline with a conditional error-exit after every node.
    """
    workflow = StateGraph(StatsAgentState)

    # ── Register nodes ────────────────────────────────────────────────────────
    workflow.add_node("fetch_live_data",            fetch_live_data)
    workflow.add_node("load_player_data",           load_player_data)
    workflow.add_node("engineer_features",          engineer_features)
    workflow.add_node("run_model",                  run_model)
    workflow.add_node("compute_form_stats",         compute_form_stats)
    workflow.add_node("compute_start_probability",  compute_start_probability)
    workflow.add_node("rank_players",               rank_players)
    workflow.add_node("format_output",              format_output)

    # ── Entry point ───────────────────────────────────────────────────────────
    workflow.set_entry_point("fetch_live_data")

    # ── Edges (linear with error-exit at each step) ───────────────────────────
    node_sequence = [
        ("fetch_live_data",           "load_player_data"),
        ("load_player_data",          "engineer_features"),
        ("engineer_features",         "run_model"),
        ("run_model",                 "compute_form_stats"),
        ("compute_form_stats",        "compute_start_probability"),
        ("compute_start_probability", "rank_players"),
        ("rank_players",              "format_output"),
    ]

    for src, dst in node_sequence:
        workflow.add_conditional_edges(
            src,
            _should_continue,
            {"continue": dst, "end": END},
        )

    workflow.add_edge("format_output", END)

    return workflow.compile()


# Compiled agent — import this in other modules
stats_agent = build_stats_agent()


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER — run the agent
# ═══════════════════════════════════════════════════════════════════════════════

def run_stats_agent(gameweek: int | None = None, season: str = "2024-25") -> dict:
    """
    Run the Stats Agent for a given gameweek.

    Args:
        gameweek: GW number to predict. None = use latest in data.
        season:   FPL season string, e.g. "2024-25".

    Returns:
        Final StatsAgentState dict with ranked players, form, start probs.

    Example:
        from agents.stats_agent import run_stats_agent
        result = run_stats_agent(gameweek=38)
        top_players = result["ranked"]["ALL"][:10]
    """
    initial_state: StatsAgentState = {
        "gameweek": gameweek,
        "season": season,
        "bootstrap": None,
        "player_df": None,
        "feature_df": None,
        "predictions": None,
        "form_stats": None,
        "start_probs": None,
        "ranked": None,
        "captain_shortlist": None,
        "error": None,
        "log": [],
    }
    return stats_agent.invoke(initial_state)


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    gw = int(sys.argv[1]) if len(sys.argv) > 1 else None
    result = run_stats_agent(gameweek=gw)

    if result["error"]:
        print(f"\nERROR: {result['error']}")
    else:
        print(f"\n{'='*60}")
        print(f"Stats Agent — GW{result['gameweek']} Results")
        print(f"{'='*60}")
        print("\nExecution log:")
        for entry in result["log"]:
            print(f"  • {entry}")

        print(f"\nTop 10 overall (by expected pts):")
        for p in result["ranked"]["ALL"][:10]:
            print(f"  {p['rank']:>2}. {p['name']:<25} {p['position']:<4} "
                  f"pred={p['predicted_pts']:.2f}  "
                  f"start={p['start_prob']:.0%}  "
                  f"exp={p['expected_pts']:.2f}")

        print(f"\nCaptain shortlist:")
        for p in result["captain_shortlist"]:
            print(f"  ★ {p['name']:<25} {p['expected_pts']:.2f} exp pts "
                  f"({p['start_prob']:.0%} start prob)")
