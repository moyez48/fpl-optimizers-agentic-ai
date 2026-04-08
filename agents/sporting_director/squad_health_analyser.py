"""
squad_health_analyser.py
========================
Per-player squad health breakdown for the Sporting Director Agent.

Produces one SquadHealthRecord per squad player, covering five dimensions:
  - Availability (injury/suspension status, chance of playing, yellow cards)
  - Rotation risk  (start probability, average minutes, blank rate)
  - Form           (last-5 average, exponentially weighted form)
  - Volatility     (standard deviation of last-5 points)
  - Fixture        (blank GWs and double GWs in the fixture window)

Plus explicit flags for the most critical conditions. The Manager Agent
consumes these flags to inform XI selection and transfer decisions.

Reference: SPORTING_DIRECTOR.md §6
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .schemas import PlayerProfile, SquadHealthRecord, safe_int

logger = logging.getLogger(__name__)


class SquadHealthAnalyser:
    """
    Produces per-player health breakdowns for a squad.

    All thresholds are class-level constants — calibrate empirically
    in Weeks 5–6 once sufficient season data is available.

    Usage:
        analyser = SquadHealthAnalyser()
        health = analyser.analyse(squad.players, fixture_data, bootstrap, form_stats,
                                  from_gameweek=next_gw, window=5)
    """

    # ── Thresholds (placeholder — calibrate in Weeks 5–6) ────────────────────
    ROTATION_RISK_START_PROB  = 0.60   # start_prob below this → rotation_risk
    ROTATION_RISK_MIN_MINUTES = 45.0   # avg_minutes_last5 below this → rotation_risk
    FORM_DECLINING_THRESHOLD  = 1.5    # avg_pts_last5 - ewm_points above this → form_declining
    HIGH_VOLATILITY_THRESHOLD = 3.5    # std_pts_last5 above this → high_volatility
    SUSPENSION_YELLOW_CARDS   = 10     # yellow card total >= this → suspension_risk

    def analyse(
        self,
        squad_players: List[PlayerProfile],
        fixture_data: Optional[Dict],
        bootstrap: Optional[dict] = None,
        form_stats: Optional[list] = None,
        from_gameweek: Optional[int] = None,
        window: int = 5,
    ) -> List[SquadHealthRecord]:
        """
        Produce a health record for each squad player.

        Args:
            squad_players:  The 15-player squad.
            fixture_data:   {team_name: {gameweek: [FixtureRating, ...]}}
                            from FixtureAnalyser.get_fixture_data().
                            Pass None if fixtures are unavailable — blank/double
                            GW flags will be absent.
            bootstrap:      FPL bootstrap-static JSON. Used to look up status,
                            chance_of_playing, and yellow_cards by element ID.
            form_stats:     List of per-player form records from the Stats Agent.
                            Used to look up avg_minutes_last5, ewm_points,
                            std_pts_last5, blank_rate_last5.
            from_gameweek:  First GW of the fixture window (typically next GW).
            window:         Number of GWs to inspect for blank/double GW flags.

        Returns:
            List[SquadHealthRecord], one per squad player.
        """
        # Build bootstrap lookup: {element_id: element_dict}
        bootstrap_lookup: Dict[int, dict] = {}
        if bootstrap:
            for elem in bootstrap.get("elements", []):
                bootstrap_lookup[elem["id"]] = elem

        # Build form_stats lookups: by element ID and by player name
        form_by_element: Dict[int, dict] = {}
        form_by_name:    Dict[str, dict] = {}
        if form_stats:
            for record in form_stats:
                if "element" in record:
                    eid = safe_int(record.get("element"), None)
                    if eid is not None and eid > 0:
                        form_by_element[eid] = record
                if "name" in record:
                    form_by_name[record["name"]] = record

        # Determine GW range from fixture_data when from_gameweek is not given
        all_gws: set = set()
        if fixture_data:
            for team_fixtures in fixture_data.values():
                all_gws.update(team_fixtures.keys())

        return [
            self._analyse_player(
                player,
                bootstrap_lookup,
                form_by_element,
                form_by_name,
                fixture_data,
                from_gameweek,
                window,
                all_gws,
            )
            for player in squad_players
        ]

    # ── Private ───────────────────────────────────────────────────────────────

    def _analyse_player(
        self,
        player: PlayerProfile,
        bootstrap_lookup: Dict[int, dict],
        form_by_element: Dict[int, dict],
        form_by_name:    Dict[str, dict],
        fixture_data:    Optional[Dict],
        from_gameweek:   Optional[int],
        window:          int,
        all_gws:         set,
    ) -> SquadHealthRecord:

        # ── Bootstrap data ────────────────────────────────────────────────────
        bs = bootstrap_lookup.get(player.element, {})
        status = bs.get("status", player.status)
        yc_raw = bs.get("yellow_cards", player.yellow_cards)
        yellow_cards = safe_int(yc_raw, player.yellow_cards)

        # chance_of_playing: prefer next_round, fall back to this_round or player field
        cop = (
            bs.get("chance_of_playing_next_round")
            or bs.get("chance_of_playing_this_round")
        )
        # FPL sometimes sends null; merged data can leave float NaN — int(NaN) raises
        chance_of_playing = safe_int(cop, player.chance_of_playing)
        is_available = status in ("a", "d")

        # ── Form stats ────────────────────────────────────────────────────────
        form_record = form_by_element.get(player.element) or form_by_name.get(player.name)
        if form_record is None:
            logger.warning(
                "squad_health: no form stats for %s (element %d) — using defaults",
                player.name, player.element,
            )

        def _form(key: str, fallback: float) -> float:
            if form_record and key in form_record:
                return float(form_record[key])
            return fallback

        avg_minutes_last5 = _form("avg_minutes_last5", player.avg_minutes_last5)
        ewm_points        = _form("ewm_points",        player.ewm_points)
        std_pts_last5     = _form("std_pts_last5",     player.std_pts_last5)
        blank_rate_last5  = _form("blank_rate_last5",  player.blank_rate_last5)

        # ── Fixture flags ─────────────────────────────────────────────────────
        has_blank_gw  = False
        has_double_gw = False
        blank_gws:  List[int] = []
        double_gws: List[int] = []

        if fixture_data is not None:
            team_fixtures = fixture_data.get(player.team, {})
            if from_gameweek is not None:
                check_gws = [from_gameweek + i for i in range(window)]
            else:
                check_gws = sorted(all_gws)

            for gw in check_gws:
                gw_fixtures = team_fixtures.get(gw, [])
                if len(gw_fixtures) == 0:
                    has_blank_gw = True
                    blank_gws.append(gw)
                elif len(gw_fixtures) >= 2:
                    has_double_gw = True
                    double_gws.append(gw)

        # ── Build flags ───────────────────────────────────────────────────────
        flags: List[str] = []

        if status in ("i", "s", "u"):
            flags.append("injured")
        elif status == "d":
            flags.append("doubtful")

        if yellow_cards >= self.SUSPENSION_YELLOW_CARDS:
            flags.append("suspension_risk")

        if (player.start_prob < self.ROTATION_RISK_START_PROB
                or avg_minutes_last5 < self.ROTATION_RISK_MIN_MINUTES):
            flags.append("rotation_risk")

        if player.avg_pts_last5 - ewm_points > self.FORM_DECLINING_THRESHOLD:
            flags.append("form_declining")

        for gw in blank_gws:
            flags.append(f"blank_gw_{gw}")

        for gw in double_gws:
            flags.append(f"double_gw_{gw}")

        if std_pts_last5 > self.HIGH_VOLATILITY_THRESHOLD:
            flags.append("high_volatility")

        return SquadHealthRecord(
            name=player.name,
            availability={
                "status":            status,
                "chance_of_playing": chance_of_playing,
                "is_available":      is_available,
                "yellow_cards":      yellow_cards,
            },
            rotation_risk={
                "start_prob":         player.start_prob,
                "avg_minutes_last5":  avg_minutes_last5,
                "blank_rate_last5":   blank_rate_last5,
            },
            form={
                "avg_pts_last5": player.avg_pts_last5,
                "ewm_points":    ewm_points,
            },
            volatility={
                "std_pts_last5": std_pts_last5,
            },
            fixture={
                "has_blank_gw":  has_blank_gw,
                "has_double_gw": has_double_gw,
            },
            flags=flags,
        )
