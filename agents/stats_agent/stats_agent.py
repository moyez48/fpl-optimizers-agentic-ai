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
import unicodedata
import requests
from typing import TypedDict, Optional, Any

import numpy as np
import pandas as pd
from langgraph.graph import StateGraph, END

warnings.filterwarnings("ignore")

# ── Paths (relative to repo root) ────────────────────────────────────────────
REPO_ROOT      = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_PATH      = os.path.join(REPO_ROOT, "data", "processed_fpl_data.csv")
MODEL_PATH     = os.path.join(REPO_ROOT, "models", "xgb_history_v2.pkl")
META_PATH      = os.path.join(REPO_ROOT, "models", "xgb_history_v2_metadata.json")
BOOTSTRAP_PATH = os.path.join(REPO_ROOT, "data", "bootstrap_static.json")
ANALYSIS_DIR   = os.path.join(REPO_ROOT, "analysis")

if ANALYSIS_DIR not in sys.path:
    sys.path.insert(0, ANALYSIS_DIR)

FPL_BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_FIXTURES_URL  = "https://fantasy.premierleague.com/api/fixtures/"
FPL_EVENT_LIVE_TMPL = "https://fantasy.premierleague.com/api/event/{}/live/"

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
    fixtures: Optional[list]         # Raw fixtures JSON (all GWs, includes FDR)
    player_df: Optional[Any]         # Raw loaded DataFrame (pd.DataFrame)
    feature_df: Optional[Any]        # Feature-engineered DataFrame

    # ── Outputs ───────────────────────────────────────────────────────────────
    predictions: Optional[list]      # [{name, team, position, predicted_pts, ...}]
    form_stats: Optional[list]       # [{name, form_last5, avg_last5, ...}]
    start_probs: Optional[dict]      # {player_name: float 0-1}
    ranked: Optional[dict]           # {GK: [...], DEF: [...], MID: [...], FWD: [...], ALL: [...]}
    captain_shortlist: Optional[list] # Top 5 captain candidates
    gw_has_actual_scores: Optional[bool]  # True if CSV has scored pts for this GW
    actual_scores_source: Optional[str]   # "fpl_event_live" | "csv_sanitised" | "none"
    dataset_gw_min: Optional[int]
    dataset_gw_max: Optional[int]

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

    # Fetch fixtures for FDR (Fixture Difficulty Rating, 1-5 scale)
    fixtures = []
    try:
        resp = requests.get(FPL_FIXTURES_URL, timeout=10)
        resp.raise_for_status()
        fixtures = resp.json()
        log.append(f"fetch_live_data: pulled {len(fixtures)} fixtures for FDR")
    except Exception as e:
        log.append(f"fetch_live_data: fixtures fetch failed ({e}), FDR unavailable")

    return {**state, "bootstrap": bootstrap, "fixtures": fixtures, "log": log}


def _norm_player_name(s: str) -> str:
    """Unicode-normalise for matching CSV `name` to FPL `web_name`."""
    return unicodedata.normalize("NFKC", (s or "").strip()).casefold()


def fetch_fpl_event_live_points(event_id: int, timeout: float = 20.0) -> dict[int, float]:
    """
    Official per-player gameweek scores from FPL (supports negatives, e.g. -1).

    GET /api/event/{event_id}/live/ → elements[].stats.total_points
    """
    url = FPL_EVENT_LIVE_TMPL.format(int(event_id))
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return {}
    out: dict[int, float] = {}
    for row in data.get("elements") or []:
        eid = row.get("id")
        st = row.get("stats") or {}
        if eid is None:
            continue
        tp = st.get("total_points")
        if tp is None:
            continue
        try:
            out[int(eid)] = float(tp)
        except (TypeError, ValueError):
            continue
    return out


# Single-gameweek scores only (FPL live is authoritative). CSV rows sometimes carry
# season/cumulative totals in `total_points` after merges — those must not pass as "this GW".
_SINGLE_GW_ACTUAL_MIN = -25.0
_SINGLE_GW_ACTUAL_MAX = 30.0


def _actual_points_from_csv_fallback(series: pd.Series) -> pd.Series:
    """
    Use CSV `total_points` only when FPL /event/{{gw}}/live/ is unavailable.

    Tight bounds reject season aggregates (e.g. 82) mistaken for one week.
    """
    ap = pd.to_numeric(series, errors="coerce")
    ap = ap.where((ap >= _SINGLE_GW_ACTUAL_MIN) & (ap <= _SINGLE_GW_ACTUAL_MAX))
    return ap


