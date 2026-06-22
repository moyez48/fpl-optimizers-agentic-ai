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

CSV ingest (cheap no-op when already current — see ``update_data.maybe_refresh_processed_csv``):
    Runs automatically before each stats-agent run unless ``SKIP_FPL_CSV_REFRESH=1``.

Periodic background sweep (optional):
    ``AUTO_REFRESH_FPL_DATA=1`` and ``AUTO_REFRESH_INTERVAL_HOURS=12`` (default).

Omit ``gameweek`` on POST ``/api/stats`` to default to FPL ``is_next`` (planning GW).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ── Resolve repo root so agents/ and analysis/ are importable ─────────────────
# backend/main.py lives at  <repo_root>/backend/main.py
# dirname(__file__)          → <repo_root>/backend/
# dirname(dirname(__file__)) → <repo_root>/
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED_CSV = os.path.join(REPO_ROOT, "data", "processed_fpl_data.csv")
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


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes")


@asynccontextmanager
async def lifespan(app: FastAPI):
    sweep_task = None

    # Optional: periodically pull merged GW CSV + re-run FE (see update_data.py).
    # Default interval 12 h — cheap (~2 s) no-op via API probe when CSV is current.
    if _truthy_env("AUTO_REFRESH_FPL_DATA"):
        hours = float(os.getenv("AUTO_REFRESH_INTERVAL_HOURS", "12"))

        async def _csv_refresh_sweep():
            await asyncio.sleep(8)
            import update_data

            interval_sec = max(3600.0, hours * 3600.0)
            try:
                while True:
                    try:
                        await asyncio.to_thread(update_data.maybe_refresh_processed_csv, False)
                    except Exception:
                        pass
                    await asyncio.sleep(interval_sec)
            except asyncio.CancelledError:
                raise

        sweep_task = asyncio.create_task(_csv_refresh_sweep())
        print(
            f"[backend] AUTO_REFRESH_FPL_DATA=1 · interval={hours}h "
            "(set AUTO_REFRESH_INTERVAL_HOURS to adjust)",
            flush=True,
        )

    yield

    if sweep_task is not None:
        sweep_task.cancel()
        try:
            await sweep_task
        except asyncio.CancelledError:
            pass


# ── App setup ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="FPL Stats Agent API",
    description="LangGraph-powered FPL point prediction backend.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — Vite localhost + *.vercel.app + optional custom domains (comma-separated)
_default_cors = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
    "http://localhost:5176",
]
_extra = [
    o.strip()
    for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys(_default_cors + _extra)),
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
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


def _recent_form_trend(pts: list | None) -> str:
    """
    Build a +/-/ trend string from a list of recent per-GW point totals.

    Compares each game to its predecessor over (up to) the last 6 games:
      '+' = scored more than previous GW, '-' = fewer, '/' = flat.
    Returns "" when there isn't enough history (< 2 games).
    """
    vals = list(pts or [])
    if len(vals) < 2:
        return ""
    recent = vals[-6:]
    syms: list[str] = []
    for a, b in zip(recent, recent[1:]):
        if b > a:
            syms.append("+")
        elif b < a:
            syms.append("-")
        else:
            syms.append("/")
    return "".join(syms)


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


# ── Pitchcraft UI helpers (GET /api/squad, POST /api/optimize) ───────────────

PITCHCRAFT_DEMO_IDS: list[int] = [
    1, 2, 7, 8, 9, 10, 11, 18, 19, 21, 24, 23, 34, 35, 39,
]

PITCHCRAFT_DEMO_SQUAD: dict[str, Any] = {
    "starting": {
        "GKP": [1],
        "DEF": [7, 8, 9, 10],
        "MID": [18, 19, 21, 23],
        "FWD": [34, 35],
    },
    "bench": [2, 11, 24, 39],
    "captain": 18,
    "vice": 34,
}

FPL_ELEMENT_TYPE_UI = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


def _mgr_pos_to_pitch(pos: str) -> str:
    if pos == "GK":
        return "GKP"
    return pos if pos in ("DEF", "MID", "FWD", "GKP") else "MID"


def _pitchcraft_squad_from_manager_json(mgr: dict) -> dict[str, Any]:
    xi = mgr.get("starting_xi") or []
    bench_rows = mgr.get("bench") or []
    buckets: dict[str, list[int]] = {"GKP": [], "DEF": [], "MID": [], "FWD": []}
    for p in xi:
        key = _mgr_pos_to_pitch(str(p.get("position", "MID")))
        buckets.setdefault(key, []).append(int(p["id"]))
    bench_ids = [int(p["id"]) for p in bench_rows]
    cap = mgr.get("captain_id")
    vc = mgr.get("vice_captain_id")
    return {
        "starting": buckets,
        "bench": bench_ids,
        "captain": int(cap) if cap is not None else None,
        "vice": int(vc) if vc is not None else None,
    }


def _bootstrap_element_maps(
    bootstrap: dict,
) -> tuple[dict[int, dict], dict[int, str], dict[int, int]]:
    by_id: dict[int, dict] = {}
    team_short: dict[int, str] = {}
    team_code: dict[int, int] = {}
    for t in bootstrap.get("teams") or []:
        tid = t.get("id")
        if tid is not None:
            team_short[int(tid)] = str(t.get("short_name") or t.get("name") or "?")[:3]
            code = t.get("code")
            if code is not None:
                team_code[int(tid)] = int(code)
    for el in bootstrap.get("elements") or []:
        eid = el.get("id")
        if eid is not None:
            by_id[int(eid)] = el
    return by_id, team_short, team_code


def _map_bootstrap_players(bootstrap: dict) -> list[dict[str, Any]]:
    """Lightweight player rows from FPL bootstrap ``elements``."""
    _, team_short, team_code = _bootstrap_element_maps(bootstrap)
    team_names: dict[int, str] = {}
    for t in bootstrap.get("teams") or []:
        tid = t.get("id")
        if tid is not None:
            team_names[int(tid)] = str(t.get("name") or "")
    rows: list[dict[str, Any]] = []
    for el in bootstrap.get("elements") or []:
        eid = el.get("id")
        if eid is None:
            continue
        tid = el.get("team")
        et = int(el.get("element_type") or 3)
        pos_ui = FPL_ELEMENT_TYPE_UI.get(et, "MID")
        web_name = el.get("web_name") or f"Player {eid}"
        fname = str(el.get("first_name") or "")
        lname = str(el.get("second_name") or "")
        ep_next = el.get("ep_next")
        ep_this = el.get("ep_this")
        rows.append(
            {
                "id": int(eid),
                "web_name": web_name,
                "name": web_name,
                "first_name": fname,
                "second_name": lname,
                "team_id": int(tid) if tid is not None else None,
                "team_code": team_code.get(int(tid)) if tid is not None else None,
                "team": team_names.get(int(tid), "?") if tid is not None else "?",
                "element_type": et,
                "position": pos_ui,
                "now_cost": int(el.get("now_cost") or 0),
                "price": round(float(el.get("now_cost") or 0) / 10.0, 1),
                "total_points": int(el.get("total_points") or 0),
                "ep_next": ep_next,
                "ep_this": ep_this,
                "form": el.get("form"),
                "xg": float(el.get("expected_goals") or 0),
                "xa": float(el.get("expected_assists") or 0),
                "xga": float(el.get("expected_goal_involvements") or 0),
                "teamShort": team_short.get(int(tid), "???") if tid is not None else "???",
            }
        )
    return rows


