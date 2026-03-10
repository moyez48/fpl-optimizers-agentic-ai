"""
sporting_director.py
====================
Main Sporting Director Agent class.

Responsibilities:
  1. Build a player pool from the Stats Agent's ranked output
  2. Enrich all players (squad + pool) with fixture weighted scores
  3. Enumerate all valid sell→buy pairs
  4. Score and rank every valid pair
  5. Detect wildcard and hold conditions
  6. Return a structured TransferRecommendation

The class has zero LangGraph imports — it is pure domain logic.
The LangGraph node wrapper in __init__.py calls this class.

Usage:
    from agents.sporting_director import run_sporting_director

    # Or directly:
    from agents.sporting_director.sporting_director import SportingDirectorAgent
    agent = SportingDirectorAgent()
    recommendation = agent.evaluate(stats_state, squad)
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .fixture_analyser import FixtureAnalyser
from .squad_validator import SquadValidator
from .transfer_scorer import TransferScorer
from .schemas import (
    PlayerProfile, Squad, TransferOption, TransferRecommendation,
    POSITIONS,
)


class SportingDirectorAgent:
    """
    Evaluates transfer options for one gameweek given the Stats Agent output.

    Args:
        top_n:   Maximum number of transfer recommendations to return.
        window:  Number of upcoming GWs to consider for fixture analysis.

    The agent is stateless between calls to evaluate() — safe to reuse
    across multiple gameweeks or squads.
    """

    # Wildcard trigger: squad needs to be broadly weak for wildcard to make sense.
    # If >= this many squad players have negative form vs average, flag wildcard.
    WILDCARD_UNDERPERFORMER_THRESHOLD = 5
    WILDCARD_MIN_TOP_SCORE = 3.0   # top transfer must score this to trigger wildcard

    def __init__(self, top_n: int = 10, window: int = 5):
        self.top_n    = top_n
        self.window   = window
        self.validator = SquadValidator()
        self.scorer    = TransferScorer()

    def evaluate(
        self,
        stats_state: dict,
        squad: Squad,
    ) -> TransferRecommendation:
        """
        Main entry point. Evaluates all transfers and returns a recommendation.

        Args:
            stats_state: The full output dict from the Stats Agent
                         (StatsAgentState). Must contain:
                         - "ranked"    : dict with position-keyed player lists
                         - "bootstrap" : FPL bootstrap-static JSON
                         - "gameweek"  : int
            squad:       The manager's current 15-player squad.

        Returns:
            TransferRecommendation with top_n best transfers, ranked best-first.
        """
        log: List[str] = []
        gameweek = stats_state.get("gameweek", squad.gameweek)
        next_gw  = gameweek + 1

        # ── Step 1: Build player pool from Stats Agent ranked output ──────────
        player_pool = self._build_player_pool(stats_state["ranked"])
        log.append(
            f"sporting_director: built pool of {len(player_pool)} players "
            f"from Stats Agent output (GW{gameweek})"
        )

        # ── Step 2: Fetch fixtures and enrich all players ─────────────────────
        fixture_analyser = FixtureAnalyser(stats_state["bootstrap"])
        loaded = fixture_analyser.fetch_fixtures(
            from_gameweek=next_gw, window=self.window
        )
        log.extend(fixture_analyser.get_log())

        if loaded:
            fixture_analyser.enrich_players(squad.players, next_gw, self.window)
            fixture_analyser.enrich_players(player_pool, next_gw, self.window)
            log.append(
                f"sporting_director: fixture scores computed for "
                f"{len(squad.players)} squad + {len(player_pool)} pool players"
            )
        else:
            log.append(
                "sporting_director: WARNING — no fixture data loaded. "
                "Fixture component will be 0 for all players."
            )

        # ── Step 3: Score all valid transfer pairs ────────────────────────────
        all_options: List[TransferOption] = []
        sellable = self.validator.get_sellable_players(squad)

        for sell in sellable:
            # Only check players of the same position
            same_pos_pool = [p for p in player_pool if p.position == sell.position]
            buyable = self.validator.get_buyable_players(squad, sell, same_pos_pool)

            for buy in buyable:
                option = self.scorer.score_transfer(
                    sell, buy, squad, transfers_used=0
                )
                all_options.append(option)

        log.append(
            f"sporting_director: evaluated {len(all_options)} valid transfer pairs"
        )

        # ── Step 4: Rank and trim ─────────────────────────────────────────────
        ranked_options = self.scorer.rank_transfers(all_options)
        top_options    = ranked_options[: self.top_n]

        log.append(
            f"sporting_director: top transfer = "
            + (
                f"{top_options[0].sell.name} → {top_options[0].buy.name} "
                f"(score {top_options[0].score:.3f}, "
                f"net gain {top_options[0].net_expected_gain:+.2f} pts)"
                if top_options
                else "none found (all transfers score ≤ 0)"
            )
        )

        # ── Step 5: Wildcard and hold detection ───────────────────────────────
        wildcard_flag = self._detect_wildcard(squad, ranked_options)
        hold_flag     = self._detect_hold(ranked_options)

        if wildcard_flag:
            log.append("sporting_director: WILDCARD flag raised — squad broadly weak")
        if hold_flag:
            log.append(
                "sporting_director: HOLD flag raised — best transfer gain < "
                f"{self.scorer.MIN_WORTHWHILE_GAIN} pts, recommend banking FT"
            )

        # ── Step 6: Build summary stub ────────────────────────────────────────
        summary = self._build_summary_stub(
            top_options, wildcard_flag, hold_flag, squad, next_gw
        )

        return TransferRecommendation(
            gameweek               = next_gw,
            free_transfers_available = squad.free_transfers,
            bank                   = squad.bank,
            recommended_transfers  = top_options,
            wildcard_flag          = wildcard_flag,
            hold_flag              = hold_flag,
            summary                = summary,
            log                    = log,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_player_pool(self, ranked: Dict[str, list]) -> List[PlayerProfile]:
        """
        Convert the Stats Agent's ranked dict into a flat list of PlayerProfiles.

        The ranked dict has keys: ALL, GK, DEF, MID, FWD.
        We use the position-specific lists (GK/DEF/MID/FWD) rather than ALL
        to avoid double-counting players who appear in multiple lists.
        We filter out unavailable players (injured/suspended).
        """
        seen: set = set()
        players: List[PlayerProfile] = []

        for pos in POSITIONS:
            pos_players = ranked.get(pos, [])
            for record in pos_players:
                name = record.get("name")
                if not name or name in seen:
                    continue
                seen.add(name)
                profile = PlayerProfile.from_ranked_player(record)
                if profile.is_available:
                    players.append(profile)

        return players

    def _detect_wildcard(
        self,
        squad: Squad,
        ranked_options: List[TransferOption],
    ) -> bool:
        """
        Recommend wildcard if:
          - 5+ squad players have avg_pts_last5 below their squad average
            (i.e. many underperforming players)
          - AND the top ranked transfer scores above WILDCARD_MIN_TOP_SCORE
            (i.e. there are good players to bring in)

        This avoids falsely triggering wildcard when the whole market is weak.
        """
        if not squad.players:
            return False

        squad_avg = sum(p.avg_pts_last5 for p in squad.players) / len(squad.players)
        underperformers = sum(
            1 for p in squad.players if p.avg_pts_last5 < squad_avg
        )

        top_score = ranked_options[0].score if ranked_options else 0.0

        return (
            underperformers >= self.WILDCARD_UNDERPERFORMER_THRESHOLD
            and top_score >= self.WILDCARD_MIN_TOP_SCORE
        )

    def _detect_hold(self, ranked_options: List[TransferOption]) -> bool:
        """
        Recommend holding the free transfer if the best available transfer
        gains less than MIN_WORTHWHILE_GAIN expected points.

        Rationale: a 1-pt expected gain has high variance. A blank or rotation
        by your new signing wipes it out. Better to bank the FT.
        """
        if not ranked_options:
            return True
        best_gain = ranked_options[0].net_expected_gain
        return best_gain < self.scorer.MIN_WORTHWHILE_GAIN

    def _build_summary_stub(
        self,
        top_options: List[TransferOption],
        wildcard_flag: bool,
        hold_flag: bool,
        squad: Squad,
        next_gw: int,
    ) -> str:
        """
        Build a concise summary string for this recommendation.

        This is deliberately structured data, not prose — Claude turns it
        into a manager briefing in the LLM reasoning node (Weeks 3-4).
        """
        if hold_flag:
            return (
                f"GW{next_gw} recommendation: HOLD. "
                f"Best transfer gain ({top_options[0].net_expected_gain:+.2f} pts) "
                f"is below the {self.scorer.MIN_WORTHWHILE_GAIN} pt threshold. "
                f"Bank the free transfer."
            ) if top_options else f"GW{next_gw}: No beneficial transfers found. Hold."

        if wildcard_flag:
            top3 = ", ".join(
                f"{o.sell.name} -> {o.buy.name}" for o in top_options[:3]
            )
            return (
                f"GW{next_gw} recommendation: WILDCARD. "
                f"Squad is broadly underperforming. "
                f"Priority moves: {top3}."
            )

        if not top_options:
            return f"GW{next_gw}: No beneficial transfers identified."

        primary = top_options[0]
        return (
            f"GW{next_gw} recommendation: "
            f"Transfer {primary.sell.name} (GBP{primary.sell.cost}m) "
            f"-> {primary.buy.name} (GBP{primary.buy.cost}m). "
            f"Expected gain: {primary.net_expected_gain:+.2f} pts "
            f"({'free' if primary.transfer_cost_points == 0 else f'{primary.transfer_cost_points}-pt hit'}). "
            f"Bank after: GBP{primary.remaining_bank}m."
        )