def _enrich_predictions_with_bootstrap(
    pred_df: pd.DataFrame,
    bootstrap: dict | None,
    log: list,
) -> pd.DataFrame:
    """
    Some processed CSV rows have missing element/team/position.  Reconcile from
    live bootstrap (web_name → id, team id → name, element_type → GK/DEF/MID/FWD).
    Drops rows that still cannot be placed in a legal position bucket.
    """
    if bootstrap is None or pred_df.empty:
        return pred_df

    TEAM_MAP = {t["id"]: t["name"] for t in bootstrap.get("teams", [])}
    POS_MAP = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}

    by_norm_web: dict[str, list[int]] = {}
    by_last: dict[str, list[tuple[str, int]]] = {}
    for el in bootstrap.get("elements", []):
        eid = el.get("id")
        wn = (el.get("web_name") or "").strip()
        if eid is None or not wn:
            continue
        eid = int(eid)
        key = _norm_player_name(wn)
        by_norm_web.setdefault(key, []).append(eid)
        parts = wn.split()
        if parts:
            by_last.setdefault(_norm_player_name(parts[-1]), []).append((wn, eid))

    df = pred_df.copy()

    def _needs_element(row) -> bool:
        el = row.get("element")
        if el is None:
            return True
        try:
            if isinstance(el, float) and np.isnan(el):
                return True
        except TypeError:
            pass
        return el == 0

    resolved = 0
    for idx in df.index:
        row = df.loc[idx]
        if not _needs_element(row):
            continue
        name_raw = row.get("name")
        name_key = _norm_player_name(str(name_raw) if name_raw is not None else "")
        if not name_key:
            continue

        eid = None
        if name_key in by_norm_web and len(by_norm_web[name_key]) == 1:
            eid = by_norm_web[name_key][0]
        else:
            parts = str(name_raw).split()
            if parts:
                cand = by_last.get(_norm_player_name(parts[-1]), [])
                if len(cand) == 1:
                    eid = cand[0][1]
                elif len(cand) > 1:
                    nraw = str(name_raw).replace(" ", "").casefold()
                    for wn, cid in cand:
                        wfold = wn.replace(" ", "").casefold()
                        if nraw in wfold or wfold.startswith(nraw):
                            eid = cid
                            break
                    if eid is None:
                        eid = cand[0][1]
        if eid is not None:
            df.at[idx, "element"] = eid
            resolved += 1

    elem_to_team: dict[int, str] = {}
    elem_to_pos: dict[int, str] = {}
    for el in bootstrap.get("elements", []):
        eid = el.get("id")
        if eid is None:
            continue
        eid = int(eid)
        elem_to_team[eid] = TEAM_MAP.get(el.get("team"), "")
        elem_to_pos[eid] = POS_MAP.get(el.get("element_type"), "")

    filled_tp = 0
    for idx in df.index:
        try:
            eid = int(df.at[idx, "element"])
        except (ValueError, TypeError):
            continue
        if eid not in elem_to_pos:
            continue
        if "team" in df.columns:
            tv = df.at[idx, "team"]
            if pd.isna(tv) or str(tv).strip() == "":
                df.at[idx, "team"] = elem_to_team.get(eid, "")
                filled_tp += 1
        if "position" in df.columns:
            pv = df.at[idx, "position"]
            if pd.isna(pv) or str(pv).strip() == "":
                df.at[idx, "position"] = elem_to_pos.get(eid, "")
                filled_tp += 1

    # Align rare CSV codes with model buckets (GKP/AM → GK/MID)
    if "position" in df.columns:
        pr = df["position"].astype(str)
        is_gkp = pr.str.upper().str.strip() == "GKP"
        is_am = pr.str.upper().str.strip() == "AM"
        df.loc[is_gkp, "position"] = "GK"
        df.loc[is_am, "position"] = "MID"

    before = len(df)
    df = df[df["element"].notna()]
    df = df[df["element"] != 0]
    df = df[df["position"].isin(list(POS_MAP.values()))]
    dropped = before - len(df)
    if resolved or filled_tp or dropped:
        log.append(
            f"run_model: bootstrap enrich — matched {resolved} element IDs, "
            f"filled {filled_tp} team/position fields, dropped {dropped} invalid rows"
        )
    return df


