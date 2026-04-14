"""
multi_transfer_evaluator.py
===========================
Evaluates T1+T2 double-transfer pairs for the Sporting Director Agent.

Algorithm (per spec §7 Node 6):
  1. Take the top t1_candidates options from single_transfer_options as T1 candidates.
  2. For each T1:
     a. Simulate post-T1 squad: remove sell, add buy, update bank.
     b. Re-score single transfers on the simulated squad with transfers_used=1
        so hit_cost = max(0, 2 - free_transfers) × 4.
     c. Find the best T2 (highest vorp_gain) that passes the hit-cost gate.
     d. Flag budget_unlock=True if T2's buy was unaffordable pre-T1 but is
        affordable post-T1.
  3. Select the best T1+T2 pair by combined vorp_gain_T1 + vorp_gain_T2.

Reference: SPORTING_DIRECTOR.md §7 Node 6
"""

from __future__ import annotations

import copy
from typing import Dict, List, Optional, Tuple

from .schemas import PlayerProfile, Squad, TransferOption
from .squad_validator import SquadValidator
from .vorp_calculator import VORPCalculator


class MultiTransferEvaluator:
    """
    Finds the best T1+T2 double-transfer pair.

    Usage:
        evaluator = MultiTransferEvaluator()
        result = evaluator.evaluate(
            squad, pool, validator, position_stats,
            single_transfers, bank, free_transfers,
            t1_candidates=3,
        )
        if result:
            t1, t2 = result
    """

    def evaluate(
        self,
        squad: Squad,
        pool: List[PlayerProfile],
        validator: SquadValidator,
        position_stats: Dict[str, dict],
        single_transfers: List[TransferOption],
        bank: float,
        free_transfers: int,
        t1_candidates: int = 3,
        max_transfers: int = 2,
    ) -> Optional[Tuple[TransferOption, TransferOption]]:
        """
        Evaluate the best T1+T2 pair.

        Args:
            squad:            Current squad.
            pool:             Available (non-squad) player pool.
            validator:        SquadValidator instance.
            position_stats:   Pre-computed VORP stats from VORPCalculator.
            single_transfers: Pre-scored single-transfer options (best-first).
            bank:             Current bank balance in £m.
            free_transfers:   Free transfers available this GW.
            t1_candidates:    How many top T1 options to explore.
            max_transfers:    Cap on transfers to evaluate (must be >= 2).

        Returns:
            (T1, T2) tuple with the highest combined vorp_gain, or None if no
            valid pair exists (T2 doesn't clear the hit-cost gate).
        """
        if max_transfers < 2 or not single_transfers:
            return None

        # T2 marginal hit cost: T1 has already paid its hit, so T2 only costs
        # 4pts if free_transfers < 2 (one more transfer beyond what's free).
        # The old formula max(0, 2-free_transfers)*4 incorrectly doubled the cost
        # to 8pts when free_transfers=0, rejecting valid T2s.
        hit_cost_t2 = 0 if free_transfers >= 2 else 4
        best_pair: Optional[Tuple[TransferOption, TransferOption]] = None
        best_combined_vorp = float("-inf")

        for t1 in single_transfers[:t1_candidates]:
            # ── Simulate post-T1 squad ────────────────────────────────────────
            post_t1_bank = round(bank + t1.sell.sell_price - t1.buy.cost, 2)
            sim_players  = [
                p for p in squad.players if p.element != t1.sell.element
            ] + [t1.buy]
            sim_squad = Squad(
                players        = sim_players,
                bank           = post_t1_bank,
                free_transfers = free_transfers,
                gameweek       = squad.gameweek,
            )

            # T1 sell player is excluded from T2 sell candidates
            t2_sellable = [
                p for p in validator.get_sellable_players(sim_squad)
                if p.element != t1.sell.element
            ]

            best_t2: Optional[TransferOption] = None
            best_t2_vorp = float("-inf")

            for sell in t2_sellable:
                same_pos_pool = [
                    p for p in pool
                    if p.position == sell.position
                    and p.element != t1.buy.element  # already bought in T1
                ]
                buyable = validator.get_buyable_players(sim_squad, sell, same_pos_pool)

                for buy in buyable:
                    expected_gain = buy.expected_pts - sell.expected_pts
                    if expected_gain <= hit_cost_t2:
                        continue

                    # VORP gain
                    sell_vorp = VORPCalculator.get_player_vorp(sell, position_stats)
                    buy_vorp  = position_stats.get(buy.position, {}).get(
                        "vorp_scores", {}
                    ).get(buy.element, 0.0)
                    vorp_gain = round(buy_vorp - sell_vorp, 4)

                    if vorp_gain <= best_t2_vorp:
                        continue

                    # Budget unlock: was this buy unaffordable before T1?
                    effective_sell = sell.sell_price if sell.sell_price > 0 else sell.cost
                    was_unaffordable = (bank + effective_sell) < buy.cost - 0.01
                    now_affordable   = (post_t1_bank + effective_sell) >= buy.cost - 0.01
                    budget_unlock    = was_unaffordable and now_affordable

                    cost_delta     = round(buy.cost - sell.sell_price, 1)
                    remaining_bank = round(post_t1_bank - cost_delta, 1)

                    best_t2_vorp = vorp_gain
                    best_t2 = TransferOption(
                        sell                 = sell,
                        buy                  = buy,
                        cost_delta           = cost_delta,
                        remaining_bank       = remaining_bank,
                        point_gain_gw        = round(buy.predicted_pts - sell.predicted_pts, 3),
                        expected_gain        = round(expected_gain, 3),
                        fixture_gain         = round(
                            buy.fixture_weighted_score - sell.fixture_weighted_score, 3
                        ),
                        form_gain            = round(buy.avg_pts_last5 - sell.avg_pts_last5, 3),
                        transfer_cost_points = hit_cost_t2,
                        net_expected_gain    = round(expected_gain - hit_cost_t2, 3),
                        score                = vorp_gain,   # use vorp_gain as primary score
                        sell_vorp_score      = sell_vorp,
                        buy_vorp_score       = buy_vorp,
                        vorp_gain            = vorp_gain,
                        budget_unlock_flag   = budget_unlock,
                        transfer_number      = 2,
                        reasoning            = (
                            f"T2 OUT: {sell.name} ({sell.position}, £{sell.sell_price}m sell) | "
                            f"T2 IN: {buy.name} ({buy.position}, £{buy.cost}m) | "
                            f"VORP gain: {vorp_gain:+.3f} | "
                            f"Exp gain: {expected_gain:+.2f} pts | "
                            f"Hit: {hit_cost_t2} pts"
                            + (" | BUDGET UNLOCK" if budget_unlock else "")
                        ),
                    )

            if best_t2 is None:
                continue

            combined_vorp = t1.vorp_gain + best_t2.vorp_gain
            if combined_vorp > best_combined_vorp:
                best_combined_vorp = combined_vorp
                best_pair = (t1, best_t2)

        return best_pair