def _model_xpts_for_element(
    element_id: int,
    pdata: dict | None,
    result: dict,
) -> float | None:
    """Risk-adjusted xPts from Stats Agent output, or None if unavailable."""
    if not pdata:
        return None
    start_prob = pdata.get("start_prob")
    if start_prob is None:
        start_prob = result.get("start_probs", {}).get(pdata.get("name", ""))
    expected = pdata.get("expected_pts")
    if expected is None:
        raw = float(pdata.get("predicted_pts") or 0)
        if start_prob is None:
            return None
        expected = raw * float(start_prob)
    return round(float(expected), 2)


def _bootstrap_ep_fallback(el: dict) -> float:
    """FPL ep_next / ep_this when the model has no row for this GW."""
    for key in ("ep_next", "ep_this"):
        val = el.get(key)
        if val is not None and str(val).strip() not in ("", "None"):
            try:
                return round(float(val), 2)
            except (TypeError, ValueError):
                continue
    return 0.0


def _gameweek_allows_live_scores(bootstrap: dict, gw: int) -> bool:
    """True when *gw* is the active or a completed round (not a future deadline)."""
    events = bootstrap.get("events") or []
    current = _current_active_gw(events)
    if current is None:
        return True
    return int(gw) <= int(current)


def _map_players_with_gw_predictions(
    bootstrap: dict,
    *,
    season: str | None = None,
    gameweek: int | None = None,
    live_gw: int | None = None,
) -> tuple[list[dict[str, Any]], int | None, str]:
    """
    Bootstrap player pool with per-player xPts for *gameweek*.

    Every active element receives ``xPts`` / ``xp`` from the Stats Agent for the
    requested GW. Missing model rows fall back to FPL ``ep_next``.

    When *live_gw* is set (explicit ``?gw=`` from the client) and refers to a
    past/current round, ``gw_pts`` / ``gw_points`` are filled from FPL live.
    """
    base_rows = _map_bootstrap_players(bootstrap)
    bs_by_id, _, _ = _bootstrap_element_maps(bootstrap)
    gw_eff = _resolve_agent_gameweek(gameweek)

    try:
        result = _get_or_run_agent(season=season, gameweek=gw_eff)
    except HTTPException:
        result = {}

    gw_live_map: dict[int, int] = {}
    attach_live = (
        live_gw is not None and _gameweek_allows_live_scores(bootstrap, int(live_gw))
    )
    if attach_live:
        gw_live_map = _fetch_event_live_points(int(live_gw))

    all_ranked = (result.get("ranked") or {}).get("ALL", []) if result else []
    predictions = result.get("predictions", []) if result else []
    ranked_by_element = _by_element(all_ranked)
    predictions_by_element = _by_element(predictions)
    form_stats = result.get("form_stats", []) if result else []
    form_by_name = _form_by_name(form_stats)

    out: list[dict[str, Any]] = []
    for row in base_rows:
        pid = int(row["id"])
        el = bs_by_id.get(pid, {})
        pdata = ranked_by_element.get(pid) or predictions_by_element.get(pid)
        if pdata:
            pdata = _merge_player_form(pdata, form_by_name)
        xp = _model_xpts_for_element(pid, pdata, result)
        source = "model"
        if xp is None:
            xp = _bootstrap_ep_fallback(el)
            source = "ep_next"

        gw_pts: int | None = None
        if live_gw is not None:
            if attach_live:
                gw_pts = int(gw_live_map.get(pid, 0))
            else:
                gw_pts = None

        enriched = {
            **row,
            "xp": xp,
            "xPts": xp,
            "xpts_source": source,
            "prediction_gw": gw_eff,
            "gw_pts": gw_pts,
            "gw_points": gw_pts,
        }
        out.append(enriched)
    return out, gw_eff, result.get("season") or season or ""


def _fpl_event_for_picks(events: list) -> dict | None:
    if not events:
        return None
    cur = next((e for e in events if e.get("is_current")), None)
    nxt = next((e for e in events if e.get("is_next")), None)
    return cur or nxt or events[-1]


def _parse_fpl_picks_to_pitchcraft(
    picks_payload: dict,
    bs_by_id: dict[int, dict],
) -> tuple[dict[str, Any], list[int]]:
    picks_raw = picks_payload.get("picks") or []
    starters = sorted(
        [p for p in picks_raw if int(p.get("position", 99)) <= 11],
        key=lambda x: int(x["position"]),
    )
    bench_pk = sorted(
        [p for p in picks_raw if int(p.get("position", 99)) > 11],
        key=lambda x: int(x["position"]),
    )
    buckets: dict[str, list[int]] = {"GKP": [], "DEF": [], "MID": [], "FWD": []}
    captain_id: int | None = None
    vice_id: int | None = None
    for pk in starters:
        pid = int(pk["element"])
        el = bs_by_id.get(pid) or {}
        et = int(el.get("element_type") or 3)
        pos_ui = FPL_ELEMENT_TYPE_UI.get(et, "MID")
        buckets[pos_ui].append(pid)
        if pk.get("multiplier") == 2 or pk.get("is_captain"):
            captain_id = pid
        if pk.get("is_vice_captain"):
            vice_id = pid
    bench_ids = [int(p["element"]) for p in bench_pk]
    order_ids = [int(pk["element"]) for pk in starters] + bench_ids
    squad = {"starting": buckets, "bench": bench_ids, "captain": captain_id, "vice": vice_id}
    return squad, order_ids


