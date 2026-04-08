"""
backend/main.py
===============
FastAPI server that bridges the React frontend to the LangGraph Stats Agent.

Routes
------
  GET  /health                        — liveness check
  POST /api/stats                     — full ranked player list for a GW
  GET  /api/predict/{player_id}       — single-player prediction by FPL element ID

Architecture note — why /api/predict doesn't call graph.invoke({"player_id": …})
----------------------------------------------------------------------------------
The Stats Agent graph was designed as a BATCH pipeline: it processes every
player in the dataset for a given gameweek and returns a ranked list of ~800
players.  It is not designed to accept a single player_id as input.

The correct pattern is:
    1. Run the full graph once (graph.invoke(full_initial_state))   → ~60 s
    2. Cache the result in memory for the current GW
    3. For /api/predict/{player_id}, filter the cached result        → <1 ms

This means the first request per gameweek is slow (graph runs); every
subsequent request — for any player — is instant.  The cache is keyed on
(season, gameweek) so it automatically invalidates when a new GW starts.

Run the server
--------------
    uvicorn backend.main:app --host 0.0.0.0 --port 8006 --reload
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ── Resolve repo root so agents/ and analysis/ are importable ─────────────────
# backend/main.py lives at  <repo_root>/backend/main.py
# dirname(__file__)          → <repo_root>/backend/
# dirname(dirname(__file__)) → <repo_root>/
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# ── Import the compiled LangGraph graph and the convenience runner ─────────────
# The graph lives at agents/stats_agent/stats_agent.py.
# We import both:
#   • stats_agent  — the compiled StateGraph object (used for graph.invoke())
#   • run_stats_agent — thin wrapper that builds the initial state and calls invoke()
from agents.stats_agent.stats_agent import (   # noqa: E402
    stats_agent as graph,
    run_stats_agent,
)
from agents.sporting_director import run_sporting_director   # noqa: E402
from agents.sporting_director.schemas import Squad, PlayerProfile  # noqa: E402
from agents.manager_agent import run_manager_agent  # noqa: E402

# ── App setup ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="FPL Stats Agent API",
    description="LangGraph-powered FPL point prediction backend.",
    version="1.0.0",
)

# CORS — allow all the Vite dev-server ports the frontend might use
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # default Vite port (and the one you specified)
        "http://localhost:5174",   # Vite fallback ports
        "http://localhost:5175",
        "http://localhost:5176",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Numpy serializer ──────────────────────────────────────────────────────────
# pandas .to_dict("records") can leave numpy int64/float64 types in the output.
# Python's built-in json.dumps() chokes on those — this encoder converts them
# to plain Python int/float so JSONResponse can serialise them cleanly.
def _sanitize(obj):
    """
    Recursively walk a nested dict/list and replace any non-JSON-safe values:
      - numpy int/float  → Python int/float
      - NaN / Inf        → None  (JSON null)
      - numpy arrays     → list
    This handles both numpy scalar types AND native Python float('nan') that
    pandas produces when converting DataFrames with missing values to dicts.
    """
    import math
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        f = float(obj)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(obj, np.ndarray):
        return [_sanitize(v) for v in obj.tolist()]
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    return obj


def _to_json(payload: dict) -> JSONResponse:
    """Serialize a dict (potentially containing numpy/NaN types) to JSONResponse."""
    return JSONResponse(content=_sanitize(payload))


def _form_by_name(form_stats: list) -> dict[str, Any]:
    return {f["name"]: f for f in (form_stats or []) if f.get("name")}


def _merge_player_form(player_data: dict, form_by_name: dict) -> dict:
    form = form_by_name.get(player_data.get("name", ""), {})
    return {
        **player_data,
        "avg_pts_last5": form.get("avg_pts_last5", player_data.get("avg_pts_last5", 0.0)),
        "form_trend": form.get("form_trend", player_data.get("form_trend", 0.0)),
        "goals_last5": form.get("goals_last5", player_data.get("goals_last5", 0)),
        "assists_last5": form.get("assists_last5", player_data.get("assists_last5", 0)),
    }


def _row_to_manager_player(merged: dict) -> dict:
    tp5 = merged.get("total_pts_last5")
    if tp5 is None:
        tp5 = float(merged.get("avg_pts_last5", 0) or 0) * 5.0
    else:
        tp5 = float(tp5)
    return {
        "id": int(merged["element"]),
        "name": merged.get("name", ""),
        "position": merged.get("position"),
        "team": merged.get("team") or "—",
        "price": float(merged.get("value_m") or 0),
        "xP": float(merged.get("expected_pts", merged.get("predicted_pts", 0))),
        "xP_5gw": round(tp5, 1),
    }


def _squad_for_manager_agent(result: dict, player_ids: list[int]) -> list[dict]:
    """Map 15 FPL element IDs → Manager Agent squad dicts (xP = expected_pts)."""
    all_ranked = result.get("ranked", {}).get("ALL", [])
    predictions = result.get("predictions", [])
    form_by_name = _form_by_name(result.get("form_stats", []))
    ranked_by_element = _by_element(all_ranked)
    predictions_by_element = _by_element(predictions)
    out: list[dict] = []
    for pid in player_ids:
        base = ranked_by_element.get(pid) or predictions_by_element.get(pid)
        if base is None:
            continue
        merged = _merge_player_form(base, form_by_name)
        out.append(_row_to_manager_player(merged))
    return out


def _by_element(rows: list) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for p in rows:
        e = p.get("element")
        if e is not None:
            out[int(e)] = p
    return out


# ── In-memory GW cache ────────────────────────────────────────────────────────
# Running the full Stats Agent graph takes ~60 seconds (feature engineering +
# XGBoost inference over 45k rows).  We don't want every call to
# /api/predict/{player_id} to trigger a fresh run.
#
# The cache stores the last agent result keyed by (season, gameweek).  When a
# request comes in for the same season + GW, we return the cached result
# instantly.  A new GW or season automatically busts the cache.
#
# Structure:
#   _cache["key"]    → "2024-25__38"          (the cache key)
#   _cache["result"] → full StatsAgentState dict
#   _cache["ts"]     → Unix timestamp of when the result was cached

_cache: dict[str, Any] = {"key": None, "result": None, "ts": 0.0}

# Maximum age of a cached result in seconds.
# 3600 s = 1 hour.  After this the graph re-runs even for the same GW,
# which picks up any live bootstrap changes (injury updates etc.).
_CACHE_TTL = 3600

# Bump when the /api/stats response schema changes so stale cached payloads
# (e.g. missing actual_points) are not served.
_CACHE_SCHEMA_VER = "20250409a"


def _get_or_run_agent(season: str, gameweek: int | None) -> dict:
    """
    Return a cached agent result if available and fresh, otherwise run the
    full graph and cache the result.

    Parameters
    ----------
    season   : FPL season string, e.g. "2024-25"
    gameweek : Target GW number, or None (agent will auto-detect latest).

    Returns
    -------
    dict
        The final StatsAgentState produced by the graph.

    Raises
    ------
    HTTPException(502)
        If the graph returns an error (e.g. FPL API unreachable, missing model).
    """
    cache_key = f"{_CACHE_SCHEMA_VER}__{season}__{gameweek}"
    now = time.time()

    # Cache hit: same season+GW and result is still within TTL
    if (
        _cache["key"] == cache_key
        and _cache["result"] is not None
        and (now - _cache["ts"]) < _CACHE_TTL
    ):
        return _cache["result"]

    # Cache miss: run the full 8-node LangGraph pipeline.
    # run_stats_agent() builds the StatsAgentState dict and calls graph.invoke().
    result = run_stats_agent(gameweek=gameweek, season=season)

    if result.get("error"):
        # Surface graph-level errors as 502 Bad Gateway so the client knows
        # the issue is upstream (the agent / FPL API), not a bad request.
        raise HTTPException(status_code=502, detail=result["error"])

    # Store in cache
    _cache["key"]    = cache_key
    _cache["result"] = result
    _cache["ts"]     = now

    return result


def _build_status_summary(element_id: int, bootstrap: dict) -> str:
    """
    Build a human-readable availability string for a player from the live
    FPL bootstrap data.

    FPL status codes
    ----------------
    "a" → Available          (no flag)
    "d" → Doubtful           (yellow flag; chance_of_playing is 25/50/75)
    "i" → Injured            (red flag)
    "s" → Suspended          (red card / ban)
    "u" → Unavailable        (left club, international clearance issue, etc.)
    "n" → Not in squad       (loaned out / released)

    Parameters
    ----------
    element_id : FPL element/player ID
    bootstrap  : Raw bootstrap-static dict (from state["bootstrap"])

    Returns
    -------
    str
        e.g. "Available", "Doubtful (75% chance of playing)", "Injured"
    """
    STATUS_LABELS = {
        "a": "Available",
        "d": "Doubtful",
        "i": "Injured",
        "s": "Suspended",
        "u": "Unavailable",
        "n": "Not in squad",
    }

    # Find this player in the bootstrap elements list
    bs_player = next(
        (el for el in bootstrap.get("elements", []) if el["id"] == element_id),
        None,
    )

    if bs_player is None:
        return "Unknown — player not found in FPL bootstrap"

    raw_status = bs_player.get("status", "a")
    base_label = STATUS_LABELS.get(raw_status, f"Unknown ({raw_status})")

    # For doubtful players, append the percentage chance so the client can
    # display something like "Doubtful (75% chance of playing)" in the UI
    if raw_status == "d":
        chance = bs_player.get("chance_of_playing_next_round")
        if chance is not None:
            return f"{base_label} ({chance}% chance of playing)"

    return base_label


# ════════════════════════════════════════════════════════════════════════════
# ROUTES
# ════════════════════════════════════════════════════════════════════════════

@app.get("/health")
def health():
    """Liveness check — returns 200 if the server is running."""
    return {"status": "ok", "port": 8006}


# ── POST /api/stats ──────────────────────────────────────────────────────────
# Full ranked player list.  Kept for the React LoadingScreen which expects
# the complete payload (all positions, captain shortlist, form stats).

class StatsRequest(BaseModel):
    gameweek: int | None = None   # None = auto-detect latest GW
    season: str | None = None     # None = auto-detect current season from CSV


@app.post("/api/stats")
def get_stats(req: StatsRequest):
    """
    Run (or return cached) Stats Agent output for a full gameweek.

    Returns the complete ranked player list, captain shortlist, and form stats.
    Used by the React app's LoadingScreen → StatsScreen flow.
    """
    result = _get_or_run_agent(season=req.season, gameweek=req.gameweek)

    # Extract real injury/availability data from the cached FPL bootstrap
    # Status codes: 'a'=available, 'd'=doubtful, 'i'=injured, 's'=suspended, 'u'=unavailable
    bootstrap = result.get("bootstrap", {})
    TEAM_MAP = {t["id"]: t["name"] for t in bootstrap.get("teams", [])}
    POS_MAP  = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
    injury_alerts = []
    for el in bootstrap.get("elements", []):
        status = el.get("status", "a")
        chance = el.get("chance_of_playing_next_round")
        # Only surface players who are a genuine risk this GW:
        # injured, suspended, or doubtful with <=50% chance of playing.
        # Exclude 'u' (unavailable / loan departures) — not an injury concern.
        if status in ("i", "s") or (status == "d" and (chance is None or chance <= 50)):
            injury_alerts.append({
                "element":  el["id"],
                "name":     el.get("web_name", ""),
                "team":     TEAM_MAP.get(el.get("team"), ""),
                "position": POS_MAP.get(el.get("element_type"), ""),
                "status":   status,
                "news":     el.get("news", ""),
                "chance_of_playing_next_round": el.get("chance_of_playing_next_round"),
            })

    # Enrich captain_shortlist entries with team/position from ranked["ALL"]
    # (captain_shortlist entries may be missing these fields)
    ranked_by_name = {p["name"]: p for p in result.get("ranked", {}).get("ALL", [])}
    enriched_captains = []
    for c in result.get("captain_shortlist", []):
        ranked_p = ranked_by_name.get(c.get("name"), {})
        enriched_captains.append({
            **c,
            "team":     c.get("team")     or ranked_p.get("team"),
            "position": c.get("position") or ranked_p.get("position"),
        })

    payload = {
        "gameweek":               result.get("gameweek"),
        "season":                 result.get("season"),
        "ranked":                 result.get("ranked", {}),
        "captain_shortlist":      enriched_captains,
        "form_stats":             result.get("form_stats", []),
        "gw_has_actual_scores":   result.get("gw_has_actual_scores", False),
        "actual_scores_source":   result.get("actual_scores_source"),
        "dataset_gw_min":         result.get("dataset_gw_min"),
        "dataset_gw_max":         result.get("dataset_gw_max"),
        "injury_alerts":          injury_alerts,
        "log":                    result.get("log", []),
    }
    return _to_json(payload)


# ── GET /api/predict/{player_id} ─────────────────────────────────────────────

@app.get("/api/predict/{player_id}")
def predict_player(
    player_id: int,
    season: str | None = Query(default=None, description="FPL season, e.g. '2025-26'. Omit to auto-detect."),
    gameweek: int | None = Query(default=None, description="Target GW (omit for latest)"),
):
    """
    Return the Stats Agent's prediction for a single player.

    The player is identified by their FPL **element ID** (the numeric ID in
    the FPL API, e.g. 328 = Mohamed Salah).

    How it works
    ------------
    The Stats Agent is a batch pipeline — it runs for all ~800 players in a
    gameweek, not for a single player_id.  Calling graph.invoke({"player_id": x})
    would not work because the graph expects a full StatsAgentState dict.

    Instead:
        1. The full graph is run via run_stats_agent() — or the cached result
           from a previous run for the same (season, gameweek) is reused.
        2. The ranked output is filtered by element ID to find this player.
        3. Their start_probability and status_summary are assembled and returned.

    Response fields
    ---------------
    player_id         : int   — the FPL element ID you requested
    player_name       : str   — player's web_name from FPL bootstrap
    team              : str   — club name
    position          : str   — GK / DEF / MID / FWD
    gameweek          : int   — the GW these predictions are for
    expected_points   : float — predicted_pts × start_probability (risk-adjusted)
    start_probability : float — 0.0–1.0 (blended start signal)
    status_summary    : str   — human-readable availability from FPL bootstrap
    predicted_pts_raw : float — raw XGBoost output before start-prob adjustment
    ep_next_fpl       : float — FPL's own expected-points signal (cross-check)

    Example
    -------
        GET /api/predict/328
        → { "player_name": "Salah", "expected_points": 6.41, ... }
    """
    # ── Step 1: get the agent result (cached or freshly computed) ─────────────
    result = _get_or_run_agent(season=season, gameweek=gameweek)

    target_gw = result["gameweek"]

    # ── Step 2: find the player in the ranked output ──────────────────────────
    # ranked["ALL"] lists every player for this GW (sorted by expected_pts).
    # Fallback to raw predictions if a row is missing (should be rare).
    all_ranked = result.get("ranked", {}).get("ALL", [])
    player_data = next(
        (p for p in all_ranked if p.get("element") == player_id),
        None,
    )

    # Fallback to raw predictions if not in ranked ALL
    if player_data is None:
        player_data = next(
            (p for p in result.get("predictions", []) if p.get("element") == player_id),
            None,
        )

    # If still not found the player has no data row for this GW (blank week,
    # not in the dataset, or wrong element ID).
    if player_data is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Player with element ID {player_id} was not found in the "
                f"GW{target_gw} prediction set.  "
                f"They may have a blank gameweek or the element ID may be incorrect."
            ),
        )

    player_name = player_data.get("name", f"Element {player_id}")

    # ── Step 3: resolve start_probability ────────────────────────────────────
    # start_prob is already in ranked["ALL"] entries.  For predictions-fallback
    # entries it may be absent, so we look it up directly from start_probs dict.
    start_prob = player_data.get("start_prob")
    if start_prob is None:
        start_prob = result.get("start_probs", {}).get(player_name)

    # ── Step 4: resolve expected_points ──────────────────────────────────────
    expected_points = player_data.get("expected_pts")
    if expected_points is None and start_prob is not None:
        raw = player_data.get("predicted_pts", 0.0)
        expected_points = round(float(raw) * float(start_prob), 3)

    # ── Step 5: pull FPL's own ep_next signal from bootstrap (cross-check) ───
    bootstrap = result.get("bootstrap", {})
    bs_player = next(
        (el for el in bootstrap.get("elements", []) if el["id"] == player_id),
        {},
    )
    ep_next_fpl = bs_player.get("ep_next", None)

    # ── Step 6: build the human-readable status_summary ──────────────────────
    status_summary = _build_status_summary(player_id, bootstrap)

    # ── Step 7: assemble and return the response ──────────────────────────────
    payload = {
        "player_id":         player_id,
        "player_name":       player_name,
        "team":              player_data.get("team"),
        "position":          player_data.get("position"),
        "gameweek":          target_gw,
        "expected_points":   expected_points,
        "start_probability": round(float(start_prob), 3) if start_prob is not None else None,
        "status_summary":    status_summary,
        # Supporting detail — useful for debugging / richer UI cards
        "predicted_pts_raw": round(float(player_data.get("predicted_pts", 0)), 3),
        "ep_next_fpl":       ep_next_fpl,
        "value_m":           player_data.get("value_m"),
    }

    return _to_json(payload)


# ── POST /api/predict-squad ───────────────────────────────────────────────────
# Accepts a list of up to 15 FPL element IDs and returns xP / start probability
# / status for each.  Uses the same GW cache as /api/predict/{player_id} so the
# agent pipeline only runs once per gameweek regardless of how many endpoints
# are called.
#
# Why we don't call graph.invoke({"player_id": pid}) per player
# -------------------------------------------------------------
# The Stats Agent graph expects a full StatsAgentState dict as input (bootstrap
# data, feature-engineered DataFrame, model weights, etc.).  Passing only a
# player_id would crash at the very first node.  The correct pattern is:
#   1. Run the full batch pipeline once  →  _get_or_run_agent()
#   2. Filter the cached result for each requested element ID  →  O(1) lookups

class SquadRequest(BaseModel):
    player_ids: list[int]            # up to 15 FPL element IDs
    gameweek: int | None = None      # None = auto-detect latest GW
    season: str | None = None        # None = auto-detect current season from CSV


@app.post("/api/predict-squad")
def predict_squad(req: SquadRequest):
    """
    Return xP predictions for a squad of up to 15 players in one call.

    The agent pipeline runs (or is served from cache) once for the requested
    gameweek, then each element ID is looked up from the cached ranked/predictions
    output.  If a player ID is not found in the dataset (blank week, wrong ID,
    etc.) a fallback entry with xP=0 is returned for that slot so the frontend
    never receives a partial list.

    Response
    --------
    {
      "gameweek": 38,
      "season": "2024-25",
      "players": [
        { "id": 328, "name": "Salah", "xP": 6.41, "chance": 0.95, "status": "Available" },
        ...
      ]
    }
    """
    # ── Step 1: run agent once (or hit cache) ─────────────────────────────────
    result = _get_or_run_agent(season=req.season, gameweek=req.gameweek)
    target_gw = result["gameweek"]

    # Pre-build O(1) lookup dicts — avoids O(n*m) nested scans for 15 players
    all_ranked  = result.get("ranked", {}).get("ALL", [])
    predictions = result.get("predictions", [])
    start_probs = result.get("start_probs", {})
    bootstrap   = result.get("bootstrap", {})

    ranked_by_element      = _by_element(all_ranked)
    predictions_by_element = _by_element(predictions)

    # ── Step 2: resolve each requested player ID ──────────────────────────────
    players_out = []
    for pid in req.player_ids:
        try:
            # Prefer ranked["ALL"] (top-50); fall back to full predictions list
            player_data = ranked_by_element.get(pid) or predictions_by_element.get(pid)

            if player_data is None:
                raise ValueError(f"element {pid} not in dataset for GW{target_gw}")

            player_name = player_data.get("name", f"Element {pid}")

            # start_prob may be absent in predictions-fallback entries
            start_prob = player_data.get("start_prob")
            if start_prob is None:
                start_prob = start_probs.get(player_name)

            # expected_pts = predicted_pts * start_prob (risk-adjusted)
            expected_pts = player_data.get("expected_pts")
            if expected_pts is None and start_prob is not None:
                raw = player_data.get("predicted_pts", 0.0)
                expected_pts = round(float(raw) * float(start_prob), 3)

            players_out.append({
                "id":     pid,
                "name":   player_name,
                "xP":     round(float(expected_pts), 2) if expected_pts is not None else 0.0,
                "chance": round(float(start_prob),   2) if start_prob   is not None else 0.0,
                "status": _build_status_summary(pid, bootstrap),
            })

        except Exception as exc:
            # One failed player must not crash the entire 15-man response
            players_out.append({
                "id":     pid,
                "name":   f"Element {pid}",
                "xP":     0.0,
                "chance": 0.0,
                "status": f"Error: {exc}",
            })

    return _to_json({
        "gameweek": target_gw,
        "season":   result.get("season"),
        "data":     players_out,
    })


# ── POST /api/manager ──────────────────────────────────────────────────────────
# LangGraph Manager Agent v2 — optimal XI, captain/VC, chip recommendation.

class ManagerRequest(BaseModel):
    player_ids: list[int]
    bank: float = 0.0
    gameweek: int | None = None
    season: str | None = None
    triple_captain: bool = True
    bench_boost: bool = True


@app.post("/api/manager")
def get_manager(req: ManagerRequest):
    """
    Run Manager Agent v2 for a 15-man squad (FPL element IDs).
    Reuses the Stats Agent GW cache — no extra full-graph run if /api/stats
    was already called for this gameweek.
    """
    result = _get_or_run_agent(season=req.season, gameweek=req.gameweek)
    squad = _squad_for_manager_agent(result, req.player_ids)
    if len(squad) != 15:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Expected 15 squad players with GW{result['gameweek']} predictions; "
                f"found {len(squad)}. Ensure player_ids are valid FPL element IDs."
            ),
        )
    chips: list[str] = []
    if req.triple_captain:
        chips.append("triple_captain")
    if req.bench_boost:
        chips.append("bench_boost")
    out = run_manager_agent({
        "squad": squad,
        "gameweek": result["gameweek"],
        "chips_available": chips,
        "bank": req.bank,
        "historical_captain_xp": [],
        "historical_bench_xp": [],
    })
    if out.get("error"):
        raise HTTPException(status_code=502, detail=out["error"])
    payload = {
        "gameweek":           out.get("gameweek"),
        "formation":          out.get("formation"),
        "starting_xi":        out.get("starting_xi"),
        "bench":              out.get("bench"),
        "captain":            out.get("captain"),
        "vice_captain":       out.get("vice_captain"),
        "captain_id":         out.get("captain_id"),
        "vice_captain_id":    out.get("vice_captain_id"),
        "chip_recommendation": out.get("chip_recommendation"),
        "projected_points":   out.get("projected_points"),
        "summary":            out.get("summary"),
        "log":                out.get("log", []),
    }
    return _to_json(payload)


# ── POST /api/transfers ───────────────────────────────────────────────────────
# Runs the Sporting Director Agent for a manager's squad and returns ranked
# transfer recommendations.  Reuses the same GW cache as the stats endpoints
# so the full graph pipeline only runs once per gameweek regardless of how
# many endpoints are called.

class TransfersRequest(BaseModel):
    player_ids: list[int]          # 15 FPL element IDs (the manager's squad)
    bank: float = 0.0              # £m in bank
    free_transfers: int = 1        # free transfers available this GW
    gameweek: int | None = None    # None = auto-detect latest GW
    season: str | None = None      # None = auto-detect from CSV


@app.post("/api/transfers")
def get_transfers(req: TransfersRequest):
    """
    Run the Sporting Director Agent to produce transfer recommendations.

    Steps
    -----
    1. Run (or cache-hit) the Stats Agent for the given gameweek.
    2. Look up each squad player from the ranked/predictions output and merge
       their form stats so PlayerProfile has all required fields.
    3. Build a Squad dataclass and call run_sporting_director().
    4. Serialise and return the TransferRecommendation.

    Response
    --------
    {
      "gameweek": 30,
      "season": "2024-25",
      "hold_flag": false,
      "wildcard_flag": false,
      "summary": "GW30 recommendation: Transfer ...",
      "transfers": [
        {
          "sell": { "name": "...", "position": "MID", "cost": 6.5, "expected_pts": 4.9, ... },
          "buy":  { "name": "...", "position": "MID", "cost": 6.5, "expected_pts": 5.8, ... },
          "net_expected_gain": 0.9,
          "transfer_cost_points": 0,
          "score": 2.3,
          "reasoning": "..."
        }, ...
      ],
      "log": [...]
    }
    """
    import dataclasses

    # ── Step 1: run stats agent (or hit cache) ────────────────────────────────
    result = _get_or_run_agent(season=req.season, gameweek=req.gameweek)
    target_gw = result["gameweek"]

    # ── Step 2: build player lookups ──────────────────────────────────────────
    all_ranked  = result.get("ranked", {}).get("ALL", [])
    predictions = result.get("predictions", [])
    form_stats  = result.get("form_stats", [])

    ranked_by_element      = _by_element(all_ranked)
    predictions_by_element = _by_element(predictions)
    form_by_name           = _form_by_name(form_stats)

    # ── Step 3: build squad PlayerProfiles ────────────────────────────────────
    squad_players: list[PlayerProfile] = []
    for pid in req.player_ids:
        player_data = ranked_by_element.get(pid) or predictions_by_element.get(pid)
        if player_data is None:
            # Player has no data row for this GW — skip (blank week / wrong ID)
            continue

        merged = _merge_player_form(player_data, form_by_name)
        squad_players.append(PlayerProfile.from_ranked_player(merged))

    if not squad_players:
        raise HTTPException(
            status_code=422,
            detail=(
                f"None of the {len(req.player_ids)} supplied element IDs were found "
                f"in the GW{target_gw} dataset.  "
                "Ensure player_ids are valid FPL element IDs (not demo/fake IDs)."
            ),
        )

    squad = Squad(
        players        = squad_players,
        bank           = req.bank,
        free_transfers = req.free_transfers,
        gameweek       = target_gw,
    )

    # ── Step 4: run Sporting Director ─────────────────────────────────────────
    recommendation = run_sporting_director(result, squad)
    rec_dict       = dataclasses.asdict(recommendation)

    # stats pipeline row is GW `target_gw`; Sporting Director plans transfers for `next_gw`
    planning_gw = recommendation.gameweek
    return _to_json({
        "gameweek":          target_gw,
        "planning_gameweek": planning_gw,
        "season":            result.get("season"),
        "hold_flag":         recommendation.hold_flag,
        "wildcard_flag":     recommendation.wildcard_flag,
        "summary":           recommendation.summary,
        "transfers":         rec_dict.get("recommended_transfers", []),
        "log":               recommendation.log,
    })
