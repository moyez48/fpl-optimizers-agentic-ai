"""
agents/sporting_director/__init__.py
=====================================
Public API for the Sporting Director Agent.

Exports:
  - SportingDirectorAgent   : core domain class (no LangGraph dependency)
  - sporting_director_node  : LangGraph node function (state dict → state dict)
  - run_sporting_director   : convenience runner (no LangGraph setup needed)

LangGraph state contract (per FPLOptimizerState spec §9)
---------------------------------------------------------
The Sporting Director node reads these keys from state:
    state["ranked"]         : dict  — Stats Agent ranked player output
    state["bootstrap"]      : dict  — FPL bootstrap-static JSON
    state["gameweek"]       : int   — current gameweek
    state["form_stats"]     : list  — per-player form records (optional)
    state["squad"]          : Squad | dict — manager's current 15-player squad
    state["bank"]           : float — £m in bank (default 0.0)
    state["free_transfers"] : int   — free transfers available (default 1)
    state["sd_top_n"]       : int   — max single-transfer recs (default 10)
    state["sd_window"]      : int   — fixture window in GWs (default 5)

The node writes these keys back (per spec §9):
    state["squad_health"]          : list[dict] — per-player health breakdown
    state["recommended_transfers"] : list[dict] — serialised TransferOptions
    state["wildcard_flag"]         : bool
    state["hold_flag"]             : bool
    state["sd_summary"]            : str  — briefing stub for Manager Agent
    state["sd_log"]                : list[str] — execution log

Standalone usage (no LangGraph)
---------------------------------
    from agents.sporting_director import run_sporting_director
    from agents.sporting_director.schemas import Squad, PlayerProfile

    squad = Squad(players=[...], bank=2.5, free_transfers=1, gameweek=29)
    recommendation = run_sporting_director(stats_result, squad)
    for transfer in recommendation.recommended_transfers[:3]:
        print(transfer.reasoning)
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from .sporting_director import SportingDirectorAgent
from .schemas import Squad, PlayerProfile, TransferRecommendation, SquadHealthRecord


# ── Convenience runner (no LangGraph required) ────────────────────────────────

def run_sporting_director(
    stats_state: dict,
    squad: Squad,
    top_n: int = 10,
    window: int = 5,
) -> TransferRecommendation:
    """
    Run the Sporting Director Agent standalone.

    Args:
        stats_state: Output dict from run_stats_agent() or the Stats Agent graph.
        squad:       Manager's current 15-player squad.
        top_n:       How many transfer recommendations to return.
        window:      Fixture window in gameweeks (default 5).

    Returns:
        TransferRecommendation with ranked transfer options.
    """
    agent = SportingDirectorAgent(top_n=top_n, window=window)
    return agent.evaluate(stats_state, squad)


# ── LangGraph node ────────────────────────────────────────────────────────────

def sporting_director_node(state: dict) -> dict:
    """
    LangGraph node for the Sporting Director Agent.

    Reads Stats Agent output from state, builds the Squad from state["squad"],
    runs the agent, and writes the recommendation back to state.

    The Squad can be provided in two ways:
      1. As a pre-built Squad object: state["squad"] = Squad(...)
      2. As a dict: state["squad"] = {"players": [...], "bank": 2.5, ...}
         where each player is a dict with at minimum: name, position, team,
         element, value_m (or value), predicted_pts, expected_pts, start_prob,
         avg_pts_last5, form_trend, goals_last5, assists_last5.

    On error, sets state["error"] (matching Stats Agent error-handling pattern).
    """
    log = list(state.get("log", []))

    # Error pass-through — if Stats Agent failed, skip
    if state.get("error"):
        return state

    try:
        # ── Build Squad from state ─────────────────────────────────────────
        squad = _build_squad_from_state(state)

        # ── Run agent ─────────────────────────────────────────────────────
        agent = SportingDirectorAgent(
            top_n           = state.get("sd_top_n", 10),
            window          = state.get("sd_window", 5),
            replacement_pct = state.get("vorp_replacement_pct", 20),
            t1_candidates   = state.get("t1_candidates", 3),
            max_transfers   = state.get("max_transfers", 2),
        )
        recommendation = agent.evaluate(state, squad)

        # ── Serialise health records ───────────────────────────────────────
        squad_health_dicts = [
            dataclasses.asdict(h) for h in recommendation.squad_health
        ]

        # ── Serialise transfer options ─────────────────────────────────────
        transfer_dicts = [
            dataclasses.asdict(t) for t in recommendation.recommended_transfers
        ]

        log.append(
            f"sporting_director_node: complete — "
            f"{len(recommendation.recommended_transfers)} transfers ranked, "
            f"hold={recommendation.hold_flag}, wildcard={recommendation.wildcard_flag}"
        )

        # ── Write spec §9 state fields ────────────────────────────────────
        return {
            **state,
            "squad_health":          squad_health_dicts,
            "recommended_transfers": transfer_dicts,
            "wildcard_flag":         recommendation.wildcard_flag,
            "hold_flag":             recommendation.hold_flag,
            "sd_summary":            recommendation.sd_summary,
            "sd_log":                recommendation.sd_log,
            "log":                   log,
        }

    except Exception as e:
        log.append(f"sporting_director_node: FAILED — {e}")
        return {**state, "error": f"sporting_director_node: {e}", "log": log}


def _build_squad_from_state(state: dict) -> Squad:
    """
    Extract a Squad from the LangGraph state dict.

    Supports two formats:
      - Already a Squad instance → return as-is
      - A dict with "players" list → build Squad from dicts
    """
    squad_data = state.get("squad")

    if isinstance(squad_data, Squad):
        return squad_data

    if isinstance(squad_data, dict):
        players = [
            PlayerProfile.from_ranked_player(p)
            for p in squad_data.get("players", [])
        ]
        return Squad(
            players        = players,
            bank           = float(squad_data.get("bank", state.get("bank", 0.0))),
            free_transfers = int(squad_data.get("free_transfers", state.get("free_transfers", 1))),
            gameweek       = int(squad_data.get("gameweek", state.get("gameweek", 30))),
        )

    # Fallback: build from top-level state keys
    players = [
        PlayerProfile.from_ranked_player(p)
        for p in state.get("squad_players", [])
    ]
    return Squad(
        players        = players,
        bank           = float(state.get("bank", 0.0)),
        free_transfers = int(state.get("free_transfers", 1)),
        gameweek       = int(state.get("gameweek", 30)),
    )


__all__ = [
    "SportingDirectorAgent",
    "run_sporting_director",
    "sporting_director_node",
    "SquadHealthRecord",
]
