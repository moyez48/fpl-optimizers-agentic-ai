"""
transfer_scorer.py
==================
Computes a composite score for every valid sell→buy transfer pair.

This module is a collection of pure, stateless functions wrapped in a class
for namespace clarity. No file I/O, no API calls, no external state.
Safe to call ~9,000 times per evaluation without performance concerns.

Composite score formula
-----------------------
  raw_score = (W_EXPECTED  × expected_gain)    # risk-adjusted pts gain
            + (W_FIXTURE   × fixture_gain)     # fixture quality improvement
            + (W_FORM      × form_gain)        # recent form (last-5 avg)
            + (W_VALUE     × value_gain × 10)  # pts-per-£m (scaled to pts range)

  transfer_cost = 4 × max(0, transfers_used - free_transfers)

  score = raw_score - transfer_cost

All weights are class-level constants — easy to tune via config in Weeks 5-6.
They sum to 1.0.

Why these weights:
  - Expected pts (0.35): the Statistician's model is directly optimised for this.
  - Fixture (0.30):      mid-season fixture swings are the #1 reason FPL managers trade.
  - Form (0.20):         recent form is the best human signal; model already captures it
                         partially, so this adds independent signal.
  - Value (0.15):        tie-breaker; prevents burning premium budget for marginal gains.
"""

from __future__ import annotations

from typing import List

from .schemas import PlayerProfile, Squad, TransferOption


