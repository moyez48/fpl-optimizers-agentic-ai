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

import math
from dataclasses import dataclass, field
from typing import Any, List, Optional


def safe_int(value: Any, default: Any = 0) -> Any:
    """Coerce to int; NaN / missing / invalid → default (pandas merges often leave NaN)."""
    if value is None:
        return default
    try:
        x = float(value)
        if not math.isfinite(x):
            return default
        return int(x)
    except (TypeError, ValueError):
        return default


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

    # FPL price tracking (required for sell price lock rule)
    purchase_price: float = 0.0   # Price paid when player was bought, £m
    sell_price:     float = 0.0   # Computed by SquadValidator.compute_sell_price()

    # FPL availability detail (sourced from bootstrap["elements"] by element ID)
    status:             str = "a"   # a / d / i / s / u
    chance_of_playing:  int = 100   # 0–100
    yellow_cards:       int = 0     # Season yellow card total

    # Form stats (sourced from Stats Agent form_stats by element)
    avg_minutes_last5: float = 0.0   # Average minutes in last 5 GWs
    ewm_points:        float = 0.0   # Exponentially weighted recent form
    std_pts_last5:     float = 0.0   # Std deviation of points over last 5 GWs
    blank_rate_last5:  float = 0.0   # Proportion of last 5 GWs where minutes = 0

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
            element       = safe_int(record.get("element"), 0),
            cost          = float(record.get("value_m", record.get("value", 0) / 10)),
            predicted_pts = float(record.get("predicted_pts", 0.0)),
            expected_pts  = float(record.get("expected_pts", 0.0)),
            start_prob    = float(record.get("start_prob", 0.7)),
            avg_pts_last5 = float(record.get("avg_pts_last5", 0.0)),
            form_trend    = float(record.get("form_trend", 0.0)),
            goals_last5   = safe_int(record.get("goals_last5"), 0),
            assists_last5 = safe_int(record.get("assists_last5"), 0),
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

    # Composite ranking score (legacy weighted scorer)
    score: float

    # VORP-based ranking (primary ranking signal per spec §5)
    sell_vorp_score:    float = 0.0
    buy_vorp_score:     float = 0.0
    vorp_gain:          float = 0.0   # buy_vorp - sell_vorp; primary sort key
    budget_unlock_flag: bool  = False  # True if T1 proceeds made this T2 affordable
    transfer_number:    int   = 1      # 1 = single or T1, 2 = T2 in a pair

    # Human-readable summary
    reasoning: str = ""

    # Alternative buy targets for the same sell player, ranked by the
    # 4-way tiebreaker (xP → cost → team_diversity → historical pts).
    # Populated by Node 5; empty for T2 multi-transfer options.
    alternatives: List[TransferOption] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# SQUAD HEALTH
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SquadHealthRecord:
    """
    Per-player health breakdown produced by SquadHealthAnalyser.

    Each dimension surfaces raw signals. Flags are explicit alerts for the
    Manager Agent to act on. No composite score — dimensions are kept separate.
    """
    name: str
    availability: dict   # status, chance_of_playing, is_available, yellow_cards
    rotation_risk: dict  # start_prob, avg_minutes_last5, blank_rate_last5
    form:          dict  # avg_pts_last5, ewm_points
    volatility:    dict  # std_pts_last5
    fixture:       dict  # has_blank_gw, has_double_gw
    flags:         List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# RECOMMENDATION
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class TransferRecommendation:
    """
    Final output of the Sporting Director Agent for one gameweek.
    This is the payload consumed by the Manager Agent and the frontend API.

    squad_health:          Per-player health breakdown (see SquadHealthRecord).
    recommended_transfers: Ordered best-first; single and multi-transfer options.
    wildcard_flag:         True if 5+ squad players have 2+ health flags.
    hold_flag:             True if no transfer passed the expected-gain gate.
    sd_summary:            Structured briefing stub for the Manager Agent.
    sd_log:                Execution log entries from all nodes.
    """
    gameweek:                 int
    free_transfers_available: int
    bank:                     float
    squad_health:             List[SquadHealthRecord]
    recommended_transfers:    List[TransferOption]   # best-first
    wildcard_flag:            bool
    hold_flag:                bool
    sd_summary:               str
    sd_log:                   List[str] = field(default_factory=list)

    # Legacy alias so existing code calling .summary / .log still works
    @property
    def summary(self) -> str:
        return self.sd_summary

    @property
    def log(self) -> List[str]:
        return self.sd_log
