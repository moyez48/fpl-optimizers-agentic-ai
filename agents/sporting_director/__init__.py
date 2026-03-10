"""
agents/sporting_director/__init__.py
=====================================
Public API for the Sporting Director Agent.

Exports:
  - SportingDirectorAgent   : core domain class (no LangGraph dependency)
  - sporting_director_node  : LangGraph node function (state dict → state dict)
  - run_sporting_director   : convenience runner (no LangGraph setup needed)

LangGraph state contract
-------------------------
The Sporting Director node reads these keys from state:
    state["ranked"]     : dict — Stats Agent ranked player output
    state["bootstrap"]  : dict — FPL bootstrap-static JSON
    state["gameweek"]   : int  — current gameweek (prediction was made for this GW)
    state["squad"]      : dict — serialised Squad (see Squad dataclass)
    state["bank"]       : float (optional, default 0.0) — £m in bank
    state["free_transfers"] : int (optional, default 1)

The node writes these keys back:
    state["transfer_recommendation"] : dict — serialised TransferRecommendation
    state["sd_summary"]              : str  — one-line summary (for Manager Agent)
    state["sd_log"]                  : list[str] — execution log

Standalone usage (no LangGraph)
---------------------------------
    from agents.sporting_director import run_sporting_director
    from agents.sporting_director.schemas import Squad, PlayerProfile
    from agents.stats_agent import run_stats_agent

    # Run Stats Agent first
    stats_result = run_stats_agent(gameweek=29, season="2025-26")

    # Define your squad
    squad = Squad(
        players=[
            PlayerProfile.from_ranked_player(p)
            for p in your_15_player_records
        ],
        bank=2.5,
        free_transfers=1,
        gameweek=29,
    )

    # Run Sporting Director
    recommendation = run_sporting_director(stats_result, squad)
    for transfer in recommendation.recommended_transfers[:3]:
        print(transfer.reasoning)
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from .sporting_director import SportingDirectorAgent
from .schemas import Squad, PlayerProfile, TransferRecommendation


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
            top_n  = state.get("sd_top_n", 10),
            window = state.get("sd_window", 5),
        )
        recommendation = agent.evaluate(state, squad)

        # ── Serialise result ──────────────────────────────────────────────
        rec_dict = dataclasses.asdict(recommendation)

        log.append(
            f"sporting_director_node: complete — "
            f"{len(recommendation.recommended_transfers)} transfers ranked, "
            f"hold={recommendation.hold_flag}, wildcard={recommendation.wildcard_flag}"
        )

        return {
            **state,
            "transfer_recommendation": rec_dict,
            "sd_summary":              recommendation.summary,
            "sd_log":                  recommendation.log,
            "log":                     log,
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
]
