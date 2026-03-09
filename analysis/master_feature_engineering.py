"""
Master FPL Feature Engineering Pipeline
========================================
Comprehensive feature engineering for Fantasy Premier League point prediction.

Key improvements over baseline:
- Decay-weighted form (exponential moving averages)
- Minutes-based rotation risk proxy
- Underlying stats (xG, xA) to reduce noise
- Synergy features (teammate interactions)
- Enhanced fixture difficulty (team strength, availability weights)
"""

import pandas as pd
import numpy as np
from typing import Optional


class MasterFPLFeatureEngineer:
    """
    Advanced feature engineering for FPL point prediction.
    
    All features use .shift(1) to prevent data leakage.
    """
    
    def __init__(self, df: pd.DataFrame):
        """
        Initialize with a cleaned FPL DataFrame.
        
        Parameters
        ----------
        df : pd.DataFrame
            Must contain: name, GW, season, position, team, total_points, minutes,
                         expected_goals, expected_assists, was_home, opponent_team
        """
        self.df = df.copy()
        self.df = self.df.sort_values(['name', 'season', 'GW']).reset_index(drop=True)
    
    # ========================================================================
    # 1. DECAY-WEIGHTED FORM & HISTORICAL MINUTES
    # ========================================================================
    
    def add_decay_weighted_form(self, alpha: float = 0.3) -> pd.DataFrame:
        """
        Exponentially weighted moving average for recent form.
        
        Recent gameweeks weighted more heavily than distant ones.
        Alpha controls decay rate: higher = more weight to recent GWs.
        
        Parameters
        ----------
        alpha : float
            Smoothing factor (0 < alpha <= 1). Default 0.3 gives ~10 GW memory.
        """
        self.df['ewm_points'] = (
            self.df.groupby(['name', 'season'])['total_points']
            .transform(lambda x: x.shift(1).ewm(alpha=alpha, adjust=False).mean())
        )
        return self.df
    
    def add_minutes_rotation_risk(self, windows: list = [3, 5]) -> pd.DataFrame:
        """
        Rolling average of minutes played — proxy for rotation risk.
        
        Players with declining minutes have higher rotation risk.
        """
        for w in windows:
            col_name = f'avg_minutes_last_{w}'
            self.df[col_name] = (
                self.df.groupby(['name', 'season'])['minutes']
                .transform(lambda x: x.shift(1).rolling(window=w, min_periods=1).mean())
            )
        
        # Minutes trend: recent vs longer-term average
        if 'avg_minutes_last_3' in self.df.columns and 'avg_minutes_last_5' in self.df.columns:
            self.df['minutes_trend'] = (
                self.df['avg_minutes_last_3'] - self.df['avg_minutes_last_5']
            )
        
        return self.df
    
    # ========================================================================
    # 2. UNDERLYING STATS (xG, xA)
    # ========================================================================
    
    def add_underlying_stats(self, windows: list = [3, 5]) -> pd.DataFrame:
        """
        Rolling averages for Expected Goals (xG) and Expected Assists (xA).
        
        These metrics reduce noise from lucky/unlucky finishing.
        """
        for stat in ['expected_goals', 'expected_assists']:
            if stat not in self.df.columns:
                continue
                
            for w in windows:
                col_name = f'{stat}_last_{w}'
                self.df[col_name] = (
                    self.df.groupby(['name', 'season'])[stat]
                    .transform(lambda x: x.shift(1).rolling(window=w, min_periods=1).mean())
                )
        
        # xG + xA combined metric (total attacking threat)
        if 'expected_goals_last_3' in self.df.columns and 'expected_assists_last_3' in self.df.columns:
            self.df['xGI_last_3'] = (
                self.df['expected_goals_last_3'] + self.df['expected_assists_last_3']
            )
        
        return self.df
    
    # ========================================================================
    # 3. SYNERGY & RELATIONAL FEATURES
    # ========================================================================
    
    def add_teammate_synergy(self) -> pd.DataFrame:
        """
        Capture teammate dependencies (e.g., KDB-Haaland effect).
        
        For each team-GW, identify the top performer from the previous GW.
        Flag whether a player's "star teammate" is available.
        """
        # Team total points LAST GW — compute team-level sum first, then lag by GW
        # (avoids the leakage from shifting within a same-GW group)
        team_gw_pts = (
            self.df.groupby(['team', 'season', 'GW'])['total_points']
            .sum()
            .reset_index(name='_team_gw_total')
        )
        team_gw_pts['team_total_points_last_gw'] = (
            team_gw_pts.groupby(['team', 'season'])['_team_gw_total']
            .shift(1)
        )
        self.df = self.df.merge(
            team_gw_pts[['team', 'season', 'GW', 'team_total_points_last_gw']],
            on=['team', 'season', 'GW'], how='left'
        )
        
        return self.df
    
    # ========================================================================
    # 4. FIXTURE DIFFICULTY & AVAILABILITY
    # ========================================================================
    
    def add_fixture_difficulty_elo(self) -> pd.DataFrame:
        """
        Team strength proxy using cumulative points as ELO-like rating.
        
        Better teams concede fewer points; weaker teams concede more.
        """
        # Team strength = cumulative total points scored by team (using team names)
        team_strength = (
            self.df.groupby(['team', 'season', 'GW'])['total_points']
            .sum()
            .groupby(level=[0, 1])
            .cumsum()
            .reset_index(name='team_strength')
        )
        
        # Create a mapping from opponent_team ID to team name based on existing data
        # Assuming each team ID maps to a unique team name
        if 'opponent_team' in self.df.columns:
            team_id_to_name = self.df[['opponent_team', 'team']].drop_duplicates()
            team_id_to_name = team_id_to_name.groupby('opponent_team')['team'].first().to_dict()
            
            # Add opponent_team_name column if it doesn't exist
            if 'opponent_team_name' not in self.df.columns:
                self.df['opponent_team_name'] = self.df['opponent_team'].map(team_id_to_name)
            
            # Merge opponent strength using team names
            self.df = self.df.merge(
                team_strength.rename(columns={'team': 'opponent_team_name', 'team_strength': 'opponent_strength'}),
                on=['opponent_team_name', 'season', 'GW'],
                how='left'
            )
        else:
            # Fallback: use team column directly if opponent_team doesn't exist
            self.df = self.df.merge(
                team_strength.rename(columns={'team_strength': 'opponent_strength'}),
                left_on=['team', 'season', 'GW'],
                right_on=['team', 'season', 'GW'],
                how='left'
            )
        
        # Shift to prevent leakage
        self.df['opponent_strength'] = (
            self.df.groupby(['name', 'season'])['opponent_strength']
            .shift(1)
        )
        
        return self.df
    
    def add_availability_weights(self) -> pd.DataFrame:
        """
        Convert injury/availability flags into numerical weights.
        
        Assumes `chance_of_playing_next_round` exists (0-100 scale).
        """
        if 'chance_of_playing_next_round' in self.df.columns:
            self.df['availability_weight'] = (
                self.df['chance_of_playing_next_round'].fillna(100) / 100.0
            )
            
            # Lag it
            self.df['availability_weight'] = (
                self.df.groupby(['name', 'season'])['availability_weight']
                .shift(1)
            )
        else:
            # Fallback: assume everyone is 100% available
            self.df['availability_weight'] = 1.0
        
        return self.df
    
    # ========================================================================
    # 5. ICT ROLLING FEATURES
    # ========================================================================

    def add_ict_rolling_features(self, windows: list = [3, 5]) -> pd.DataFrame:
        """
        Create clean rolling aliases for ICT index components.

        The processed CSV already has `ict_index_last_3_avg` etc. created by
        FPLFeatureEngineer, but the master feature list expects short names like
        `ict_index_last_3`.  This method creates those aliases and also adds
        rolling influence/creativity/threat computed within this pipeline so the
        names are consistent regardless of which pipeline stage ran first.
        """
        for col in ['ict_index', 'creativity', 'threat', 'influence', 'bps']:
            if col not in self.df.columns:
                continue
            for w in windows:
                alias = f'{col}_last_{w}'
                src   = f'{col}_last_{w}_avg'      # name from FPLFeatureEngineer
                if alias not in self.df.columns:
                    if src in self.df.columns:
                        self.df[alias] = self.df[src]
                    else:
                        # Compute from scratch (lag-safe)
                        self.df[alias] = (
                            self.df.groupby(['name', 'season'])[col]
                            .transform(
                                lambda x: x.shift(1).rolling(window=w, min_periods=1).mean()
                            )
                        )
        return self.df

    # ========================================================================
    # 6. ATTACKING FEATURES (FWD / MID focused)
    # ========================================================================

    def add_attacking_features(self, windows: list = [3, 5]) -> pd.DataFrame:
        """
        Team-level attacking strength and blank-GW proxy features.

        - team_goals_last_3   : rolling goals scored by player's team (proxy for
                                 attacking environment, e.g. Man City vs Sheffield Utd)
        - team_xG_last_3      : rolling xG by team (cleaner than goals)
        - blank_gw_last       : 1 if player played 0 minutes last GW (rotation / blank)
        - blank_rate_last_5   : fraction of last 5 GWs with 0 minutes
        """
        # Team attacking strength — sum goals/xG per team-GW, then rolling
        if 'goals_scored' in self.df.columns:
            team_gw_goals = (
                self.df.groupby(['team', 'season', 'GW'])['goals_scored']
                .sum()
                .reset_index(name='team_gw_goals')
            )
            team_gw_goals['team_goals_last_3'] = (
                team_gw_goals.groupby(['team', 'season'])['team_gw_goals']
                .transform(lambda x: x.shift(1).rolling(3, min_periods=1).mean())
            )
            self.df = self.df.merge(
                team_gw_goals[['team', 'season', 'GW', 'team_goals_last_3']],
                on=['team', 'season', 'GW'], how='left'
            )

        if 'expected_goals' in self.df.columns:
            team_gw_xg = (
                self.df.groupby(['team', 'season', 'GW'])['expected_goals']
                .sum()
                .reset_index(name='team_gw_xG')
            )
            team_gw_xg['team_xG_last_3'] = (
                team_gw_xg.groupby(['team', 'season'])['team_gw_xG']
                .transform(lambda x: x.shift(1).rolling(3, min_periods=1).mean())
            )
            self.df = self.df.merge(
                team_gw_xg[['team', 'season', 'GW', 'team_xG_last_3']],
                on=['team', 'season', 'GW'], how='left'
            )

        # Blank GW proxy — lag-safe (uses last GW's minutes)
        if 'minutes' in self.df.columns:
            mins_last = (
                self.df.groupby(['name', 'season'])['minutes']
                .transform(lambda x: x.shift(1))
            )
            self.df['blank_gw_last']    = (mins_last == 0).astype(int)
            self.df['blank_rate_last_5'] = (
                self.df.groupby(['name', 'season'])['minutes']
                .transform(
                    lambda x: (x.shift(1) == 0).rolling(5, min_periods=1).mean()
                )
            )

        return self.df

    # ========================================================================
    # 7. DEFENSIVE FEATURES (DEF / GK focused)
    # ========================================================================

    def add_defensive_features(self, windows: list = [3, 5]) -> pd.DataFrame:
        """
        Team-level clean sheet rate and opponent attacking threat for defenders.

        - team_cs_rate_last_5       : rolling clean sheet rate for player's team
        - opponent_xGC_last_3       : opponent's expected goals conceded (proxy
                                       for how many chances they give up — lower =
                                       harder to score against)
        - opponent_goals_conceded_last_3 : raw goals conceded by opponent, rolling
        """
        # Team clean sheet rate
        if 'clean_sheets' in self.df.columns:
            for w in windows:
                col = f'team_cs_rate_last_{w}'
                team_cs = (
                    self.df.groupby(['team', 'season', 'GW'])['clean_sheets']
                    .max()                               # 1 if any player had cs
                    .reset_index(name='team_had_cs')
                )
                team_cs[col] = (
                    team_cs.groupby(['team', 'season'])['team_had_cs']
                    .transform(lambda x: x.shift(1).rolling(w, min_periods=1).mean())
                )
                self.df = self.df.merge(
                    team_cs[['team', 'season', 'GW', col]],
                    on=['team', 'season', 'GW'], how='left'
                )

        # Opponent xG conceded (how leaky the opponent's defence is)
        if 'expected_goals_conceded' in self.df.columns and 'opponent_team' in self.df.columns:
            # Compute team-level xGC per GW (average across all players in that team)
            team_xgc = (
                self.df.groupby(['team', 'season', 'GW'])['expected_goals_conceded']
                .mean()
                .reset_index(name='team_xGC')
            )
            for w in windows:
                col = f'team_xGC_last_{w}'
                team_xgc[col] = (
                    team_xgc.groupby(['team', 'season'])['team_xGC']
                    .transform(lambda x: x.shift(1).rolling(w, min_periods=1).mean())
                )

            # Opponent = the team the player is facing, map via opponent_team_name
            if 'opponent_team_name' in self.df.columns:
                opp_xgc = team_xgc[['team', 'season', 'GW', 'team_xGC_last_3', 'team_xGC_last_5']].rename(
                    columns={
                        'team': 'opponent_team_name',
                        'team_xGC_last_3': 'opponent_xGC_last_3',
                        'team_xGC_last_5': 'opponent_xGC_last_5',
                    }
                )
                self.df = self.df.merge(
                    opp_xgc, on=['opponent_team_name', 'season', 'GW'], how='left'
                )

        # Opponent goals conceded (raw) — already in processed CSV as goals_conceded_last_3_avg
        if 'goals_conceded' in self.df.columns:
            for w in windows:
                alias = f'goals_conceded_last_{w}'
                src   = f'goals_conceded_last_{w}_avg'
                if alias not in self.df.columns:
                    if src in self.df.columns:
                        self.df[alias] = self.df[src]
                    else:
                        self.df[alias] = (
                            self.df.groupby(['name', 'season'])['goals_conceded']
                            .transform(
                                lambda x: x.shift(1).rolling(w, min_periods=1).mean()
                            )
                        )

        return self.df

    # ========================================================================
    # 8. PROPERLY LAGGED PER-90 RATES
    # ========================================================================

    def add_per90_rolling_features(self, windows: list = [3, 5]) -> pd.DataFrame:
        """
        Rolling per-90-minute rates computed from PREVIOUS GWs only.

        The base FPLFeatureEngineer creates per-90 stats using the CURRENT GW
        (leakage). This method replaces them with lag-safe rolling averages:

            goals_per_90_last_3  = mean of (goals_scored/minutes*90) over GW N-3 to N-1
            assists_per_90_last_3 = same for assists

        To predict GW 35 we use rates from GW 32-34 — never GW 35 itself.
        """
        if 'minutes' not in self.df.columns:
            return self.df

        mins = self.df['minutes'].replace(0, np.nan)

        for raw_col, out_prefix in [('goals_scored', 'goals_per_90'),
                                     ('assists',       'assists_per_90'),
                                     ('bonus',         'bonus_per_90')]:
            if raw_col not in self.df.columns:
                continue

            # per-90 value for each individual GW (NOT to be used as feature directly)
            # Fill 0 when minutes=0: player who didn't play had a 0 scoring rate.
            per90 = ((self.df[raw_col] / mins) * 90).fillna(0)

            for w in windows:
                col = f'{out_prefix}_last_{w}'
                if col not in self.df.columns:
                    # Attach temporarily, compute rolling on previous GWs, then drop temp
                    self.df['_per90_tmp'] = per90
                    self.df[col] = (
                        self.df.groupby(['name', 'season'])['_per90_tmp']
                        .transform(
                            lambda x: x.shift(1).rolling(window=w, min_periods=1).mean()
                        )
                    )
                    self.df.drop(columns=['_per90_tmp'], inplace=True)

        return self.df

    # ========================================================================
    # 9. xP (FPL EXPECTED POINTS) ROLLING FEATURES
    # ========================================================================

    def add_xp_features(self, windows: list = [3, 5]) -> pd.DataFrame:
        """
        Rolling and EWM features from FPL's own expected points (xP).

        xP already encodes fixture difficulty + player form as seen by FPL's
        algorithm, making it one of the strongest signals for MID/FWD prediction.
        """
        if 'xP' not in self.df.columns:
            return self.df

        for w in windows:
            col = f'xP_last_{w}'
            if col not in self.df.columns:
                self.df[col] = (
                    self.df.groupby(['name', 'season'])['xP']
                    .transform(lambda x: x.shift(1).rolling(window=w, min_periods=1).mean())
                )

        # EWM of xP — recent fixture run weighted more heavily
        if 'xP_ewm' not in self.df.columns:
            self.df['xP_ewm'] = (
                self.df.groupby(['name', 'season'])['xP']
                .transform(lambda x: x.shift(1).ewm(alpha=0.3, adjust=False).mean())
            )

        return self.df

    # ========================================================================
    # 9. HOME ATTACK BOOST (MID / FWD focused)
    # ========================================================================

    def add_home_attack_features(self) -> pd.DataFrame:
        """
        Interaction between home advantage and recent attacking output.

        Attackers (MID/FWD) score significantly more in home fixtures.
        home_attack_boost = was_home * xGI_last_3 (or xG+xA fallback).
        """
        if 'was_home' not in self.df.columns:
            return self.df

        home = self.df['was_home'].astype(float)

        if 'xGI_last_3' in self.df.columns:
            self.df['home_attack_boost'] = home * self.df['xGI_last_3'].fillna(0)
        elif 'expected_goals_last_3' in self.df.columns and 'expected_assists_last_3' in self.df.columns:
            xgi = self.df['expected_goals_last_3'].fillna(0) + self.df['expected_assists_last_3'].fillna(0)
            self.df['home_attack_boost'] = home * xgi
        elif 'xP_last_3' in self.df.columns:
            self.df['home_attack_boost'] = home * self.df['xP_last_3'].fillna(0)

        return self.df

    # ========================================================================
    # 10. TRANSFER & PRICE MOMENTUM
    # ========================================================================

    def add_transfer_features(self) -> pd.DataFrame:
        """
        Transfer pressure and price momentum as community wisdom signals.

        - transfer_momentum : fraction of transfers that are buys (0..1).
          Surging towards 1.0 means the community is piling in — strong form signal.
        - price_momentum    : current value vs rolling 5-GW mean.
          Positive = price rising; negative = price falling.
        """
        if 'transfers_in' in self.df.columns and 'transfers_out' in self.df.columns:
            denom = (self.df['transfers_in'] + self.df['transfers_out'] + 1)
            self.df['_raw_tm'] = self.df['transfers_in'] / denom
            self.df['transfer_momentum'] = (
                self.df.groupby(['name', 'season'])['_raw_tm']
                .transform(lambda x: x.shift(1))
            )
            self.df.drop(columns=['_raw_tm'], inplace=True)

        if 'value' in self.df.columns:
            rolling_val = (
                self.df.groupby(['name', 'season'])['value']
                .transform(lambda x: x.shift(1).rolling(window=5, min_periods=1).mean())
            )
            self.df['price_momentum'] = (
                self.df.groupby(['name', 'season'])['value']
                .transform(lambda x: x.shift(1)) - rolling_val
            )

        return self.df

    # ========================================================================
    # 11. EXPECTED GOAL INVOLVEMENTS ROLLING
    # ========================================================================

    def add_egi_rolling_features(self, windows: list = [3, 5]) -> pd.DataFrame:
        """
        Rolling averages for expected_goal_involvements (xG + xA combined per FPL).

        FPL provides this directly; it's a cleaner single metric than separate xG/xA.
        """
        col = 'expected_goal_involvements'
        if col not in self.df.columns:
            return self.df

        for w in windows:
            alias = f'{col}_last_{w}'
            src   = f'{col}_last_{w}_avg'
            if alias not in self.df.columns:
                if src in self.df.columns:
                    self.df[alias] = self.df[src]
                else:
                    self.df[alias] = (
                        self.df.groupby(['name', 'season'])[col]
                        .transform(lambda x: x.shift(1).rolling(window=w, min_periods=1).mean())
                    )

        return self.df

    # ========================================================================
    # MASTER PIPELINE
    # ========================================================================

    def create_all_master_features(self) -> pd.DataFrame:
        """
        Run all master feature engineering steps in sequence.

        Returns
        -------
        pd.DataFrame
            DataFrame with all master features added.
        """
        import random
        random.seed(42)
        np.random.seed(42)

        print("Running Master Feature Engineering Pipeline...")

        # 1. Decay-weighted form
        print("  -> Decay-weighted form (EWM)")
        self.add_decay_weighted_form(alpha=0.3)

        # 2. Minutes rotation risk
        print("  -> Minutes rotation risk")
        self.add_minutes_rotation_risk(windows=[3, 5])

        # 3. Underlying stats (xG, xA)
        print("  -> Underlying stats (xG, xA)")
        self.add_underlying_stats(windows=[3, 5])

        # 4. Teammate synergy
        print("  -> Teammate synergy features")
        self.add_teammate_synergy()

        # 5. Fixture difficulty ELO
        print("  -> Fixture difficulty (ELO-like)")
        self.add_fixture_difficulty_elo()

        # 6. Availability weights
        print("  -> Availability weights")
        self.add_availability_weights()

        # 7. ICT rolling aliases
        print("  -> ICT / creativity / threat rolling features")
        self.add_ict_rolling_features(windows=[3, 5])

        # 8. Attacking features (team strength, blank GW proxy)
        print("  -> Attacking features (team strength, blank GW)")
        self.add_attacking_features(windows=[3, 5])

        # 9. Defensive features (clean sheet rate, opponent xGC)
        print("  -> Defensive features (CS rate, opponent xGC)")
        self.add_defensive_features(windows=[3, 5])

        # 10. xP rolling features
        print("  -> xP rolling features (FPL expected points)")
        self.add_xp_features(windows=[3, 5])

        # 11. Home attack boost (MID/FWD interaction)
        print("  -> Home attack boost interaction")
        self.add_home_attack_features()

        # 12. Transfer & price momentum
        print("  -> Transfer & price momentum")
        self.add_transfer_features()

        # 13. Expected goal involvements rolling
        print("  -> Expected goal involvements rolling")
        self.add_egi_rolling_features(windows=[3, 5])

        # 14. Properly lagged per-90 rates (fixes base FE leakage)
        print("  -> Per-90 rolling rates (lagged goals/assists/bonus)")
        self.add_per90_rolling_features(windows=[3, 5])

        print("Master feature engineering complete.")
        print(f"   Total columns: {len(self.df.columns)}")

        return self.df
