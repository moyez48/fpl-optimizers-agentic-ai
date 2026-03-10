"""
schemas.py
==========
Data contracts for the Sporting Director Agent.

Every piece of data flowing into or out of the agent is typed here.
Field names deliberately mirror the Stats Agent output (STATS_AGENT.md)
so no renaming or mapping is needed at the boundary.

Position values match the processed CSV: GK, DEF, MID, FWD.
Costs are always in £m (e.g. 6.0 = £6.0m), never the raw FPL 0.1m units.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


# ── Position constants ────────────────────────────────────────────────────────
# These match the values in the processed CSV and Stats Agent output.
POSITIONS = ("GK", "DEF", "MID", "FWD")

# FPL squad construction rules
POSITION_LIMITS = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
SQUAD_SIZE      = 15
MAX_PER_CLUB    = 3
TOTAL_BUDGET    = 100.0   # £m


# ═══════════════════════════════════════════════════════════════════════════════
# PLAYER
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class PlayerProfile:
    """
    One player as understood by the Sporting Director.

    Built from a RankedPlayer record produced by the Stats Agent.
    The fixture fields (fixture_scores, fixture_weighted_score) are
    populated later by FixtureAnalyser.enrich_players().
    """
    # Identity
    name:       str
    position:   str          # "GK" | "DEF" | "MID" | "FWD"
    team:       str
    element:    int          # FPL player ID (used to match bootstrap data)
    cost:       float        # £m — value_m from Stats Agent (value / 10)

    # Stats Agent predictions
    predicted_pts: float     # Raw XGBoost output
    expected_pts:  float     # predicted_pts × start_prob (risk-adjusted)
    start_prob:    float     # 0.0 – 1.0

    # Form signals
    avg_pts_last5: float
    form_trend:    float     # positive = improving
    goals_last5:   int
    assists_last5: int

    # Availability (False = injured/suspended, exclude from buy targets)
    is_available: bool = True

    # Populated by FixtureAnalyser
    fixture_scores:          List[float] = field(default_factory=list)
    fixture_weighted_score:  float = 0.0

    @classmethod
    def from_ranked_player(cls, record: dict) -> "PlayerProfile":
        """
        Build a PlayerProfile from a RankedPlayer dict as produced by
        the Stats Agent's rank_players node.

        Expected keys: name, team, position, element, value_m,
                       predicted_pts, expected_pts, start_prob,
                       avg_pts_last5, form_trend, goals_last5, assists_last5
        """
        return cls(
            name          = record["name"],
            position      = record["position"],
            team          = record["team"],
            element       = int(record.get("element", 0)),
            cost          = float(record.get("value_m", record.get("value", 0) / 10)),
            predicted_pts = float(record.get("predicted_pts", 0.0)),
            expected_pts  = float(record.get("expected_pts", 0.0)),
            start_prob    = float(record.get("start_prob", 0.7)),
            avg_pts_last5 = float(record.get("avg_pts_last5", 0.0)),
            form_trend    = float(record.get("form_trend", 0.0)),
            goals_last5   = int(record.get("goals_last5", 0)),
            assists_last5 = int(record.get("assists_last5", 0)),
            is_available  = record.get("is_available", True),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SQUAD
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Squad:
    """
    A manager's current 15-player FPL squad.

    bank: money in the bank (not tied up in players).
    total_value is computed from the player list — do not set it manually.
    budget = total_value + bank = the maximum you could spend if you sold everyone.
    """
    players:        List[PlayerProfile]
    bank:           float   # £m remaining
    free_transfers: int = 1
    gameweek:       int = 30

    @property
    def total_value(self) -> float:
        return round(sum(p.cost for p in self.players), 1)

    @property
    def budget(self) -> float:
        return round(self.total_value + self.bank, 1)

    def players_by_position(self, position: str) -> List[PlayerProfile]:
        return [p for p in self.players if p.position == position]

    def players_by_team(self, team: str) -> List[PlayerProfile]:
        return [p for p in self.players if p.team == team]

    def get_player(self, name: str) -> Optional[PlayerProfile]:
        for p in self.players:
            if p.name == name:
                return p
        return None

    def club_counts(self) -> dict:
        counts: dict = {}
        for p in self.players:
            counts[p.team] = counts.get(p.team, 0) + 1
        return counts


# ═══════════════════════════════════════════════════════════════════════════════
# FIXTURE
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class FixtureRating:
    """
    One team's fixture for one gameweek.
    FDR is the FPL Fixture Difficulty Rating (1 = easiest, 5 = hardest).
    adjusted_fdr applies a home-advantage reduction.
    """
    team:         str
    gameweek:     int
    opponent:     str
    is_home:      bool
    fdr:          int          # 1–5 (raw from FPL API)
    adjusted_fdr: float        # fdr - HOME_ADVANTAGE if is_home


# ═══════════════════════════════════════════════════════════════════════════════
# TRANSFER
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class TransferOption:
    """
    A single evaluated sell→buy transfer pair.

    All gain fields are (buy - sell), so positive = buy is better.
    score is the composite ranking metric — higher is better.
    net_expected_gain is what a human manager cares about most:
    how many expected points do we gain after paying any hit.
    """
    sell: PlayerProfile
    buy:  PlayerProfile

    # Budget
    cost_delta:      float   # buy.cost - sell.cost (positive = spend money)
    remaining_bank:  float   # bank after transfer executes

    # Gain metrics (buy minus sell)
    point_gain_gw:   float   # predicted_pts gain (raw model output)
    expected_gain:   float   # expected_pts gain (risk-adjusted)
    fixture_gain:    float   # fixture_weighted_score gain
    form_gain:       float   # avg_pts_last5 gain

    # Transfer cost
    transfer_cost_points: int    # 0 if free transfer, 4 per hit
    net_expected_gain:    float  # expected_gain - transfer_cost_points

    # Composite ranking score
    score: float

    # Human-readable summary (Claude expands this in Weeks 3-4)
    reasoning: str


# ═══════════════════════════════════════════════════════════════════════════════
# RECOMMENDATION
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class TransferRecommendation:
    """
    Final output of the Sporting Director Agent for one gameweek.
    This is the payload consumed by the Manager Agent and the frontend API.

    recommended_transfers: ordered best-first.
    wildcard_flag: True if the agent detects the squad is broadly weak enough
                   to justify activating the wildcard chip.
    hold_flag: True if the best available transfer gains < 2 expected pts —
               better to hold the free transfer and bank it.
    summary: one-paragraph explanation stub — Claude fills this in Weeks 3-4.
    """
    gameweek:              int
    free_transfers_available: int
    bank:                  float
    recommended_transfers: List[TransferOption]   # best-first
    wildcard_flag:         bool
    hold_flag:             bool
    summary:               str
    log:                   List[str] = field(default_factory=list)
