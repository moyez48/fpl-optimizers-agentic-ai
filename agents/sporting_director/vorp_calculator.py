"""
vorp_calculator.py
==================
Value Over Replacement Player (VORP) scoring for the Sporting Director Agent.

VORP measures a player's expected points above the replacement level for their
position. The replacement level is the player at the vorp_replacement_pct
percentile of expected_pts within that position cluster.

A player at exactly the replacement level has vorp_score = 0.
Higher is better; negative means below replacement.

Reference: SPORTING_DIRECTOR.md §5
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np

from .schemas import PlayerProfile, POSITIONS


class VORPCalculator:
    """
    Computes VORP scores for transfer evaluation.

    All methods are static — no state, no I/O, trivially unit-testable.

    Usage:
        position_stats = VORPCalculator.build_position_stats(pool, replacement_pct=20)

        # For a pool player (buy candidate):
        vorp = position_stats[player.position]["vorp_scores"][player.element]

        # For a squad player (sell candidate, not in pool):
        vorp = VORPCalculator.get_player_vorp(player, position_stats)
    """

    @staticmethod
    def build_position_stats(
        pool: List[PlayerProfile],
        replacement_pct: int = 20,
    ) -> Dict[str, dict]:
        """
        For each position cluster, compute mean_pts, std_pts, replacement_z,
        and a per-player vorp_score lookup (keyed by element ID).

        Args:
            pool:            Available (non-squad) players.
            replacement_pct: Percentile of expected_pts used as the replacement
                             level. A player at this percentile has vorp_score=0.
                             Default 20 (bottom quintile of the available pool).

        Returns:
            {
                "GK":  {"mean_pts": float, "std_pts": float,
                        "replacement_z": float, "vorp_scores": {element: float}},
                "DEF": {...},
                "MID": {...},
                "FWD": {...},
            }

        Edge cases:
            - Fewer than 2 pool players at a position: vorp_score defaults to 0.
            - std_pts == 0 (all players identical): all vorp_scores are 0.
        """
        position_stats: Dict[str, dict] = {}

        for pos in POSITIONS:
            pos_players = [p for p in pool if p.position == pos]

            if len(pos_players) < 2:
                position_stats[pos] = {
                    "mean_pts":     0.0,
                    "std_pts":      0.0,
                    "replacement_z": 0.0,
                    "vorp_scores":  {p.element: 0.0 for p in pos_players},
                }
                continue

            pts = [p.expected_pts for p in pos_players]
            mean_pts = float(np.mean(pts))
            std_pts  = float(np.std(pts))

            if std_pts == 0:
                position_stats[pos] = {
                    "mean_pts":     mean_pts,
                    "std_pts":      0.0,
                    "replacement_z": 0.0,
                    "vorp_scores":  {p.element: 0.0 for p in pos_players},
                }
                continue

            # Z-score for every pool player at this position
            z_scores = {
                p.element: (p.expected_pts - mean_pts) / std_pts
                for p in pos_players
            }

            # Replacement level: player at the replacement_pct percentile
            replacement_pts = float(np.percentile(pts, replacement_pct))
            replacement_z   = (replacement_pts - mean_pts) / std_pts

            # VORP = z_score − replacement_z  (anchored to 0 at replacement level)
            vorp_scores = {
                elem: round(z - replacement_z, 4)
                for elem, z in z_scores.items()
            }

            position_stats[pos] = {
                "mean_pts":      round(mean_pts, 4),
                "std_pts":       round(std_pts, 4),
                "replacement_z": round(replacement_z, 4),
                "vorp_scores":   vorp_scores,
            }

        return position_stats

    @staticmethod
    def get_player_vorp(
        player: PlayerProfile,
        position_stats: Dict[str, dict],
    ) -> float:
        """
        Compute VORP for a squad player (sell candidate) who is NOT in the pool.

        Uses the same position-level statistics as build_position_stats() so
        squad and pool players are on a comparable scale.

        Args:
            player:          A squad player (sell candidate).
            position_stats:  Output from build_position_stats().

        Returns:
            vorp_score (float). Returns 0.0 if position stats are unavailable
            or std_pts == 0.
        """
        pos_stats = position_stats.get(player.position)
        if not pos_stats or pos_stats["std_pts"] == 0:
            return 0.0

        z = (player.expected_pts - pos_stats["mean_pts"]) / pos_stats["std_pts"]
        return round(z - pos_stats["replacement_z"], 4)