def _patch_preds_identity_from_bootstrap(
    preds: pd.DataFrame,
    bootstrap: dict | None,
) -> pd.DataFrame:
    """
    Last-chance fill of element / team / position / name before ranking.

    Cached runs or edge-case CSV rows can still leave these null after run_model;
    without position the per-position ranked lists are empty and the React app
    shows no players.
    """
    if bootstrap is None or preds.empty:
        return preds

    TEAM_MAP = {t["id"]: t["name"] for t in bootstrap.get("teams", [])}
    POS_MAP = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
    elements = bootstrap.get("elements", [])

    by_norm_web: dict[str, list[int]] = {}
    by_last: dict[str, list[tuple[str, int]]] = {}
    for el in elements:
        eid = el.get("id")
        wn = (el.get("web_name") or "").strip()
        if eid is None or not wn:
            continue
        eid = int(eid)
        by_norm_web.setdefault(_norm_player_name(wn), []).append(eid)
        parts = wn.split()
        if parts:
            by_last.setdefault(_norm_player_name(parts[-1]), []).append((wn, eid))

    elem_full = {int(el["id"]): el for el in elements if el.get("id") is not None}
    out = preds.copy()

    def _resolve_eid_from_name(name_raw: Any) -> int | None:
        name_key = _norm_player_name(str(name_raw) if name_raw is not None else "")
        if not name_key:
            return None
        if name_key in by_norm_web and len(by_norm_web[name_key]) == 1:
            return by_norm_web[name_key][0]
        parts = str(name_raw).split()
        if not parts:
            return None
        cand = by_last.get(_norm_player_name(parts[-1]), [])
        if len(cand) == 1:
            return cand[0][1]
        if len(cand) > 1:
            nraw = str(name_raw).replace(" ", "").casefold()
            for wn, cid in cand:
                wfold = wn.replace(" ", "").casefold()
                if nraw in wfold or wfold.startswith(nraw):
                    return cid
            return cand[0][1]
        return None

    for idx in out.index:
        # Existing element → fill team/position/name from bootstrap
        el_raw = out.at[idx, "element"] if "element" in out.columns else None
        eid: int | None = None
        if el_raw is not None and not (isinstance(el_raw, float) and np.isnan(el_raw)):
            try:
                eid = int(float(el_raw))
                out.at[idx, "element"] = eid
            except (ValueError, TypeError):
                eid = None
        if eid is not None and eid in elem_full:
            bel = elem_full[eid]
            if "team" in out.columns:
                tv = out.at[idx, "team"]
                if pd.isna(tv) or str(tv).strip() == "":
                    out.at[idx, "team"] = TEAM_MAP.get(bel.get("team"), "")
            if "position" in out.columns:
                pv = out.at[idx, "position"]
                if pd.isna(pv) or str(pv).strip() == "":
                    out.at[idx, "position"] = POS_MAP.get(bel.get("element_type"), "")
            if "name" in out.columns:
                nv = out.at[idx, "name"]
                if pd.isna(nv) or str(nv).strip() == "":
                    out.at[idx, "name"] = bel.get("web_name", nv)

        # Still missing element → resolve from name
        el2 = out.at[idx, "element"] if "element" in out.columns else None
        need_el = el2 is None or (isinstance(el2, float) and np.isnan(el2)) or el2 == 0
        if need_el and "name" in out.columns:
            resolved = _resolve_eid_from_name(out.at[idx, "name"])
            if resolved is not None:
                out.at[idx, "element"] = resolved
                bel = elem_full.get(resolved)
                if bel:
                    if "team" in out.columns:
                        tv = out.at[idx, "team"]
                        if pd.isna(tv) or str(tv).strip() == "":
                            out.at[idx, "team"] = TEAM_MAP.get(bel.get("team"), "")
                    if "position" in out.columns:
                        pv = out.at[idx, "position"]
                        if pd.isna(pv) or str(pv).strip() == "":
                            out.at[idx, "position"] = POS_MAP.get(bel.get("element_type"), "")

    if "position" in out.columns:
        pr = out["position"].astype(str)
        out.loc[pr.str.upper().str.strip() == "GKP", "position"] = "GK"
        out.loc[pr.str.upper().str.strip() == "AM", "position"] = "MID"

    return out


