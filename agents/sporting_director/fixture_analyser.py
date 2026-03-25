"""
fixture_analyser.py
===================
Fetches FPL fixture difficulty ratings and computes a weighted score
for each team across a configurable gameweek window.

Data source:
  Live:    https://fantasy.premierleague.com/api/fixtures/?event=N
  Cached:  data/fixtures_cache.json  (written after first successful fetch)

Fixture scoring:
  - FDR runs 1 (easiest) to 5 (hardest).
  - We invert it: score = 6 - adjusted_fdr, so easier fixtures = higher score.
  - Home advantage: FDR reduced by 0.5 for home games.
  - Decay weights (GW+1 is most valuable, GW+5 barely matters):
        GW+1: 40%,  GW+2: 30%,  GW+3: 15%,  GW+4: 10%,  GW+5: 5%
  - A double gameweek adds both fixture scores for that GW window slot.
  - A blank gameweek contributes 0 for that slot.

Usage:
    analyser = FixtureAnalyser(bootstrap)
    analyser.fetch_fixtures(from_gameweek=30)
    enriched_players = analyser.enrich_players(players, from_gameweek=30, window=5)
"""

from __future__ import annotations

import json
import os
import requests
from typing import Dict, List, Optional, Tuple

from .schemas import PlayerProfile, FixtureRating


# ── Constants ─────────────────────────────────────────────────────────────────
FPL_FIXTURES_URL    = "https://fantasy.premierleague.com/api/fixtures/"
FIXTURES_CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "fixtures_cache.json"
)

# Decay weights for GW+1 through GW+5
# Must sum to 1.0
DECAY_WEIGHTS = {1: 0.40, 2: 0.30, 3: 0.15, 4: 0.10, 5: 0.05}

# Home-game FDR reduction (playing at home is meaningfully easier)
HOME_ADVANTAGE_REDUCTION = 0.5

# Fixture score: 6 - adjusted_fdr (so FDR 1 → score 5.0, FDR 5 → score 1.0)
FDR_BASELINE = 6


