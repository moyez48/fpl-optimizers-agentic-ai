"""
squad_validator.py
==================
Enforces FPL squad construction rules for the Sporting Director Agent.

All methods are pure functions (no state, no I/O) so they are trivially
unit-testable and can be called 9,000+ times per evaluation without overhead.

FPL rules enforced:
  - Squad must contain exactly 15 players: 2 GK, 5 DEF, 5 MID, 3 FWD
  - Maximum 3 players from any single Premier League club
  - Total squad cost must not exceed £100m budget
  - Transfers must swap same-position players
  - Cannot buy a player already in the squad
"""

from __future__ import annotations

from typing import List, Tuple

from .schemas import (
    Squad, PlayerProfile,
    POSITION_LIMITS, SQUAD_SIZE, MAX_PER_CLUB, TOTAL_BUDGET,
)


class SquadValidator:
    """
    Validates squads and individual transfer pairs against FPL rules.

    Usage:
        validator = SquadValidator()
        valid, reasons = validator.validate_transfer(squad, sell_player, buy_player)
        if valid:
            scorer.score_transfer(...)
    """

    def validate_squad(self, squad: Squad) -> Tuple[bool, List[str]]:
        """
        Check an entire squad for FPL compliance.

        Returns:
            (is_valid, list_of_violations)
            list_of_violations is empty when is_valid is True.
        """
        violations = []

        # Size check
        if len(squad.players) != SQUAD_SIZE:
            violations.append(
                f"Squad has {len(squad.players)} players, must be {SQUAD_SIZE}"
            )

        # Position counts
        for pos, limit in POSITION_LIMITS.items():
            count = len(squad.players_by_position(pos))
            if count != limit:
                violations.append(
                    f"{pos}: {count} players, must be exactly {limit}"
                )

        # Club limit
        for team, count in squad.club_counts().items():
            if count > MAX_PER_CLUB:
                violations.append(
                    f"{team}: {count} players, max is {MAX_PER_CLUB}"
                )

        # Budget
        if squad.total_value > TOTAL_BUDGET + squad.bank + 0.01:
            violations.append(
                f"Squad value £{squad.total_value}m exceeds budget £{TOTAL_BUDGET}m"
            )

        return (len(violations) == 0), violations

    def validate_transfer(
        self,
        squad: Squad,
        sell: PlayerProfile,
        buy: PlayerProfile,
    ) -> Tuple[bool, List[str]]:
        """
        Check whether a sell→buy transfer is legal.

        Rules checked (in order of how often they eliminate candidates):
          1. Sell player must actually be in the squad
          2. Buy player must not already be in the squad
          3. Buy and sell must be the same position
          4. Budget: bank + sell.cost >= buy.cost
          5. Club limit: buying doesn't push any club above 3
        """
        violations = []

        # 1. Sell must be in squad
        if not any(p.name == sell.name for p in squad.players):
            violations.append(f"{sell.name} is not in the squad")

        # 2. Buy must not already be in squad
        if any(p.name == buy.name for p in squad.players):
            violations.append(f"{buy.name} is already in the squad")

        # 3. Same position
        if sell.position != buy.position:
            violations.append(
                f"Position mismatch: selling {sell.position} ({sell.name}), "
                f"buying {buy.position} ({buy.name})"
            )

        # 4. Budget
        if not self.can_afford(squad, sell, buy):
            shortfall = round(buy.cost - (squad.bank + sell.cost), 1)
            violations.append(
                f"Cannot afford: buy £{buy.cost}m, bank £{squad.bank}m + "
                f"sell £{sell.cost}m = £{round(squad.bank + sell.cost, 1)}m "
                f"(short by £{shortfall}m)"
            )

        # 5. Club limit (only relevant if buy.team != sell.team)
        if buy.team != sell.team:
            club_counts = squad.club_counts()
            # Simulate: remove sell's club count, add buy's club count
            sell_team_count = club_counts.get(sell.team, 0) - 1
            buy_team_count  = club_counts.get(buy.team, 0) + 1
            if buy_team_count > MAX_PER_CLUB:
                violations.append(
                    f"Club limit: already have {club_counts.get(buy.team, 0)} "
                    f"players from {buy.team} (max {MAX_PER_CLUB})"
                )

        return (len(violations) == 0), violations

    def can_afford(self, squad: Squad, sell: PlayerProfile, buy: PlayerProfile) -> bool:
        """
        True if the transfer is affordable given current bank and sell price.
        Uses a small epsilon (0.01) to handle floating-point rounding.
        """
        available = round(squad.bank + sell.cost, 2)
        return available >= buy.cost - 0.01

    def get_buyable_players(
        self,
        squad: Squad,
        sell: PlayerProfile,
        player_pool: List[PlayerProfile],
    ) -> List[PlayerProfile]:
        """
        Filter the player pool to those legally buyable when selling `sell`.

        Applies all five rules, returning only valid buy targets.
        Does NOT score them — that is the TransferScorer's job.
        """
        valid = []
        for candidate in player_pool:
            ok, _ = self.validate_transfer(squad, sell, candidate)
            if ok:
                valid.append(candidate)
        return valid

    def get_sellable_players(self, squad: Squad) -> List[PlayerProfile]:
        """
        Returns all squad players who can be considered for sale.

        Currently all 15 — selling price lock logic (where you can only
        sell at purchase price if value has risen) is not implemented yet
        as it requires tracking individual purchase prices.
        """
        return list(squad.players)

    def club_counts_after_transfer(
        self,
        squad: Squad,
        sell: PlayerProfile,
        buy: PlayerProfile,
    ) -> dict:
        """
        Returns per-club player count as it would be after the transfer.
        Useful for inspecting the state after a hypothetical move.
        """
        counts = squad.club_counts()
        counts[sell.team] = counts.get(sell.team, 0) - 1
        if counts[sell.team] == 0:
            del counts[sell.team]
        counts[buy.team] = counts.get(buy.team, 0) + 1
        return counts