def _assign_fpl_identity_from_element(preds: pd.DataFrame, bootstrap: dict | None) -> pd.DataFrame:
    """
    Set position (and missing team/name) from FPL bootstrap using element id.

    element_type in bootstrap is the source of truth for GK/DEF/MID/FWD, so
    per-position ranked lists match real roles even when the CSV left position blank.
    """
    if bootstrap is None or preds.empty or "element" not in preds.columns:
        return preds

    POS_MAP = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
    TEAM_MAP = {t["id"]: t["name"] for t in bootstrap.get("teams", [])}
    by_el = {
        int(el["id"]): el
        for el in bootstrap.get("elements", [])
        if el.get("id") is not None
    }

    out = preds.copy()
    for idx in out.index:
        try:
            er = out.at[idx, "element"]
            if er is None or (isinstance(er, float) and np.isnan(er)):
                continue
            eid = int(float(er))
        except (ValueError, TypeError):
            continue

        bel = by_el.get(eid)
        if not bel:
            continue

        pos = POS_MAP.get(bel.get("element_type"))
        if pos:
            out.at[idx, "position"] = pos

        if "team" in out.columns:
            tv = out.at[idx, "team"]
            if pd.isna(tv) or str(tv).strip() == "":
                out.at[idx, "team"] = TEAM_MAP.get(bel.get("team"), "")

        if "name" in out.columns:
            nv = out.at[idx, "name"]
            if pd.isna(nv) or str(nv).strip() == "":
                out.at[idx, "name"] = bel.get("web_name", nv)

    return out


def _value_m_from_bootstrap_row(element: Any, raw_value: Any, bs_by_id: dict[int, dict]) -> float:
    """£m price: prefer live bootstrap now_cost; else infer from CSV value column."""
    try:
        eid = int(element) if element is not None and not (isinstance(element, float) and np.isnan(element)) else None
    except (ValueError, TypeError):
        eid = None
    if eid is not None and eid in bs_by_id:
        nc = bs_by_id[eid].get("now_cost")
        if nc is not None:
            return round(float(nc) / 10.0, 1)
    if raw_value is None or (isinstance(raw_value, float) and np.isnan(raw_value)):
        return 0.0
    v = float(raw_value)
    # FPL-style tenths (e.g. 55 → £5.5m) vs already-in-millions floats
    if v >= 25.0:
        return round(v / 10.0, 1)
    return round(v, 1)


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

        # Build team name and position lookups from bootstrap
        team_map = {t["id"]: t["name"] for t in state["bootstrap"].get("teams", [])}
        pos_map  = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}

        # Build bs_merge as an explicit copy to avoid SettingWithCopyWarning
        bs_merge = bs_elements[[
            "id", "status", "chance_of_playing_next_round",
            "chance_of_playing_this_round", "ep_next",
            "penalties_order", "direct_freekicks_order",
            "corners_and_indirect_freekicks_order",
            "team", "element_type",
        ]].copy().rename(columns={"id": "element"})

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

        # ── Merge FDR from fixtures API ───────────────────────────────────────
        fixtures = state.get("fixtures") or []
        if fixtures:
            team_map = {t["id"]: t["name"] for t in state["bootstrap"].get("teams", [])}
            fdr_rows = []
            for fx in fixtures:
                gw = fx.get("event")
                if gw is None:
                    continue
                fdr_rows.append({"team": team_map.get(fx["team_h"], ""), "GW": gw,
                                 "fdr": fx.get("team_h_difficulty", 3)})
                fdr_rows.append({"team": team_map.get(fx["team_a"], ""), "GW": gw,
                                 "fdr": fx.get("team_a_difficulty", 3)})
            if fdr_rows:
                fdr_df = pd.DataFrame(fdr_rows).drop_duplicates(subset=["team", "GW"])
                if "fdr" in df.columns:
                    df = df.drop(columns=["fdr"])
                df = df.merge(fdr_df, on=["team", "GW"], how="left")
                df["fdr"] = df["fdr"].fillna(3)
                log.append(f"load_player_data: merged FDR for {len(fdr_df)} team-GW fixtures")
        else:
            if "fdr" not in df.columns:
                df["fdr"] = 3
            log.append("load_player_data: no fixtures data, FDR defaulted to 3")

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

        # Drop columns that MasterFPLFeatureEngineer creates via DataFrame.merge()
        # internally.  If those columns already exist in the CSV (because
        # update_data.py ran MasterFPLFeatureEngineer and saved all columns),
        # pandas creates _x/_y suffixes after the merge and the original column
        # name disappears — causing a KeyError on the very next line inside the
        # engineer.  Dropping them here lets the engineer recreate them cleanly.
        _merge_created = [
            "opponent_strength",           # add_fixture_difficulty_elo
            "opponent_team_name",          # intermediate used by elo + defensive merges
            "team_total_points_last_gw",   # add_teammate_synergy
            "team_goals_last_3",           # add_attacking_features
            "team_xG_last_3",              # add_attacking_features
            "team_cs_rate_last_3",         # add_defensive_features
            "team_cs_rate_last_5",         # add_defensive_features
            "opponent_xGC_last_3",         # add_defensive_features
            "opponent_xGC_last_5",         # add_defensive_features
        ]
        df = df.drop(columns=[c for c in _merge_created if c in df.columns])

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

        season = state["season"]
        sdf = df[df["season"] == season]
        gw_min = int(sdf["GW"].min()) if len(sdf) else None
        gw_max = int(sdf["GW"].max()) if len(sdf) else None

    except Exception as e:
        return {**state, "error": f"engineer_features: {e}", "log": log}

    return {
        **state,
        "feature_df": df,
        "dataset_gw_min": gw_min,
        "dataset_gw_max": gw_max,
        "log": log,
    }


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

        if pred_df.empty:
            mx = int(season_df["GW"].max()) if len(season_df) else 0
            return {
                **state,
                "error": (
                    f"run_model: no feature rows for {season} GW{target_gw}. "
                    f"Dataset currently has GW1–GW{mx}. "
                    f"Refresh processed data to add this gameweek, or pick GW1–GW{mx}."
                ),
                "log": log,
            }

        # Fill any missing features with 0 (conservative default)
        missing = [f for f in FEATURES if f not in pred_df.columns]
        for col in missing:
            pred_df[col] = 0.0
        if missing:
            log.append(f"run_model: filled {len(missing)} missing features with 0: {missing}")

        X = pred_df[FEATURES].fillna(0)
        pred_df["predicted_pts"] = model.predict(X)

        pred_df = _enrich_predictions_with_bootstrap(pred_df, state.get("bootstrap"), log)

        # Keep useful output columns
        keep = ["name", "team", "position", "value", "predicted_pts",
                "ep_next", "fdr", "total_points", "GW", "was_home", "element"]
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
# Splits into position groups; ALL + each position list is complete (every player).
# ═══════════════════════════════════════════════════════════════════════════════

