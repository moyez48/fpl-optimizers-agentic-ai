"""
sporting_director.py
====================
Main Sporting Director Agent class.

Implements an 8-step pipeline (mirroring the LangGraph nodes in __init__.py):
  1. build_player_pool       — flat list of available PlayerProfiles from ranked output
  2. compute_sell_prices     — populate sell_price on all squad players (price lock)
  3. fetch_enrich_fixtures   — fixture difficulty scores for squad + pool
  4. analyse_squad_health    — per-player health breakdown with flags
  5. score_single_transfers  — VORP-ranked single-transfer options
  6. evaluate_multi_transfer — best T1+T2 pair
  7. detect_wildcard_hold    — wildcard / hold flags
  8. format_output           — assemble TransferRecommendation

The class has zero LangGraph imports — pure domain logic.
The LangGraph node wrapper in __init__.py calls this class.

Usage:
    from agents.sporting_director import run_sporting_director

    # Or directly:
    from agents.sporting_director.sporting_director import SportingDirectorAgent
    agent = SportingDirectorAgent()
    recommendation = agent.evaluate(stats_state, squad)
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .fixture_analyser      import FixtureAnalyser
from .squad_validator       import SquadValidator
from .vorp_calculator       import VORPCalculator
from .squad_health_analyser import SquadHealthAnalyser
from .multi_transfer_evaluator import MultiTransferEvaluator
from .schemas import (
    PlayerProfile, Squad, TransferOption, TransferRecommendation,
    SquadHealthRecord, POSITIONS,
)


class SportingDirectorAgent:
    """
    Evaluates transfer options and squad health for one gameweek.

    Args:
        top_n:               Maximum single-transfer recommendations to return.
        window:              Fixture window in gameweeks.
        replacement_pct:     VORP replacement level percentile (default 20).
        t1_candidates:       Number of T1 options explored in multi-transfer eval.
        max_transfers:       Maximum transfers to evaluate (cap: 3, default: 2).

    The agent is stateless between calls to evaluate() — safe to reuse
    across multiple gameweeks or squads.
    """

    # Wildcard trigger thresholds (placeholder — calibrate in Weeks 5–6)
    WILDCARD_MIN_PLAYERS_WITH_FLAGS = 5   # at least this many players flagged
    WILDCARD_MIN_FLAGS_PER_PLAYER   = 2   # each flagged player must have >= this many flags

    def __init__(
        self,
        top_n:           int = 10,
        window:          int = 5,
        replacement_pct: int = 20,
        t1_candidates:   int = 3,
        max_transfers:   int = 2,
    ):
        self.top_n           = top_n
        self.window          = window
        self.replacement_pct = replacement_pct
        self.t1_candidates   = t1_candidates
        self.max_transfers   = max_transfers

        self.validator  = SquadValidator()
        self.health_analyser = SquadHealthAnalyser()
        self.multi_evaluator = MultiTransferEvaluator()

    def evaluate(
        self,
        stats_state: dict,
        squad: Squad,
    ) -> TransferRecommendation:
        """
        Main entry point. Runs the 8-step pipeline and returns a recommendation.

        Args:
            stats_state: Output dict from the Stats Agent. Must contain:
                         - "ranked"     : dict with position-keyed player lists
                         - "bootstrap"  : FPL bootstrap-static JSON
                         - "gameweek"   : int
                         Optional:
                         - "form_stats" : list of per-player form records
            squad:       The manager's current 15-player squad.

        Returns:
            TransferRecommendation with squad health, transfer options, and flags.
        """
        log: List[str] = []
        error: Optional[str] = None

        try:
            # ── Node 1: build_player_pool ─────────────────────────────────────
            gameweek    = stats_state.get("gameweek", squad.gameweek)
            next_gw     = gameweek + 1
            player_pool = self._node1_build_player_pool(stats_state["ranked"])
            log.append(
                f"[1] build_player_pool: {len(player_pool)} available players "
                f"(GW{gameweek} → planning GW{next_gw})"
            )

            # ── Node 2: compute_sell_prices ───────────────────────────────────
            sellable = self._node2_compute_sell_prices(squad)
            log.append(
                f"[2] compute_sell_prices: sell prices computed for "
                f"{len(sellable)} squad players"
            )

            # ── Node 3: fetch_enrich_fixtures ─────────────────────────────────
            fixture_data, fixture_analyser = self._node3_fetch_enrich_fixtures(
                stats_state["bootstrap"], squad, player_pool, next_gw, log
            )

            # ── Node 4: analyse_squad_health ──────────────────────────────────
            squad_health = self._node4_analyse_squad_health(
                squad, fixture_data, stats_state, next_gw, log
            )

            # ── Node 5: score_single_transfers ────────────────────────────────
            position_stats, single_options = self._node5_score_single_transfers(
                squad, player_pool, log
            )

            # ── Node 6: evaluate_multi_transfer ───────────────────────────────
            multi_pair = self._node6_evaluate_multi_transfer(
                squad, player_pool, position_stats, single_options,
                squad.bank, squad.free_transfers, log
            )

            # ── Node 7: detect_wildcard_hold ──────────────────────────────────
            wildcard_flag, hold_flag = self._node7_detect_wildcard_hold(
                squad_health, single_options, log
            )

            # ── Node 8: format_output ─────────────────────────────────────────
            recommended_transfers = self._node8_format_output(
                single_options, multi_pair
            )

        except Exception as exc:
            error = str(exc)
            log.append(f"sporting_director: FAILED — {exc}")
            # Return a minimal error result
            return TransferRecommendation(
                gameweek                 = squad.gameweek + 1,
                free_transfers_available = squad.free_transfers,
                bank                     = squad.bank,
                squad_health             = [],
                recommended_transfers    = [],
                wildcard_flag            = False,
                hold_flag                = True,
                sd_summary               = f"ERROR: {error}",
                sd_log                   = log,
            )

        summary = self._build_summary(
            recommended_transfers, wildcard_flag, hold_flag, squad, next_gw
        )
        log.append(
            f"[8] format_output: {len(recommended_transfers)} transfer(s) ranked, "
            f"wildcard={wildcard_flag}, hold={hold_flag}"
        )

        return TransferRecommendation(
            gameweek                 = next_gw,
            free_transfers_available = squad.free_transfers,
            bank                     = squad.bank,
            squad_health             = squad_health,
            recommended_transfers    = recommended_transfers,
            wildcard_flag            = wildcard_flag,
            hold_flag                = hold_flag,
            sd_summary               = summary,
            sd_log                   = log,
        )

    # ── Node implementations ──────────────────────────────────────────────────

    def _node1_build_player_pool(self, ranked: Dict[str, list]) -> List[PlayerProfile]:
        """
        Build a flat list of available PlayerProfiles from the Stats Agent's ranked dict.
        Uses position-specific lists (GK/DEF/MID/FWD) to avoid double-counting.
        Deduplicates by element ID. Filters out unavailable players.
        """
        seen: set = set()
        players: List[PlayerProfile] = []
        for pos in POSITIONS:
            for record in ranked.get(pos, []):
                elem = record.get("element")
                if not elem or elem in seen:
                    continue
                seen.add(elem)
                profile = PlayerProfile.from_ranked_player(record)
                if profile.is_available:
                    players.append(profile)
        return players

    def _node2_compute_sell_prices(self, squad: Squad) -> List[PlayerProfile]:
        """
        Compute sell_price on every squad player using the FPL price lock rule.
        Must run before any budget check in any subsequent node.
        """
        return self.validator.get_sellable_players(squad)

    def _node3_fetch_enrich_fixtures(
        self,
        bootstrap: dict,
        squad: Squad,
        player_pool: List[PlayerProfile],
        next_gw: int,
        log: List[str],
    ) -> Tuple[Optional[dict], FixtureAnalyser]:
        """
        Fetch fixture data and enrich squad + pool players with fixture scores.
        Non-fatal: returns None for fixture_data if fetch fails.
        """
        analyser = FixtureAnalyser(bootstrap)
        loaded   = analyser.fetch_fixtures(from_gameweek=next_gw, window=self.window)
        log.extend(analyser.get_log())

        if loaded:
            analyser.enrich_players(squad.players,  next_gw, self.window)
            analyser.enrich_players(player_pool,     next_gw, self.window)
            fixture_data = analyser.get_fixture_data()
            log.append(
                f"[3] fetch_enrich_fixtures: fixture scores computed for "
                f"{len(squad.players)} squad + {len(player_pool)} pool players"
            )
        else:
            fixture_data = None
            log.append(
                "[3] fetch_enrich_fixtures: WARNING — no fixture data. "
                "Fixture component will be 0; blank/double GW flags absent."
            )

        return fixture_data, analyser

    def _node4_analyse_squad_health(
        self,
        squad: Squad,
        fixture_data: Optional[dict],
        stats_state: dict,
        next_gw: int,
        log: List[str],
    ) -> List[SquadHealthRecord]:
        """
        Produce per-player health breakdown with flags.
        """
        health = self.health_analyser.analyse(
            squad_players  = squad.players,
            fixture_data   = fixture_data,
            bootstrap      = stats_state.get("bootstrap"),
            form_stats     = stats_state.get("form_stats"),
            from_gameweek  = next_gw,
            window         = self.window,
        )
        log.append(
            f"[4] analyse_squad_health: {len(health)} records produced, "
            f"{sum(len(r.flags) for r in health)} total flags"
        )
        return health

    def _node5_score_single_transfers(
        self,
        squad: Squad,
        player_pool: List[PlayerProfile],
        log: List[str],
    ) -> Tuple[Dict, List[TransferOption]]:
        """
        Score and rank single-transfer options using VORP.

        Step 1 — Gate:   expected_gain > hit_cost
        Step 2 — Rank:   by vorp_gain descending, cost_delta ascending as tiebreaker
        """
        # Build position-level VORP statistics over the pool
        position_stats = VORPCalculator.build_position_stats(
            player_pool, self.replacement_pct
        )

        hit_cost = max(0, 1 - squad.free_transfers) * 4
        # A rolled free transfer is worth ~0.5 pts in expectation (optionality value).
        # Require that gain clears this floor so we don't recommend sideways moves.
        FT_OPPORTUNITY_COST = 0.5
        min_gain = hit_cost + (FT_OPPORTUNITY_COST if hit_cost == 0 else 0)
        options:  List[TransferOption] = []

        for sell in self.validator.get_sellable_players(squad):
            sell_vorp = VORPCalculator.get_player_vorp(sell, position_stats)

            same_pos_pool = [p for p in player_pool if p.position == sell.position]
            buyable = self.validator.get_buyable_players(squad, sell, same_pos_pool)

            for buy in buyable:
                expected_gain = buy.expected_pts - sell.expected_pts
                if expected_gain <= min_gain:
                    continue   # doesn't clear the gate (includes FT opportunity cost)

                buy_vorp  = position_stats.get(buy.position, {}).get(
                    "vorp_scores", {}
                ).get(buy.element, 0.0)
                vorp_gain = round(buy_vorp - sell_vorp, 4)

                cost_delta     = round(buy.cost - sell.sell_price, 1)
                remaining_bank = round(squad.bank - cost_delta, 1)

                options.append(TransferOption(
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
                    transfer_cost_points = hit_cost,
                    net_expected_gain    = round(expected_gain - hit_cost, 3),
                    score                = vorp_gain,   # use vorp_gain as primary sort key
                    sell_vorp_score      = sell_vorp,
                    buy_vorp_score       = buy_vorp,
                    vorp_gain            = vorp_gain,
                    transfer_number      = 1,
                    reasoning            = (
                        f"OUT: {sell.name} ({sell.position}, £{sell.sell_price}m sell) | "
                        f"IN: {buy.name} ({buy.position}, £{buy.cost}m) | "
                        f"VORP gain: {vorp_gain:+.3f} | "
                        f"Exp gain: {expected_gain:+.2f} pts | "
                        f"Hit: {hit_cost} pts"
                    ),
                ))

        # Rank by vorp_gain desc, cost_delta asc as tiebreaker
        ranked = sorted(options, key=lambda o: (-o.vorp_gain, o.cost_delta))

        # Deduplicate: keep only the best-ranked option per sell player and per buy player
        seen_sell: set = set()
        seen_buy:  set = set()
        deduped: List[TransferOption] = []
        for opt in ranked:
            if opt.sell.element not in seen_sell and opt.buy.element not in seen_buy:
                seen_sell.add(opt.sell.element)
                seen_buy.add(opt.buy.element)
                deduped.append(opt)

        top = deduped[: self.top_n]

        log.append(
            f"[5] score_single_transfers: {len(options)} pairs passed gate; "
            f"top transfer = "
            + (
                f"{top[0].sell.name} → {top[0].buy.name} "
                f"(vorp_gain {top[0].vorp_gain:+.3f}, exp_gain {top[0].expected_gain:+.2f})"
                if top else "none"
            )
        )

        return position_stats, top

    def _node6_evaluate_multi_transfer(
        self,
        squad: Squad,
        player_pool: List[PlayerProfile],
        position_stats: Dict,
        single_options: List[TransferOption],
        bank: float,
        free_transfers: int,
        log: List[str],
    ) -> Optional[Tuple[TransferOption, TransferOption]]:
        """
        Find the best T1+T2 pair. Only runs if max_transfers >= 2.
        """
        if self.max_transfers < 2 or not single_options:
            log.append("[6] evaluate_multi_transfer: skipped (max_transfers < 2 or no T1)")
            return None

        pair = self.multi_evaluator.evaluate(
            squad             = squad,
            pool              = player_pool,
            validator         = self.validator,
            position_stats    = position_stats,
            single_transfers  = single_options,
            bank              = bank,
            free_transfers    = free_transfers,
            t1_candidates     = self.t1_candidates,
            max_transfers     = self.max_transfers,
        )

        if pair:
            t1, t2 = pair
            log.append(
                f"[6] evaluate_multi_transfer: best pair — "
                f"T1 {t1.sell.name}→{t1.buy.name} (vorp {t1.vorp_gain:+.3f}) + "
                f"T2 {t2.sell.name}→{t2.buy.name} (vorp {t2.vorp_gain:+.3f})"
            )
        else:
            log.append("[6] evaluate_multi_transfer: no valid T2 found for any T1")

        return pair

    def _node7_detect_wildcard_hold(
        self,
        squad_health: List[SquadHealthRecord],
        single_options: List[TransferOption],
        log: List[str],
    ) -> Tuple[bool, bool]:
        """
        Wildcard: 5+ players each have 2+ health flags.
        Hold:     no single transfer passed the expected-gain gate.
        """
        players_with_multiple_flags = sum(
            1 for r in squad_health
            if len(r.flags) >= self.WILDCARD_MIN_FLAGS_PER_PLAYER
        )
        wildcard_flag = players_with_multiple_flags >= self.WILDCARD_MIN_PLAYERS_WITH_FLAGS
        hold_flag     = len(single_options) == 0

        if wildcard_flag:
            log.append(
                f"[7] detect_wildcard_hold: WILDCARD — "
                f"{players_with_multiple_flags} players have "
                f">= {self.WILDCARD_MIN_FLAGS_PER_PLAYER} flags"
            )
        if hold_flag:
            log.append(
                "[7] detect_wildcard_hold: HOLD — no transfer passed the gate; "
                "recommend banking the free transfer"
            )

        return wildcard_flag, hold_flag

    def _node8_format_output(
        self,
        single_options: List[TransferOption],
        multi_pair:     Optional[Tuple[TransferOption, TransferOption]],
    ) -> List[TransferOption]:
        """
        Assemble the recommended_transfers list.

        Single-transfer options each become one entry with transfer_number=1.
        The multi-transfer pair becomes two consecutive entries with
        transfer_number=1 and transfer_number=2 respectively.

        Single and multi options are returned together; the Manager Agent
        chooses which to act on.
        """
        transfers: List[TransferOption] = list(single_options)

        if multi_pair:
            t1, t2 = multi_pair
            # Insert the pair at the front if the combined vorp beats the best single
            combined = t1.vorp_gain + t2.vorp_gain
            best_single_vorp = single_options[0].vorp_gain if single_options else float("-inf")
            if combined > best_single_vorp:
                transfers = [t1, t2] + transfers
            else:
                transfers = transfers + [t1, t2]

        # Deduplicate by (sell, buy) pair — T1 of multi_pair is drawn from
        # single_options so it would otherwise appear twice in the list
        seen: set = set()
        deduped: List[TransferOption] = []
        for t in transfers:
            key = (t.sell.element, t.buy.element)
            if key not in seen:
                seen.add(key)
                deduped.append(t)

        return deduped

    # ── Summary ───────────────────────────────────────────────────────────────

    def _build_summary(
        self,
        transfers:     List[TransferOption],
        wildcard_flag: bool,
        hold_flag:     bool,
        squad:         Squad,
        next_gw:       int,
    ) -> str:
        if wildcard_flag:
            top3 = ", ".join(
                f"{o.sell.name}→{o.buy.name}"
                for o in transfers[:3]
                if o.transfer_number == 1
            )
            return (
                f"GW{next_gw}: WILDCARD recommended. "
                f"Squad health is broadly poor. Priority moves: {top3 or 'see transfers'}."
            )

        if hold_flag:
            return (
                f"GW{next_gw}: HOLD. No transfer cleared the expected-gain gate. "
                f"Bank the free transfer."
            )

        if not transfers:
            return f"GW{next_gw}: No beneficial transfers identified."

        primary = next((t for t in transfers if t.transfer_number == 1), transfers[0])
        return (
            f"GW{next_gw}: Transfer {primary.sell.name} (£{primary.sell.sell_price}m) "
            f"→ {primary.buy.name} (£{primary.buy.cost}m). "
            f"VORP gain: {primary.vorp_gain:+.3f} | "
            f"Exp gain: {primary.expected_gain:+.2f} pts "
            f"({'free' if primary.transfer_cost_points == 0 else f'{primary.transfer_cost_points}-pt hit'}). "
            f"Bank after: £{primary.remaining_bank}m."
        )