def _pitchcraft_player_rows(
    result: dict,
    player_ids: list[int],
    bootstrap: dict | None,
    gw_points_map: dict[int, int] | None = None,
) -> list[dict[str, Any]]:
    """_rows shaped like the Pitchcraft React PLAYERS table.

    ``gw_points_map`` (element_id → points) overrides each player's GW points so
    the sidebar reflects the *selected* gameweek rather than the live one.
    """
    bs_by_id, team_short, team_codes = (
        _bootstrap_element_maps(bootstrap) if bootstrap else ({}, {}, {})
    )
    all_ranked = result.get("ranked", {}).get("ALL", [])
    predictions = result.get("predictions", [])
    form_stats = result.get("form_stats", [])
    ranked_by_element = _by_element(all_ranked)
    predictions_by_element = _by_element(predictions)
    form_by_name = _form_by_name(form_stats)
    rows: list[dict[str, Any]] = []
    for pid in player_ids:
        pdata = ranked_by_element.get(pid) or predictions_by_element.get(pid)
        merged = _merge_player_form(pdata, form_by_name) if pdata else {}
        el = bs_by_id.get(pid, {})
        et = int(el.get("element_type") or merged.get("element_type") or 3)
        pos_ui = FPL_ELEMENT_TYPE_UI.get(et, "MID")
        tid = el.get("team")
        team_name = ""
        if tid is not None and bootstrap:
            team_name = next(
                (
                    str(t.get("name") or "")
                    for t in (bootstrap.get("teams") or [])
                    if int(t.get("id") or -1) == int(tid)
                ),
                "",
            )
        start_prob = merged.get("start_prob")
        if start_prob is None and pdata:
            start_prob = result.get("start_probs", {}).get(pdata.get("name", ""))
        raw_pred = float(
            merged.get("predicted_pts")
            or (pdata.get("predicted_pts") if pdata else 0)
            or 0.0
        )
        xp = merged.get("expected_pts")
        if xp is None:
            xp = raw_pred * float(start_prob or 0.0)
        xp = round(float(xp or 0.0), 2)
        web_name = el.get("web_name") or merged.get("name") or f"Player {pid}"
        price = float(el.get("now_cost") or 0) / 10.0 if el else float(
            merged.get("cost") or merged.get("value_m") or 0
        )
        injured = str(el.get("status") or "a") in ("i", "s")
        fname = str(el.get("first_name") or "")
        lname = str(el.get("second_name") or "")
        full_name = (fname + " " + lname).strip() or web_name

        # Advanced / aggregate stats for the Players tab data table.
        form_rec   = form_by_name.get(merged.get("name") or "", {})
        pts5       = form_rec.get("pts_last5") or []
        avg_pts    = float(merged.get("avg_pts_last5") or form_rec.get("avg_pts_last5") or 0)
        median_pts = round(float(np.median(pts5)), 1) if len(pts5) else round(avg_pts, 1)
        goals      = int(merged.get("goals_last5") or 0)
        assists    = int(merged.get("assists_last5") or 0)
        xg_val     = float(merged.get("xg_last_5") or 0)
        xa_val     = float(merged.get("xa_last_5") or 0)
        trend_str  = _recent_form_trend(pts5)

        rows.append(
            {
                "id": pid,
                "name": web_name,
                "web_name": web_name,
                "position": pos_ui,
                "element_type": et,
                "team": team_name or "?",
                "teamShort": team_short.get(int(tid), "???") if tid is not None else "???",
                "team_id": int(tid) if tid is not None else None,
                "team_code": team_codes.get(int(tid)) if tid is not None else None,
                "price": round(price, 1),
                "form": float(el.get("form") or merged.get("form") or 0),
                "xp": xp,
                "xPts": xp,
                "xG": xg_val,
                "xA": xa_val,
                # Lowercase keys consumed by the Players-tab table.
                "xg": round(xg_val, 2),
                "xa": round(xa_val, 2),
                "goals": goals,
                "assists": assists,
                "avg_pts": round(avg_pts, 2),
                "median_pts": median_pts,
                "form_trend": trend_str,
                "fixtureDifficulty": int(merged.get("fixture_difficulty") or 3),
                "nextFixture": str(merged.get("next_fixture") or "—"),
                "injured": injured,
                "ownership": float(el.get("selected_by_percent") or 0),
                "variance": 2.0,
                # Extended FPL API stats for the click-to-expand detail panel.
                "ict_index": float(el.get("ict_index") or 0),
                "points_per_game": float(el.get("points_per_game") or 0),
                "total_points": int(el.get("total_points") or 0),
                "clean_sheets": int(el.get("clean_sheets") or 0),
                "minutes": int(el.get("minutes") or 0),
                "starts": int(el.get("starts") or 0),
                "season_goals": int(el.get("goals_scored") or 0),
                "season_assists": int(el.get("assists") or 0),
                # DISPLAY ONLY — never feed gw_points into Manager / Transfer agents.
                # Optimal XI and transfer math use xp/xPts (model predictions) only.
                # Points scored in the selected gameweek. When a per-GW map is
                # supplied, never fall back to bootstrap event_points (live GW).
                "gw_points": int(
                    gw_points_map.get(pid, 0)
                    if gw_points_map
                    else el.get("event_points") or 0
                ),
                "gw_pts": int(
                    gw_points_map.get(pid, 0)
                    if gw_points_map
                    else el.get("event_points") or 0
                ),
            }
        )
    return rows


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


def _invalidate_agent_cache() -> None:
    """Clear in-memory stats payload so the next request re-runs the graph."""
    _cache["key"] = None
    _cache["result"] = None
    _cache["ts"] = 0.0


def _maybe_refresh_csv_before_agent() -> None:
    """
    Cheap ingest check before each stats run (bootstrap + CSV max vs latest finished GW).
    Skips heavy work when already current. Disable with SKIP_FPL_CSV_REFRESH=1.

    AUTO_REFRESH_FPL_DATA=1 additionally starts the periodic sweep in lifespan — unrelated
    to this hook except both use update_data.maybe_refresh_processed_csv.
    """
    if _truthy_env("SKIP_FPL_CSV_REFRESH"):
        return
    try:
        import update_data

        if update_data.maybe_refresh_processed_csv(False):
            _invalidate_agent_cache()
    except Exception:
        pass


# Maximum age of a cached result in seconds.
# 3600 s = 1 hour.  After this the graph re-runs even for the same GW,
# which picks up any live bootstrap changes (injury updates etc.).
_CACHE_TTL = 3600

# Bump when the /api/stats response schema changes so stale cached payloads
# (e.g. missing actual_points) are not served.
_CACHE_SCHEMA_VER = "20260206b"


def _get_or_run_agent(season: str | None, gameweek: int | None) -> dict:
    """
    Return a cached agent result if available and fresh, otherwise run the
    full graph and cache the result.

    Parameters
    ----------
    season   : FPL season string, e.g. "2024-25"
    gameweek : Target GW number, or None → resolved via _resolve_agent_gameweek()

    Returns
    -------
    dict
        The final StatsAgentState produced by the graph.

    Raises
    ------
    HTTPException(502)
        If the graph returns an error (e.g. FPL API unreachable, missing model).
    """
    _maybe_refresh_csv_before_agent()
    gw_eff = _resolve_agent_gameweek(gameweek)
    cache_key = f"{_CACHE_SCHEMA_VER}__{season}__{gw_eff}"
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
    result = run_stats_agent(gameweek=gw_eff, season=season)

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