class TransferScorer:
    """
    Scores sell→buy transfer pairs and generates human-readable reasoning.

    Usage:
        scorer = TransferScorer()
        option = scorer.score_transfer(sell, buy, squad, transfers_used_so_far=0)
        ranked = scorer.rank_transfers([option1, option2, ...])
    """

    # ── Composite score weights (must sum to 1.0) ─────────────────────────────
    W_EXPECTED = 0.35
    W_FIXTURE  = 0.30
    W_FORM     = 0.20
    W_VALUE    = 0.15

    # FPL points deducted per transfer beyond free transfers
    HIT_COST = 4

    # Minimum net expected gain for a transfer to be worth recommending
    MIN_WORTHWHILE_GAIN = 2.0

    def score_transfer(
        self,
        sell: PlayerProfile,
        buy: PlayerProfile,
        squad: Squad,
        transfers_used: int = 0,
    ) -> TransferOption:
        """
        Score a single sell→buy pair and return a populated TransferOption.

        Args:
            sell:            The squad player to sell.
            buy:             The pool player to buy.
            squad:           Current squad (for budget and free transfer info).
            transfers_used:  How many transfers have already been made this GW
                             (0 = first transfer, 1 = second, etc.)

        Returns:
            A fully populated TransferOption, including score and reasoning.
        """
        # ── Budget ────────────────────────────────────────────────────────────
        # Use sell_price (price-lock adjusted) not cost — a risen player's
        # sell proceeds are capped at purchase_price + 50% of the rise.
        effective_sell = sell.sell_price if sell.sell_price > 0 else sell.cost
        cost_delta     = round(buy.cost - effective_sell, 1)
        remaining_bank = round(squad.bank - cost_delta, 1)

        # ── Gain metrics (buy − sell) ──────────────────────────────────────────
        point_gain_gw = round(buy.predicted_pts - sell.predicted_pts, 3)
        expected_gain = round(buy.expected_pts  - sell.expected_pts,  3)
        fixture_gain  = round(
            buy.fixture_weighted_score - sell.fixture_weighted_score, 3
        )
        form_gain = round(buy.avg_pts_last5 - sell.avg_pts_last5, 3)

        # Value = expected pts per £m (scaled × 10 to bring into points range)
        buy_value  = buy.expected_pts  / buy.cost  if buy.cost  > 0 else 0.0
        sell_value = sell.expected_pts / sell.cost if sell.cost > 0 else 0.0
        value_gain = round((buy_value - sell_value) * 10, 3)

        # ── Transfer cost ─────────────────────────────────────────────────────
        # Each transfer beyond free_transfers costs HIT_COST points.
        hits = max(0, transfers_used + 1 - squad.free_transfers)
        transfer_cost_points = hits * self.HIT_COST

        # ── Composite score ───────────────────────────────────────────────────
        raw_score = (
            self.W_EXPECTED * expected_gain
            + self.W_FIXTURE  * fixture_gain
            + self.W_FORM     * form_gain
            + self.W_VALUE    * value_gain
        )
        score = round(raw_score - transfer_cost_points, 4)

        # ── Net expected gain (what a human cares about most) ─────────────────
        net_expected_gain = round(expected_gain - transfer_cost_points, 3)

        # ── Human-readable reasoning stub ────────────────────────────────────
        # Claude expands this in Weeks 3-4. Keep it information-dense.
        reasoning = self._generate_reasoning(
            sell, buy, expected_gain, fixture_gain, form_gain,
            transfer_cost_points, net_expected_gain, cost_delta,
        )

        return TransferOption(
            sell                 = sell,
            buy                  = buy,
            cost_delta           = cost_delta,
            remaining_bank       = remaining_bank,
            point_gain_gw        = point_gain_gw,
            expected_gain        = expected_gain,
            fixture_gain         = fixture_gain,
            form_gain            = form_gain,
            transfer_cost_points = transfer_cost_points,
            net_expected_gain    = net_expected_gain,
            score                = score,
            reasoning            = reasoning,
        )

    def rank_transfers(
        self,
        options: List[TransferOption],
        min_score: float = 0.0,
    ) -> List[TransferOption]:
        """
        Sort transfer options by score (descending) and filter out poor ones.

        A transfer with score <= 0 has no expected benefit after paying any hit.
        We use min_score=0 by default — the agent's hold_flag logic uses
        MIN_WORTHWHILE_GAIN separately for the hold/proceed decision.

        Returns:
            Sorted list with score > min_score.
        """
        return sorted(
            [o for o in options if o.score > min_score],
            key=lambda x: x.score,
            reverse=True,
        )

    def _generate_reasoning(
        self,
        sell: PlayerProfile,
        buy: PlayerProfile,
        expected_gain: float,
        fixture_gain: float,
        form_gain: float,
        transfer_cost_points: int,
        net_expected_gain: float,
        cost_delta: float,
    ) -> str:
        """
        Generate a concise, information-dense reasoning string.

        This is deliberately structured so Claude can read it as a prompt
        and write a polished manager briefing around it.

        Example output:
            "OUT: Salah (MID, £13.0m, 4.2 pred pts, FDR 2.8, last5 avg 5.1)
             IN:  Mbeumo (MID, £8.5m, 6.1 pred pts, FDR 1.9, last5 avg 6.3)
             Expected gain: +1.9 pts | Fixture swing: +0.9 | Form: +1.2 | Hit: 0 pts
             Net gain: +1.9 pts | Budget delta: -£4.5m"
        """
        hit_str = f"{transfer_cost_points} pts" if transfer_cost_points > 0 else "free"
        cost_str = (
            f"-GBP{abs(cost_delta)}m" if cost_delta > 0
            else f"+GBP{abs(cost_delta)}m" if cost_delta < 0
            else "+/-GBP0m"
        )
        gain_str = f"+{net_expected_gain:.2f}" if net_expected_gain >= 0 else f"{net_expected_gain:.2f}"

        return (
            f"OUT: {sell.name} ({sell.position}, GBP{sell.cost}m, "
            f"{sell.predicted_pts:.1f} pred pts, "
            f"FDR {sell.fixture_weighted_score:.1f}, last5 avg {sell.avg_pts_last5:.1f}) | "
            f"IN: {buy.name} ({buy.position}, GBP{buy.cost}m, "
            f"{buy.predicted_pts:.1f} pred pts, "
            f"FDR {buy.fixture_weighted_score:.1f}, last5 avg {buy.avg_pts_last5:.1f}) | "
            f"Exp gain: {expected_gain:+.2f} pts | "
            f"Fixture swing: {fixture_gain:+.2f} | "
            f"Form: {form_gain:+.2f} | "
            f"Hit: {hit_str} | "
            f"Net: {gain_str} pts | "
            f"Budget: {cost_str}"
        )