class FixtureAnalyser:
    """
    Loads and analyses FPL fixture difficulty for teams over a GW window.

    The bootstrap dict (from the Stats Agent or fetched directly) provides
    the team ID → name mapping. Fixture data is fetched from the FPL API
    (or loaded from cache if offline).
    """

    def __init__(self, bootstrap: dict):
        """
        Args:
            bootstrap: The FPL bootstrap-static JSON dict.
                       Used to resolve team IDs to names.
        """
        self.team_map: Dict[int, str] = {
            t["id"]: t["name"] for t in bootstrap.get("teams", [])
        }
        # {team_name: {gameweek: [FixtureRating, ...]}}
        # A team can have 2 fixtures in one GW (double gameweek).
        self._fixtures: Dict[str, Dict[int, List[FixtureRating]]] = {}
        self._log: List[str] = []

    # ── Data Fetching ─────────────────────────────────────────────────────────

    def fetch_fixtures(
        self,
        from_gameweek: int,
        window: int = 5,
        timeout: int = 10,
    ) -> bool:
        """
        Fetch and parse fixture data for gameweeks from_gameweek to
        from_gameweek + window - 1.

        Tries the FPL API first, falls back to fixtures_cache.json.

        Returns:
            True if fixtures were loaded successfully, False otherwise.
        """
        raw_fixtures = self._fetch_raw(timeout)
        if raw_fixtures is None:
            self._log.append("fixture_analyser: no fixture data available")
            return False

        gw_end = from_gameweek + window - 1
        self._fixtures = {}

        for fx in raw_fixtures:
            gw = fx.get("event")
            if gw is None or gw < from_gameweek or gw > gw_end:
                continue

            team_h_id   = fx["team_h"]
            team_a_id   = fx["team_a"]
            team_h_name = self.team_map.get(team_h_id, f"Team{team_h_id}")
            team_a_name = self.team_map.get(team_a_id, f"Team{team_a_id}")
            fdr_h       = int(fx.get("team_h_difficulty", 3))
            fdr_a       = int(fx.get("team_a_difficulty", 3))

            home_rating = FixtureRating(
                team         = team_h_name,
                gameweek     = gw,
                opponent     = team_a_name,
                is_home      = True,
                fdr          = fdr_h,
                adjusted_fdr = max(1.0, fdr_h - HOME_ADVANTAGE_REDUCTION),
            )
            away_rating = FixtureRating(
                team         = team_a_name,
                gameweek     = gw,
                opponent     = team_h_name,
                is_home      = False,
                fdr          = fdr_a,
                adjusted_fdr = float(fdr_a),
            )

            for rating in (home_rating, away_rating):
                self._fixtures.setdefault(rating.team, {})
                self._fixtures[rating.team].setdefault(rating.gameweek, [])
                self._fixtures[rating.team][rating.gameweek].append(rating)

        n_teams = len(self._fixtures)
        self._log.append(
            f"fixture_analyser: loaded fixtures GW{from_gameweek}-GW{gw_end} "
            f"for {n_teams} teams"
        )
        return n_teams > 0

    def _fetch_raw(self, timeout: int) -> Optional[list]:
        """
        Try FPL API first, then local cache.
        Returns raw fixture list or None if both fail.
        """
        try:
            resp = requests.get(FPL_FIXTURES_URL, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            self._cache_fixtures(data)
            self._log.append("fixture_analyser: fetched live fixtures from FPL API")
            return data
        except Exception as e:
            self._log.append(f"fixture_analyser: API failed ({e}), trying cache")

        if os.path.exists(FIXTURES_CACHE_PATH):
            try:
                with open(FIXTURES_CACHE_PATH, encoding="utf-8") as f:
                    data = json.load(f)
                self._log.append("fixture_analyser: loaded cached fixtures")
                return data
            except Exception as e:
                self._log.append(f"fixture_analyser: cache load failed ({e})")

        return None

    def _cache_fixtures(self, data: list) -> None:
        """Write fetched fixtures to local cache for offline use."""
        try:
            os.makedirs(os.path.dirname(FIXTURES_CACHE_PATH), exist_ok=True)
            with open(FIXTURES_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            pass  # Cache write failing is non-fatal

    # ── Scoring ───────────────────────────────────────────────────────────────

    def get_team_fixture_score(
        self,
        team: str,
        from_gameweek: int,
        window: int = 5,
    ) -> Tuple[float, List[FixtureRating]]:
        """
        Compute the weighted fixture score for a team over the next `window` GWs.

        Score formula per GW slot:
            slot_score = sum(FDR_BASELINE - r.adjusted_fdr for r in slot_fixtures)
            weighted   = slot_score × DECAY_WEIGHTS[slot_index]

        - Higher score = EASIER fixtures = better for FPL returns.
        - Double gameweek: both fixture scores are summed for that slot.
        - Blank gameweek: contributes 0 (player earns nothing).

        Returns:
            (total_weighted_score, flat list of all FixtureRating objects)
        """
        team_fixtures = self._fixtures.get(team, {})
        total_score   = 0.0
        all_ratings:  List[FixtureRating] = []

        for slot_idx in range(1, window + 1):
            gw = from_gameweek + slot_idx - 1
            weight = DECAY_WEIGHTS.get(slot_idx, 0.0)
            gw_fixtures = team_fixtures.get(gw, [])  # empty list = blank GW

            slot_score = sum(
                FDR_BASELINE - r.adjusted_fdr for r in gw_fixtures
            )
            total_score += slot_score * weight
            all_ratings.extend(gw_fixtures)

        return round(total_score, 3), all_ratings

    # ── Enrichment ────────────────────────────────────────────────────────────

    def enrich_players(
        self,
        players: List[PlayerProfile],
        from_gameweek: int,
        window: int = 5,
    ) -> List[PlayerProfile]:
        """
        Populate fixture_weighted_score and fixture_scores on each player.

        Call this once on both the squad and the player pool before scoring
        any transfers. Mutates the PlayerProfile objects in-place.

        Args:
            players:       List of PlayerProfile objects to enrich.
            from_gameweek: First GW of the fixture window (typically next GW).
            window:        Number of GWs to look ahead (default 5).

        Returns:
            The same list, with fixture fields populated.
        """
        missing_teams = set()

        for player in players:
            score, ratings = self.get_team_fixture_score(
                player.team, from_gameweek, window
            )
            player.fixture_weighted_score = score
            player.fixture_scores = [r.adjusted_fdr for r in ratings]

            if score == 0.0 and player.team not in self._fixtures:
                missing_teams.add(player.team)

        if missing_teams:
            self._log.append(
                f"fixture_analyser: no fixture data for teams: {sorted(missing_teams)}. "
                f"Those players will score 0 on fixture component."
            )

        return players

    # ── Utility ───────────────────────────────────────────────────────────────

    def get_log(self) -> List[str]:
        return list(self._log)

    def get_fixture_data(self) -> Dict[str, Dict[int, list]]:
        """
        Return the internal fixture dict for consumption by SquadHealthAnalyser.

        Structure: {team_name: {gameweek: [FixtureRating, ...]}}
        An empty dict is returned if fetch_fixtures() has not been called yet
        or failed.
        """
        return dict(self._fixtures)

    def fixture_summary(self, team: str, from_gameweek: int, window: int = 5) -> str:
        """
        Human-readable fixture run for a team.
        E.g. "Arsenal: BUR(H,2) → MCI(A,5) → CHE(H,3)"
        """
        team_fixtures = self._fixtures.get(team, {})
        parts = []
        for slot_idx in range(1, window + 1):
            gw = from_gameweek + slot_idx - 1
            gw_fixtures = team_fixtures.get(gw, [])
            if not gw_fixtures:
                parts.append("BLANK")
            else:
                for r in gw_fixtures:
                    venue = "H" if r.is_home else "A"
                    parts.append(f"{r.opponent[:3].upper()}({venue},{r.fdr})")
        return f"{team}: " + " → ".join(parts)