@app.get("/api/data/meta")
def data_csv_meta():
    """
    Fast snapshot of merged dataset on disk (+ FPL bootstrap latest finished GW).
    Use to verify deployed API / image has the CSV you expect (no full agent run).
    """
    try:
        st = os.stat(PROCESSED_CSV)
        mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
        df = pd.read_csv(PROCESSED_CSV, usecols=["season", "GW"])
        by_season: dict[str, dict[str, int]] = {}
        for season in df["season"].unique():
            sub = df.loc[df["season"].astype(str) == str(season), "GW"]
            by_season[str(season)] = {
                "gw_min": int(sub.min()),
                "gw_max": int(sub.max()),
            }
        fpl_finished: int | None = None
        try:
            r = requests.get(
                "https://fantasy.premierleague.com/api/bootstrap-static/",
                timeout=15,
            )
            r.raise_for_status()
            lx = 1
            for ev in r.json().get("events") or []:
                if ev.get("finished") is True:
                    lx = int(ev["id"])
            fpl_finished = lx
        except Exception:
            fpl_finished = None

        return _to_json(
            {
                "processed_csv": "data/processed_fpl_data.csv",
                "csv_mtime_utc": mtime,
                "gw_range_by_season": by_season,
                "fpl_latest_finished_gw": fpl_finished,
                "deploy_git_sha": os.getenv("VERCEL_GIT_COMMIT_SHA")
                or os.getenv("RAILWAY_GIT_COMMIT_SHA")
                or os.getenv("GIT_COMMIT"),
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"data meta: {exc}") from exc


# ── POST /api/stats ──────────────────────────────────────────────────────────
# Full ranked player list.  Kept for the React LoadingScreen which expects
# the complete payload (all positions, captain shortlist, form stats).

class StatsRequest(BaseModel):
    gameweek: int | None = None   # None = FPL is_next (planning GW); see _resolve_agent_gameweek
    season: str | None = None     # None = auto-detect current season from CSV


FPL_BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"

# Browser-like headers — the FPL API can rate-limit / reject default clients.
FPL_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


def _get_fpl_planning_gameweek() -> int | None:
    """
    Fetch the 'planning' gameweek from FPL API — the upcoming deadline (is_next).
    Falls back to is_current if is_next isn't set, or None on error.
    """
    try:
        r = requests.get(FPL_BOOTSTRAP_URL, timeout=15)
        r.raise_for_status()
        events = r.json().get("events", [])
        # is_next = the upcoming GW deadline (where you plan transfers)
        next_gw = next((e for e in events if e.get("is_next")), None)
        if next_gw:
            return int(next_gw["id"])
        # Fallback to is_current
        current = next((e for e in events if e.get("is_current")), None)
        if current:
            return int(current["id"])
        return None
    except Exception:
        return None


def _resolve_agent_gameweek(requested: int | None) -> int | None:
    """
    If the client passes an explicit GW, use it. Otherwise prefer FPL ``is_next``
    so defaults align with the deadline you're planning for (often dataset_max+1
    in planning mode). Fallback: CSV max GW + 1 for ACTIVE_INGEST_SEASON.
    """
    if requested is not None:
        return requested
    g = _get_fpl_planning_gameweek()
    if g is not None:
        return g
    try:
        import update_data as ud

        mx = ud.csv_max_gw_for_season(ud.ACTIVE_INGEST_SEASON)
        if mx is not None:
            return min(38, mx + 1)
    except Exception:
        pass
    return None


@app.post("/api/stats")
def get_stats(req: StatsRequest):
    """
    Run (or return cached) Stats Agent output for a full gameweek.

    Returns the complete ranked player list, captain shortlist, and form stats.
    Used by the React app's LoadingScreen → StatsScreen flow.
    """
    # Get the FPL planning gameweek (is_next) for context
    planning_gw = _get_fpl_planning_gameweek()
    
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

    # The model uses features from the latest finished GW in the CSV.
    # The planning_gameweek is the FPL "is_next" GW (where you set transfers).
    model_gw = result.get("gameweek")
    
    payload = {
        "gameweek":               model_gw,
        "planning_gameweek":      planning_gw,  # FPL's upcoming deadline
        "season":                 result.get("season"),
        "ranked":                 result.get("ranked", {}),
        "captain_shortlist":      enriched_captains,
        "form_stats":             result.get("form_stats", []),
        "gw_has_actual_scores":   result.get("gw_has_actual_scores", False),
        "actual_scores_source":   result.get("actual_scores_source"),
        "dataset_gw_min":         result.get("dataset_gw_min"),
        "dataset_gw_max":         result.get("dataset_gw_max"),
        "gw_fallback_warning":    result.get("gw_fallback_warning"),
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
    chips_available: list[str] | None = None


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
    chips: list[str] = list(req.chips_available or [])
    if not chips:
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
    # element_id → price actually paid (£m). When supplied (from live FPL picks)
    # the agent uses the true FPL selling price (50% profit tax) for bank math.
    purchase_prices: dict[int, float] | None = None


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
      "gameweek": 35,
      "season": "2024-25",
      "hold_flag": false,
      "wildcard_flag": false,
      "summary": "GW35 recommendation: Transfer ...",
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
        profile = PlayerProfile.from_ranked_player(merged)
        # Use the manager's real purchase price (from live FPL picks) so the
        # sell-price lock (50% profit tax) is computed against what they paid,
        # not the player's current now_cost.
        if req.purchase_prices:
            paid = req.purchase_prices.get(profile.element)
            if paid:
                profile.purchase_price = float(paid)
        squad_players.append(profile)

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

    raw_transfers = rec_dict.get("recommended_transfers", [])

    # ── Step 1: deduplicate exact (player_out, player_in) pairs ──────────────
    # The same pair can arrive via the single-transfer path AND the T1 of a
    # multi-transfer pair. Keep the copy with the highest expected_gain (xP_gain).
    pair_best: dict[tuple, dict] = {}
    for t in raw_transfers:
        sell_elem = (t.get("sell") or {}).get("element")
        buy_elem  = (t.get("buy")  or {}).get("element")
        key  = (sell_elem, buy_elem)
        gain = t.get("expected_gain") or 0
        if key not in pair_best or gain > (pair_best[key].get("expected_gain") or 0):
            pair_best[key] = t

    # ── Step 2: group by player_out; #1 → Primary, rest → alternatives ───────
    # Preserve the agent's sell-player ranking order (dict insertion is ordered).
    by_sell: dict[int, list] = {}
    for t in pair_best.values():
        sell_elem = (t.get("sell") or {}).get("element")
        by_sell.setdefault(sell_elem, []).append(t)

    final_transfers: list[dict] = []
    for group in by_sell.values():
        # Within each sell group rank by expected_gain (xP_gain) descending
        group.sort(key=lambda x: (x.get("expected_gain") or 0), reverse=True)

        primary = dict(group[0])          # shallow copy — never mutate rec_dict
        primary_buy = (primary.get("buy") or {}).get("element")

        # Merge agent-provided alternatives with any extra same-sell top-level rows
        agent_alts = list(primary.get("alternatives") or [])
        extra_alts = group[1:]            # other buy targets as separate top-level rows

        alt_seen: set = set()
        merged_alts: list[dict] = []
        for alt in extra_alts + agent_alts:
            buy_elem = (alt.get("buy") or {}).get("element")
            if buy_elem and buy_elem != primary_buy and buy_elem not in alt_seen:
                alt_seen.add(buy_elem)
                merged_alts.append(alt)

        primary["alternatives"] = merged_alts[:2]
        final_transfers.append(primary)

    # ── Step 3: apply FPL hit penalties sequentially ─────────────────────────
    # The first `free_transfers` moves are free; EVERY transfer beyond that
    # costs exactly 4 pts, deducted from that specific move's expected gain.
    # Order best-gain-first so the free transfers are spent on the top moves.
    free_t = max(0, int(req.free_transfers))
    final_transfers.sort(key=lambda t: -(t.get("expected_gain") or 0))
    for idx, t in enumerate(final_transfers):
        hit = 0 if idx < free_t else 4
        gain = t.get("expected_gain") or 0
        t["transfer_cost_points"] = hit
        t["net_expected_gain"] = round(gain - hit, 3)
        # Alternatives occupy the SAME transfer slot as their primary — they
        # are swap-in options, not extra transfers, so they share the same hit.
        for alt in t.get("alternatives") or []:
            alt_gain = alt.get("expected_gain") or 0
            alt["transfer_cost_points"] = hit
            alt["net_expected_gain"] = round(alt_gain - hit, 3)
    deduped_transfers = final_transfers

    # ── Step 4: chip suggestion ──────────────────────────────────────────────
    # A plan needing >= 4 transfers would cost a heavy points hit; suggest a
    # chip instead. Free Hit when the squad is dominated by a one-off
    # blank/double GW, otherwise a Wildcard for a permanent rebuild.
    WILDCARD_TRANSFER_THRESHOLD = 4
    num_moves = len(deduped_transfers)
    wildcard_field: Any = False
    if num_moves >= WILDCARD_TRANSFER_THRESHOLD or recommendation.wildcard_flag:
        has_blank_or_double = any(
            (getattr(r, "fixture", {}) or {}).get("has_blank_gw")
            or (getattr(r, "fixture", {}) or {}).get("has_double_gw")
            for r in (recommendation.squad_health or [])
        )
        wildcard_field = "Free Hit" if has_blank_or_double else "Wildcard"

    return _to_json({
        "gameweek":          min(target_gw, 38),
        "planning_gameweek": min(planning_gw, 38),
        "season":            result.get("season"),
        "hold_flag":         recommendation.hold_flag,
        "wildcard_flag":     wildcard_field,
        "summary":           recommendation.summary,
        "transfers":         deduped_transfers,
        "log":               recommendation.log,
    })


def _json_response_payload(resp: JSONResponse) -> dict[str, Any]:
    raw = getattr(resp, "body", None)
    if raw is None:
        return {}
    if isinstance(raw, memoryview):
        raw = raw.tobytes()
    return json.loads(bytes(raw).decode("utf-8"))


class OptimizeRequest(BaseModel):
    """Pitchcraft dashboard — Manager + Sporting Director in one round-trip."""

    player_ids: list[int]
    bank: float = 0.5
    free_transfers: int = 1
    gameweek: int | None = None
    season: str | None = None
    # Optional FPL manager ID — when present we fetch live purchase/selling
    # prices so transfer bank math reflects the user's real squad.
    fpl_id: int | None = None


def _fetch_fpl_purchase_prices(entry: int) -> dict[int, float]:
    """
    Fetch a manager's current picks and return {element_id: purchase_price_£m}.

    The FPL picks payload exposes ``purchase_price`` and ``selling_price`` in
    0.1m units; we return the purchase price so the sell-price lock (50% profit
    tax) can be recomputed exactly. Returns {} on any failure (best-effort).
    """
    try:
        br = requests.get(FPL_BOOTSTRAP_URL, headers=FPL_REQUEST_HEADERS, timeout=15)
        br.raise_for_status()
        ev = _fpl_event_for_picks(br.json().get("events") or [])
        if not ev:
            return {}
        pr = requests.get(
            f"https://fantasy.premierleague.com/api/entry/{int(entry)}/event/{int(ev['id'])}/picks/",
            headers=FPL_REQUEST_HEADERS,
            timeout=15,
        )
        pr.raise_for_status()
        out: dict[int, float] = {}
        for pick in pr.json().get("picks") or []:
            el = pick.get("element")
            paid = pick.get("purchase_price")
            if el is not None and paid is not None:
                out[int(el)] = round(float(paid) / 10.0, 1)
        return out
    except Exception:
        return {}


def _fetch_manager_squad_stats(entry: int, gw: int | None = None) -> dict[str, Any]:
    """
    Manager-level aggregate stats from the FPL season history.

    Pulls ``/entry/{id}/history/`` and derives:
      - highest_points / median_points across played gameweeks
      - current_gw_points for the requested ``gw`` (or most recent if omitted)
      - overall_trend ("up" | "down" | "flat") — recent form vs earlier form
      - squad_form — a +/-/ string over the last few gameweeks
    Returns {} on any failure (best-effort, non-fatal).
    """
    try:
        hist = _fetch_fpl_entry_history(entry)
        current = hist.get("current") or []
        pts = [int(gw_row.get("points") or 0) for gw_row in current]
        if not pts:
            return {}

        highest = max(pts)
        med = round(float(np.median(pts)), 1)

        # Points for the *selected* gameweek, not always the latest row.
        target_gw = int(gw) if gw is not None else int(current[-1].get("event") or 0)
        gw_row = next(
            (row for row in current if int(row.get("event") or -1) == target_gw),
            None,
        )
        current_gw_points = int(gw_row.get("points") or 0) if gw_row else pts[-1]

        # overall_trend: compare overall_rank across the last 3 gameweeks.
        # A *smaller* rank number = better, so a falling rank ⇒ "Up".
        ranks = [
            int(gw["overall_rank"])
            for gw in current
            if gw.get("overall_rank") is not None
        ]
        trend = "Flat"
        if len(ranks) >= 2:
            window = ranks[-3:]
            first, last = window[0], window[-1]
            if last < first:
                trend = "Up"       # rank improved (number got smaller)
            elif last > first:
                trend = "Down"     # rank worsened (number got larger)
            else:
                trend = "Flat"

        # Per-gameweek points history for the trend line.
        points_history = [
            {"gw": int(gw.get("event")), "points": int(gw.get("points") or 0)}
            for gw in current
            if gw.get("event") is not None
        ]

        return {
            "current_gw_points": current_gw_points,
            "highest_points": highest,
            "median_points": med,
            "overall_trend": trend,
            "squad_form": _recent_form_trend(pts),
            "points_history": points_history,
        }
    except Exception:
        return {}


def _fetch_fpl_entry_history(entry: int) -> dict[str, Any]:
    """Season history payload from ``/entry/{id}/history/`` (or {})."""
    try:
        r = requests.get(
            f"https://fantasy.premierleague.com/api/entry/{int(entry)}/history/",
            headers=FPL_REQUEST_HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}


def _compute_banked_free_transfers(history_data: dict[str, Any]) -> int:
    """
    Free transfers banked for the upcoming GW (FPL roll-up cap: 5).

    Mirrors the frontend ``computeFreeTransfers`` rules in ``fplApi.js``.
    """
    current = history_data.get("current") or []
    chips = history_data.get("chips") or []
    chips_by_gw = {
        int(c["event"]): str(c["name"])
        for c in chips
        if c.get("event") is not None and c.get("name")
    }
    fts = 1
    for gw_row in current:
        event = int(gw_row.get("event") or 0)
        chip = chips_by_gw.get(event)
        transfers = int(gw_row.get("event_transfers") or 0)
        if chip in ("wildcard", "freehit"):
            fts = 1
        elif transfers <= fts:
            fts = min(fts - transfers + 1, 5)
        else:
            fts = 1
    return fts


def _compute_available_chips(history_data: dict[str, Any], current_gw: int) -> list[str]:
    """
    Chips the manager still holds this season.

    Any chip row with an ``event`` in history is treated as already played.
    Wildcard is once per half-season (GW1–19 / GW20–38).
    """
    chips = history_data.get("chips") or []
    played = {
        str(c.get("name"))
        for c in chips
        if c.get("event") is not None and c.get("name")
    }
    first_half_boundary = 19
    in_second_half = int(current_gw) > first_half_boundary
    wildcard_first = any(
        c.get("name") == "wildcard"
        and c.get("event") is not None
        and int(c["event"]) <= first_half_boundary
        for c in chips
    )
    wildcard_second = any(
        c.get("name") == "wildcard"
        and c.get("event") is not None
        and int(c["event"]) > first_half_boundary
        for c in chips
    )
    available: list[str] = []
    if in_second_half:
        if not wildcard_second:
            available.append("wildcard")
    elif not wildcard_first:
        available.append("wildcard")
    if "freehit" not in played:
        available.append("freehit")
    if "3xc" not in played:
        available.append("triple_captain")
    if "bboost" not in played:
        available.append("bench_boost")
    return available


def _manager_chips_from_available(available: list[str]) -> list[str]:
    """Map Pitchcraft chip keys → Manager Agent ``chips_available`` names."""
    out: list[str] = []
    if "triple_captain" in available:
        out.append("triple_captain")
    if "bench_boost" in available:
        out.append("bench_boost")
    if "wildcard" in available:
        out.append("wildcard")
    if "freehit" in available:
        out.append("free_hit")
    return out


def _fetch_event_live_points(event_id: int) -> dict[int, int]:
    """Map element_id → points scored in gameweek ``event_id``.

    Uses the FPL "live" endpoint, which returns every element's stats for the
    gameweek in a single request (so the sidebar can show per-GW points without
    one call per player).
    """
    try:
        r = requests.get(
            f"https://fantasy.premierleague.com/api/event/{int(event_id)}/live/",
            headers=FPL_REQUEST_HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        elements = r.json().get("elements") or []
        out: dict[int, int] = {}
        for el in elements:
            eid = el.get("id")
            stats = el.get("stats") or {}
            if eid is not None:
                out[int(eid)] = int(stats.get("total_points") or 0)
        return out
    except Exception:
        return {}


def _current_active_gw(events: list) -> int | None:
    """Real-world active gameweek from FPL bootstrap (is_current → is_next)."""
    ev = _fpl_event_for_picks(events or [])
    return int(ev["id"]) if ev else None


def _season_max_pts(history: list[dict], gw: int | None) -> int | None:
    """Highest single-GW score across full season history up to *gw* (exclusive)."""
    rows = [
        h
        for h in history
        if h.get("round") is not None
        and (gw is None or int(h.get("round")) < int(gw))
    ]
    if not rows:
        return None
    return max(int(h.get("total_points") or 0) for h in rows)


def _fetch_player_deep_stats(
    element_id: int,
    gw: int | None,
    bootstrap: dict | None,
) -> dict[str, Any]:
    """Deep player research payload from bootstrap + element-summary."""
    bootstrap = bootstrap or {}
    bs_by_id, team_short, team_codes = _bootstrap_element_maps(bootstrap)
    el = bs_by_id.get(int(element_id), {})
    events = bootstrap.get("events") or []
    finished_ids = {int(e["id"]) for e in events if e.get("finished")}
    team_matches = len(finished_ids)
    if team_matches == 0:
        active = _current_active_gw(events)
        team_matches = max(0, (active or 1) - 1)

    tid = el.get("team")
    team_name = ""
    if tid is not None:
        team_name = next(
            (
                str(t.get("name") or "")
                for t in (bootstrap.get("teams") or [])
                if int(t.get("id") or -1) == int(tid)
            ),
            "",
        )

    et = int(el.get("element_type") or 3)
    pos_ui = FPL_ELEMENT_TYPE_UI.get(et, "MID")

    minutes = int(el.get("minutes") or 0)
    starts = int(el.get("starts") or 0)
    max_possible_minutes = team_matches * 90
    minutes_played_pct = (
        round((minutes / max_possible_minutes) * 100, 1) if max_possible_minutes else 0.0
    )
    start_pct = round((starts / team_matches) * 100, 1) if team_matches else 0.0

    history: list[dict] = []
    try:
        sr = requests.get(
            f"https://fantasy.premierleague.com/api/element-summary/{int(element_id)}/",
            headers=FPL_REQUEST_HEADERS,
            timeout=15,
        )
        sr.raise_for_status()
        history = sr.json().get("history") or []
    except Exception:
        history = []

    hist_pts = [int(h.get("total_points") or 0) for h in history]
    max_pts = _season_max_pts(history, gw)
    median_pts = round(float(np.median(hist_pts)), 1) if hist_pts else round(
        float(el.get("points_per_game") or 0), 1
    )

    current_gw_ev = next((e for e in events if e.get("is_current")), None)
    next_gw_ev = next((e for e in events if e.get("is_next")), None)
    current_gw = int(current_gw_ev["id"]) if current_gw_ev else None
    next_gw = int(next_gw_ev["id"]) if next_gw_ev else None

    gw_points: int | None = None
    gw_started = False
    if gw is not None:
        gw_started = int(gw) in finished_ids
        if gw_started:
            live = _fetch_event_live_points(int(gw))
            if live and int(element_id) in live:
                gw_points = int(live[int(element_id)])
            elif history:
                hist_row = next(
                    (h for h in history if int(h.get("round") or -1) == int(gw)),
                    None,
                )
                if hist_row is not None:
                    gw_points = int(hist_row.get("total_points") or 0)

    fname = str(el.get("first_name") or "")
    lname = str(el.get("second_name") or "")
    web_name = el.get("web_name") or f"Player {element_id}"
    full_name = (fname + " " + lname).strip() or web_name

    return {
        "id": int(element_id),
        "name": full_name,
        "web_name": web_name,
        "club": team_name or "?",
        "team_id": int(tid) if tid is not None else None,
        "team_code": team_codes.get(int(tid)) if tid is not None else None,
        "element_type": et,
        "teamShort": team_short.get(int(tid), "???") if tid is not None else "???",
        "position": pos_ui,
        "gw_points": gw_points,
        "gw_started": gw_started,
        "context_gw": int(gw) if gw is not None else None,
        "total_points": int(el.get("total_points") or 0),
        "form": el.get("form"),
        "ep_next": el.get("ep_next"),
        "ep_this": el.get("ep_this"),
        "current_gw": current_gw,
        "next_gw": next_gw,
        "goals": int(el.get("goals_scored") or 0),
        "assists": int(el.get("assists") or 0),
        "clean_sheets": int(el.get("clean_sheets") or 0),
        "max_pts": max_pts,
        "median_pts": median_pts,
        "xg": round(float(el.get("expected_goals") or 0), 2),
        "xa": round(float(el.get("expected_assists") or 0), 2),
        "xga": round(float(el.get("expected_goal_involvements") or 0), 2),
        "minutes": minutes,
        "starts": starts,
        "team_matches_played": team_matches,
        "max_possible_minutes": max_possible_minutes,
        "minutes_played_pct": minutes_played_pct,
        "start_pct": start_pct,
        "ownership": float(el.get("selected_by_percent") or 0),
        "price": round(float(el.get("now_cost") or 0) / 10.0, 1),
        "points_history": sorted(
            [
                {
                    "gw": int(h.get("round")),
                    "points": int(h.get("total_points") or 0),
                }
                for h in history
                if h.get("round") is not None
                and (gw is None or int(h.get("round")) < int(gw))
            ],
            key=lambda row: row["gw"],
        ),
    }


@app.get("/api/player/{element_id}")
def get_player_deep_stats(
    element_id: int,
    gw: int | None = Query(None, description="Gameweek context for GW points display"),
):
    """Deep FPL research stats for the player stats modal."""
    bootstrap: dict[str, Any] = {}
    try:
        br = requests.get(FPL_BOOTSTRAP_URL, headers=FPL_REQUEST_HEADERS, timeout=15)
        br.raise_for_status()
        bootstrap = br.json()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to load FPL bootstrap: {exc}",
        ) from exc

    bs_by_id, _, _ = _bootstrap_element_maps(bootstrap)
    if int(element_id) not in bs_by_id:
        raise HTTPException(status_code=404, detail=f"FPL element {element_id} not found.")

    return _to_json(_fetch_player_deep_stats(element_id, gw, bootstrap))


@app.get("/api/players")
async def get_all_players(
    gw: int | None = Query(
        None,
        description="Selected gameweek — xPts mapped from the model for this GW.",
    ),
    season: str | None = Query(None),
):
    """
    All active FPL players with universal xPts for the requested gameweek.

    Each player's ``xPts`` comes from the Stats Agent for ``gw`` (or the
    planning GW when omitted). Players without a model row fall back to FPL
    ``ep_next``.
    """
    try:
        br = await asyncio.to_thread(
            requests.get,
            FPL_BOOTSTRAP_URL,
            headers=FPL_REQUEST_HEADERS,
            timeout=15,
        )
        br.raise_for_status()
        bootstrap = br.json()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to load FPL bootstrap: {exc}",
        ) from exc

    players, gw_eff, season_eff = _map_players_with_gw_predictions(
        bootstrap,
        season=season,
        gameweek=gw,
        live_gw=gw,
    )
    return _to_json(
        {
            "players": players,
            "gameweek": gw_eff,
            "season": season_eff or None,
        }
    )


@app.get("/api/event/{gw}/live-points")
def get_event_live_points_api(gw: int):
    """
    Live element_id → total_points for an in-progress or finished gameweek.

    Used by the Pitchcraft UI to refresh actual GW scores during the active
    round without re-fetching the full squad envelope.
    """
    pts = _fetch_event_live_points(int(gw))
    return _to_json(
        {
            "gameweek": int(gw),
            "points": {str(k): v for k, v in pts.items()},
        }
    )


@app.get("/api/squad")
def get_pitchcraft_squad(
    entry: int | None = Query(
        None,
        description="FPL manager entry ID (optional — demo squad if omitted)",
    ),
    bank: float = Query(0.5),
    free_transfers: int = Query(1),
    gameweek: int | None = Query(None),
    season: str | None = Query(None),
    gw: int | None = Query(
        None,
        description="Historical gameweek — fetch the manager's lineup for this GW. "
        "Defaults to the most recent completed gameweek.",
    ),
):
    """
    Bootstrap payload for the Pitchcraft UI: squad layout + enriched player rows.

    When ``entry`` is set, pulls live picks from the official FPL API (requires
    outbound network). Otherwise serves the built-in demo ``PITCHCRAFT_DEMO_IDS``.

    When ``gw`` is provided, the manager's lineup for that specific gameweek is
    fetched instead of the current/auto-resolved gameweek.
    """
    bootstrap: dict[str, Any] = {}
    squad_layout: dict[str, Any] = dict(PITCHCRAFT_DEMO_SQUAD)
    ordered_ids: list[int] = list(PITCHCRAFT_DEMO_IDS)
    overall_rank: int | None = None
    manager_initials = "FC"
    picks_gameweek: int | None = None
    gw_points_map: dict[int, int] = {}

    try:
        br = requests.get(FPL_BOOTSTRAP_URL, headers=FPL_REQUEST_HEADERS, timeout=15)
        br.raise_for_status()
        bootstrap = br.json()
    except Exception:
        bootstrap = {}

    bs_by_id, _, _ = _bootstrap_element_maps(bootstrap) if bootstrap else ({}, {}, {})

    if entry is not None:
        # A manager ID was explicitly requested: fetch their real team from the
        # FPL API and surface failures instead of silently serving demo data.
        try:
            er = requests.get(
                f"https://fantasy.premierleague.com/api/entry/{int(entry)}/",
                headers=FPL_REQUEST_HEADERS,
                timeout=15,
            )
            er.raise_for_status()
            ej = er.json()
            overall_rank = ej.get("summary_overall_rank")
            pf = str(ej.get("player_first_name") or "").strip() or "?"
            pl = str(ej.get("player_last_name") or "").strip() or "?"
            manager_initials = (pf[0] + pl[0]).upper()

            # Pick the gameweek whose lineup to show: an explicit `gw` wins,
            # otherwise auto-resolve to the most recent completed/current GW.
            if gw is not None:
                eid = int(gw)
            else:
                ev = _fpl_event_for_picks(bootstrap.get("events") or [])
                if not ev:
                    raise HTTPException(
                        status_code=502,
                        detail="Could not determine a gameweek from the FPL bootstrap.",
                    )
                eid = int(ev["id"])
            picks_gameweek = eid
            pr = requests.get(
                f"https://fantasy.premierleague.com/api/entry/{int(entry)}/event/{eid}/picks/",
                headers=FPL_REQUEST_HEADERS,
                timeout=15,
            )
            pr.raise_for_status()
            squad_layout, ordered_ids = _parse_fpl_picks_to_pitchcraft(
                pr.json(), bs_by_id
            )
            # Per-player points actually scored in this gameweek (one request for
            # the whole GW) so the sidebar's "GW Pts" tracks the selected GW.
            gw_points_map = _fetch_event_live_points(eid)
        except HTTPException:
            raise
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", 502)
            if status == 404:
                raise HTTPException(
                    status_code=404,
                    detail=f"FPL manager {entry} not found (or no squad for this gameweek).",
                ) from exc
            raise HTTPException(
                status_code=502,
                detail=f"FPL API error while loading manager {entry} (HTTP {status}).",
            ) from exc
        except Exception as exc:  # network/parse errors
            raise HTTPException(
                status_code=502,
                detail=f"Failed to load FPL manager {entry}: {exc}",
            ) from exc

    result = _get_or_run_agent(season=season, gameweek=gameweek)
    gw_eff = result.get("gameweek")
    season_eff = result.get("season")
    players_rows = _pitchcraft_player_rows(
        result, ordered_ids, bootstrap if bootstrap else None, gw_points_map
    )

    # Manager-level aggregate stats (only meaningful for a real entry).
    squad_stats = (
        _fetch_manager_squad_stats(entry, gw=picks_gameweek)
        if entry is not None
        else {}
    )

    current_active_gw = _current_active_gw(bootstrap.get("events") or []) if bootstrap else None

    available_chips: list[str] = []
    available_free_transfers = free_transfers
    if entry is not None:
        hist = _fetch_fpl_entry_history(entry)
        planning_gw = current_active_gw or picks_gameweek or gw_eff or 1
        available_chips = _compute_available_chips(hist, int(planning_gw))
        available_free_transfers = _compute_banked_free_transfers(hist)

    return _to_json(
        {
            "gameweek": gw_eff,
            "season": season_eff,
            "bank": bank,
            "free_transfers": available_free_transfers,
            "available_free_transfers": available_free_transfers,
            "available_chips": available_chips,
            "entry": entry,
            "overall_rank": overall_rank,
            "manager_initials": manager_initials,
            "picks_gameweek": picks_gameweek,
            "current_active_gw": current_active_gw,
            "squad": squad_layout,
            "players": players_rows,
            "squad_stats": squad_stats,
        }
    )


@app.get("/api/squad/{fpl_id}")
def get_pitchcraft_squad_by_id(
    fpl_id: int,
    bank: float = Query(0.5),
    free_transfers: int = Query(1),
    gameweek: int | None = Query(None),
    season: str | None = Query(None),
    gw: int | None = Query(
        None,
        description="Historical gameweek to view (defaults to most recent).",
    ),
):
    """
    Path-param alias for ``GET /api/squad?entry=<fpl_id>``.

    The Pitchcraft "Load Team" button calls ``/api/squad/<fpl_id>``; this route
    forwards the manager ID to the query-param handler so the same enriched
    ``{squad, players, …}`` envelope is returned. Pass ``?gw=<n>`` to view the
    manager's lineup for a specific historical gameweek.
    """
    return get_pitchcraft_squad(
        entry=fpl_id,
        bank=bank,
        free_transfers=free_transfers,
        gameweek=gameweek,
        season=season,
        gw=gw,
    )


@app.post("/api/optimize")
def post_pitchcraft_optimize(req: OptimizeRequest):
    """
    Manager Agent optimal XI / captaincy + Sporting Director transfers.

    Returns Pitchcraft-ready ``squad`` + merged ``players`` plus raw ``manager``
    and ``transfers`` payloads for debugging / richer UI.
    """
    ids = list(req.player_ids)[:15]
    if len(ids) != 15:
        raise HTTPException(
            status_code=422,
            detail="Exactly 15 FPL element IDs required for optimisation.",
        )

    # Pull the manager's real purchase prices so transfer bank math uses the
    # true FPL selling price (50% profit tax), not the player's now_cost.
    purchase_prices = (
        _fetch_fpl_purchase_prices(req.fpl_id) if req.fpl_id else {}
    )

    available_chips: list[str] = []
    available_free_transfers = max(0, int(req.free_transfers))
    if req.fpl_id:
        hist = _fetch_fpl_entry_history(int(req.fpl_id))
        try:
            br = requests.get(FPL_BOOTSTRAP_URL, headers=FPL_REQUEST_HEADERS, timeout=15)
            br.raise_for_status()
            planning_gw = _current_active_gw(br.json().get("events") or []) or 1
        except Exception:
            planning_gw = 1
        available_chips = _compute_available_chips(hist, int(planning_gw))
        available_free_transfers = _compute_banked_free_transfers(hist)

    mgr_chips = _manager_chips_from_available(available_chips)

    mgr_resp = get_manager(
        ManagerRequest(
            player_ids=ids,
            bank=req.bank,
            gameweek=req.gameweek,
            season=req.season,
            triple_captain="triple_captain" in available_chips,
            bench_boost="bench_boost" in available_chips,
            chips_available=mgr_chips or None,
        )
    )
    xfer_resp = get_transfers(
        TransfersRequest(
            player_ids=ids,
            bank=req.bank,
            free_transfers=available_free_transfers,
            gameweek=req.gameweek,
            season=req.season,
            purchase_prices=purchase_prices or None,
        )
    )

    mgr_data = _json_response_payload(mgr_resp)
    xfer_data = _json_response_payload(xfer_resp)

    squad_pc = _pitchcraft_squad_from_manager_json(mgr_data)
    ordered: list[int] = []
    for row in mgr_data.get("starting_xi") or []:
        ordered.append(int(row["id"]))
    for row in mgr_data.get("bench") or []:
        ordered.append(int(row["id"]))

    try:
        br = requests.get(FPL_BOOTSTRAP_URL, timeout=15)
        br.raise_for_status()
        bootstrap_live = br.json()
    except Exception:
        bootstrap_live = {}

    result = _get_or_run_agent(season=req.season, gameweek=req.gameweek)
    players_rows = _pitchcraft_player_rows(
        result, ordered, bootstrap_live if bootstrap_live else None
    )

    xfer_data["available_chips"] = available_chips
    xfer_data["available_free_transfers"] = available_free_transfers

    return _to_json(
        {
            "gameweek": mgr_data.get("gameweek"),
            "season": xfer_data.get("season") or mgr_data.get("season"),
            "bank": req.bank,
            "free_transfers": available_free_transfers,
            "available_free_transfers": available_free_transfers,
            "available_chips": available_chips,
            "squad": squad_pc,
            "players": players_rows,
            "manager": mgr_data,
            "transfers": xfer_data,
        }
    )