def rank_players(state: StatsAgentState) -> StatsAgentState:
    log = state.get("log", [])
    if state.get("error"):
        return state

    actual_scores_source = "none"
    try:
        preds  = pd.DataFrame(state["predictions"])
        preds  = _patch_preds_identity_from_bootstrap(preds, state.get("bootstrap"))
        form   = pd.DataFrame(state["form_stats"]) if state["form_stats"] else pd.DataFrame()
        probs  = state["start_probs"] or {}

        # Merge form stats
        if not form.empty:
            preds = preds.merge(form[["name", "avg_pts_last5", "form_trend",
                                      "goals_last5", "assists_last5"]], on="name", how="left")

        # Add start probability and expected value
        preds["start_prob"]    = preds["name"].map(probs).fillna(0.7)
        preds["expected_pts"]  = (preds["predicted_pts"] * preds["start_prob"]).round(3)
        bs_by_id = {
            int(el["id"]): el
            for el in (state.get("bootstrap") or {}).get("elements", [])
            if el.get("id") is not None
        }
        if "value" in preds.columns:
            preds["value_m"] = preds.apply(
                lambda r: _value_m_from_bootstrap_row(r.get("element"), r.get("value"), bs_by_id),
                axis=1,
            )
        else:
            preds["value_m"] = preds.apply(
                lambda r: _value_m_from_bootstrap_row(r.get("element"), None, bs_by_id),
                axis=1,
            )

        # Authoritative GK/DEF/MID/FWD from FPL element_type (fixes blank CSV + UI buckets)
        preds = _assign_fpl_identity_from_element(preds, state.get("bootstrap"))

        # Realised points: prefer official FPL /api/event/{gw}/live/ (supports negatives, e.g. -1).
        # Gap-fill from CSV only where FPL has no value; CSV is loosely sanitised (drops absurd values).
        gw_id = int(state["gameweek"])
        fpl_live = fetch_fpl_event_live_points(gw_id)
        el = pd.to_numeric(preds["element"], errors="coerce")

        def _fpl_lookup(e: Any) -> float:
            if pd.isna(e):
                return np.nan
            try:
                return float(fpl_live.get(int(float(e)), np.nan))
            except (TypeError, ValueError):
                return np.nan

        ap = el.apply(_fpl_lookup) if len(fpl_live) > 0 else pd.Series(np.nan, index=preds.index)
        actual_scores_source = "fpl_event_live" if len(fpl_live) > 0 else "none"

        if "total_points" in preds.columns:
            csv_ap = _actual_points_from_csv_fallback(preds["total_points"])
            if len(fpl_live) == 0:
                ap = csv_ap
                actual_scores_source = "csv_sanitised"
            # When live exists, do NOT combine_first from CSV: gap-fill was mixing
            # official GW totals with bad merged season/cumulative values (e.g. 82, 50).
            # Missing FPL rows stay NaN (wrong element id, etc.).

        preds["actual_points"] = ap
        gw_has_actual = bool(preds["actual_points"].notna().any())
        log.append(
            f"rank_players: actual_scores_source={actual_scores_source} "
            f"(FPL keys={len(fpl_live)})"
        )

        # Sort by expected_pts descending
        preds = preds.sort_values("expected_pts", ascending=False).reset_index(drop=True)
        preds["rank"] = preds.index + 1

        def _pos_records(code: str) -> list:
            sub = preds[preds["position"] == code].sort_values(
                "expected_pts", ascending=False
            )
            return sub.to_dict("records")

        ranked = {
            "ALL": preds.to_dict("records"),
            "GK":  _pos_records("GK"),
            "DEF": _pos_records("DEF"),
            "MID": _pos_records("MID"),
            "FWD": _pos_records("FWD"),
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

    return {
        **state,
        "ranked": ranked,
        "captain_shortlist": captain_shortlist,
        "gw_has_actual_scores": gw_has_actual,
        "actual_scores_source": actual_scores_source,
        "log": log,
    }


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

def _detect_current_season() -> str:
    """
    Detect the current FPL season from the calendar date.

    FPL seasons run August → May.  The convention is 'YYYY-(YYYY+1)':
      - Aug–Dec YYYY  →  'YYYY-(YYYY+1)'   e.g. Aug 2025 → '2025-26'
      - Jan–Jul YYYY  →  '(YYYY-1)-YYYY'   e.g. Mar 2026 → '2025-26'

    Falls back to checking which seasons exist in the CSV as a safety net.
    """
    from datetime import date
    today = date.today()
    if today.month >= 8:
        start_year = today.year
    else:
        start_year = today.year - 1
    season = f"{start_year}-{str(start_year + 1)[-2:]}"

    # Safety check: confirm this season exists in the CSV; fall back if not
    try:
        df = pd.read_csv(DATA_PATH, usecols=["season"])
        available = df["season"].unique().tolist()
        if season not in available:
            # Most recent season in the CSV as fallback
            season = sorted(available)[-1]
    except Exception:
        pass

    return season


def run_stats_agent(gameweek: int | None = None, season: str | None = None) -> dict:
    """
    Run the Stats Agent for a given gameweek.

    Args:
        gameweek: GW number to predict. None = use latest in data.
        season:   FPL season string, e.g. '2025-26'. None = auto-detect
                  from the CSV (picks the season with the highest GW).

    Returns:
        Final StatsAgentState dict with ranked players, form, start probs.

    Example:
        from agents.stats_agent import run_stats_agent
        result = run_stats_agent()          # fully auto-detected
        result = run_stats_agent(gameweek=30)
        top_players = result["ranked"]["ALL"][:10]
    """
    if season is None:
        season = _detect_current_season()

    initial_state: StatsAgentState = {
        "gameweek": gameweek,
        "season": season,
        "bootstrap": None,
        "fixtures": None,
        "player_df": None,
        "feature_df": None,
        "predictions": None,
        "form_stats": None,
        "start_probs": None,
        "ranked": None,
        "captain_shortlist": None,
        "gw_has_actual_scores": None,
        "actual_scores_source": None,
        "dataset_gw_min": None,
        "dataset_gw_max": None,
        "error": None,
        "log": [],
    }
    return stats_agent.invoke(initial_state)


# ═══════════════════════════════════════════════════════════════════════════════
# GRAPH VERIFICATION — run this file directly to smoke-test the full pipeline
#
#   python agents/stats_agent/stats_agent.py
#
# What this block does:
#   1. Builds the mock initial state (the same dict structure every LangGraph
#      node reads from and writes to).
#   2. Invokes the compiled stats_agent graph so every node executes in order:
#      fetch_live_data → load_player_data → engineer_features → run_model
#      → compute_form_stats → compute_start_probability → rank_players
#      → format_output
#   3. Finds the target player (element ID 355) in the final ranked output.
#   4. Prints the three verification fields:
#        • expected_pts        — our model's risk-adjusted prediction
#                                (predicted_pts × start_probability)
#        • expected_pts_xP     — FPL's own ep_next signal from bootstrap
#                                (cross-check: should directionally agree)
#        • start_probability   — blended signal (recent starts + availability
#                                + avg minutes) computed in Node 6
#        • status_summary      — human-readable availability string derived
#                                from the FPL bootstrap status field
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    # ── Which player and gameweek to inspect ──────────────────────────────────
    # Element 355 is a highly-owned player in the FPL dataset.
    # Change TARGET_ELEMENT to any player's FPL element ID, or pass a GW
    # on the command line:  python stats_agent.py 32
    TARGET_ELEMENT = 355
    TARGET_SEASON  = "2024-25"   # matches the backend default; 2025-26 data has a
                                  # column-conflict in add_fixture_difficulty_elo

    import sys
    gw_arg = int(sys.argv[1]) if len(sys.argv) > 1 else None

    # ── Step 1: build the initial state ───────────────────────────────────────
    # This is the exact dict that LangGraph passes into Node 1 (fetch_live_data).
    # Every key in StatsAgentState must be present — None is the safe default
    # for anything the graph will populate itself.
    initial_state: StatsAgentState = {
        "gameweek":         gw_arg,        # None → agent uses latest GW in CSV
        "season":           TARGET_SEASON,
        # The fields below are all None at start — each graph node fills them in
        "bootstrap":        None,          # populated by fetch_live_data
        "fixtures":         None,          # populated by fetch_live_data (FDR)
        "player_df":        None,          # populated by load_player_data
        "feature_df":       None,          # populated by engineer_features
        "predictions":      None,          # populated by run_model
        "form_stats":       None,          # populated by compute_form_stats
        "start_probs":      None,          # populated by compute_start_probability
        "ranked":           None,          # populated by rank_players
        "captain_shortlist": None,         # populated by rank_players
        "gw_has_actual_scores": None,      # populated by rank_players
        "error":            None,          # set by any node on failure
        "log":              [],            # append-only execution trace
    }

    print("\n" + "=" * 62)
    print("  STATS AGENT — GRAPH VERIFICATION RUN")
    print("=" * 62)
    print(f"  Target player : element ID {TARGET_ELEMENT}")
    print(f"  Season        : {TARGET_SEASON}")
    print(f"  Gameweek      : {gw_arg or 'auto-detect (latest in CSV)'}")
    print("=" * 62)

    # ── Step 2: invoke the compiled LangGraph agent ───────────────────────────
    # stats_agent is the compiled graph built by build_stats_agent() above.
    # .invoke() runs the full 8-node pipeline synchronously and returns the
    # final state dict after format_output completes (or after the first node
    # that sets state["error"]).
    print("\n[Running graph — this takes ~30-60s for feature engineering]\n")
    final_state = stats_agent.invoke(initial_state)

    # ── Step 3: check for pipeline errors ────────────────────────────────────
    if final_state.get("error"):
        print(f"\n[FAILED]  PIPELINE ERROR in node:\n    {final_state['error']}")
        print("\nExecution log up to failure:")
        for entry in final_state["log"]:
            print(f"  • {entry}")
        sys.exit(1)

    # ── Step 4: print the execution trace ────────────────────────────────────
    print(f"[OK] Graph completed for GW{final_state['gameweek']}\n")
    print("Execution log (one entry per node):")
    for entry in final_state["log"]:
        print(f"  • {entry}")

    # ── Step 5: locate element 355 in the ranked output ──────────────────────
    # ranked["ALL"] is a list of dicts sorted by expected_pts descending.
    # We search by element ID (the FPL unique player identifier) which is
    # more stable than name (players can change clubs and names can vary).
    all_players = final_state["ranked"]["ALL"]

    target = next(
        (p for p in all_players if p.get("element") == TARGET_ELEMENT),
        None,
    )

    # Fallback: if element 355 isn't in the top-50 ranked list, check the
    # raw predictions list which covers ALL players in the target GW.
    if target is None:
        target = next(
            (p for p in final_state["predictions"]
             if p.get("element") == TARGET_ELEMENT),
            None,
        )

    # ── Step 6: build status_summary from bootstrap ───────────────────────────
    # The bootstrap "elements" list has a "status" field:
    #   "a" = available, "d" = doubtful, "i" = injured,
    #   "s" = suspended, "u" = unavailable, "n" = not in squad
    STATUS_LABELS = {
        "a": "[OK]  Available",
        "d": "[!!]  Doubtful",
        "i": "[X]   Injured",
        "s": "[X]   Suspended",
        "u": "[X]   Unavailable",
        "n": "[-]   Not in squad",
    }

    bs_elements = {
        el["id"]: el
        for el in final_state["bootstrap"]["elements"]
    }
    bs_player = bs_elements.get(TARGET_ELEMENT, {})

    raw_status   = bs_player.get("status", "?")
    chance       = bs_player.get("chance_of_playing_next_round")
    ep_next      = bs_player.get("ep_next", "N/A")     # FPL's own xP signal
    player_name  = bs_player.get("web_name", f"Element {TARGET_ELEMENT}")

    status_label = STATUS_LABELS.get(raw_status, f"Unknown ({raw_status})")
    chance_str   = f"{chance}% chance of playing" if chance is not None else "No fitness flag"
    status_summary = f"{status_label} — {chance_str}"

    # ── Step 7: print the three verification fields ───────────────────────────
    print(f"\n{'=' * 62}")
    print(f"  PLAYER REPORT  —  {player_name}  (element {TARGET_ELEMENT})")
    print(f"{'=' * 62}")

    if target:
        # start_prob and expected_pts exist on ranked["ALL"] entries but may be
        # absent when target was found in the raw predictions fallback.
        # Look them up directly from the agent's state dicts in that case.
        start_prob = target.get("start_prob")
        if start_prob is None:
            start_prob = final_state["start_probs"].get(target.get("name"))

        expected_pts = target.get("expected_pts")
        if expected_pts is None and start_prob is not None:
            raw_pred = target.get("predicted_pts")
            expected_pts = round(raw_pred * start_prob, 3) if raw_pred else "N/A"

        start_prob_str  = f"{start_prob:.0%}" if isinstance(start_prob, float) else "N/A"
        expected_pts_str = f"{expected_pts:.3f}" if isinstance(expected_pts, float) else str(expected_pts)
        pred_pts_raw     = target.get('predicted_pts')
        pred_pts_str     = f"{pred_pts_raw:.3f}" if isinstance(pred_pts_raw, float) else "N/A"

        print(f"\n  {'expected_pts':<28}  {expected_pts_str}")
        print(f"  {'expected_pts_xP (FPL ep_next)':<28}  {ep_next}")
        print(f"  {'start_probability':<28}  {start_prob_str}")
        print(f"  {'status_summary':<28}  {status_summary}")
        print(f"\n  --- supporting detail ---")
        print(f"  {'predicted_pts (raw model)':<28}  {pred_pts_str}")
        print(f"  {'position':<28}  {target.get('position', 'N/A')}")
        print(f"  {'team':<28}  {target.get('team', 'N/A')}")
        print(f"  {'value_m (price £m)':<28}  {target.get('value_m', 'N/A')}")
        print(f"  {'avg_pts_last5':<28}  {target.get('avg_pts_last5', 'N/A')}")
        print(f"  {'overall rank':<28}  #{target.get('rank', 'outside top-50')}")
    else:
        # Player exists in bootstrap but had no data rows in the target GW
        print(f"\n  [!!] element {TARGET_ELEMENT} ({player_name}) was not found in")
        print(f"     the GW{final_state['gameweek']} prediction set.")
        print(f"     They may not have had a fixture this gameweek.\n")
        print(f"  {'expected_pts_xP (FPL ep_next)':<28}  {ep_next}")
        print(f"  {'status_summary':<28}  {status_summary}")

    # ── Step 8: captain shortlist (sanity check on ranking quality) ───────────
    print(f"\n{'=' * 62}")
    print("  CAPTAIN SHORTLIST (top 5 by expected pts, start prob >= 70%)")
    print(f"{'=' * 62}")
    for p in final_state["captain_shortlist"]:
        marker = "<-- TARGET" if p.get("element") == TARGET_ELEMENT else ""
        print(
            f"  * {p['name']:<24} "
            f"exp={p['expected_pts']:.2f}  "
            f"start={p['start_prob']:.0%}  "
            f"{marker}"
        )

    print(f"\n{'=' * 62}\n")
