"""
Feature Engineering Module for FPL Optimizer
============================================
This module creates advanced features for FPL prediction models.
"""

import pandas as pd
import numpy as np
from typing import List, Optional


class FPLFeatureEngineer:
    """
    A class to create engineered features for FPL data.
    
    Features include:
    - Rolling averages (points, minutes, etc.)
    - Form indicators
    - Fixture difficulty
    - Home/away performance splits
    - Per-minute statistics
    """
    
    def __init__(self):
        """Initialize the feature engineer."""
        pass
    
    def create_all_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create all engineered features.
        
        Args:
            df (pd.DataFrame): Cleaned FPL data
            
        Returns:
            pd.DataFrame: Data with engineered features added
        """
        print("Creating engineered features...")
        print("="*60)
        
        df = df.copy()
        
        # Ensure data is sorted by player and gameweek
        df = df.sort_values(['name', 'season', 'GW']).reset_index(drop=True)
        
        # Create rolling average features
        df = self.create_rolling_features(df)
        
        # Create form indicators
        df = self.create_form_features(df)
        
        # Create per-minute statistics
        df = self.create_per_minute_features(df)
        
        # Create home/away performance features
        df = self.create_home_away_features(df)
        
        # Create fixture-based features
        df = self.create_fixture_features(df)
        
        # Create cumulative season statistics
        df = self.create_cumulative_features(df)
        
        print("="*60)
        print("✓ Feature engineering complete!")
        print(f"Total features: {len(df.columns)}")
        print("="*60 + "\n")
        
        return df
    
    def create_rolling_features(self, df: pd.DataFrame, 
                                windows: List[int] = [3, 5, 10]) -> pd.DataFrame:
        """
        Create rolling average features for various windows.
        
        Args:
            df (pd.DataFrame): Input data
            windows (List[int]): List of window sizes for rolling averages
            
        Returns:
            pd.DataFrame: Data with rolling features added
        """
        print("\nCreating rolling average features...")
        
        # Columns to create rolling averages for
        rolling_cols = [
            'total_points', 'minutes', 'goals_scored', 'assists',
            'clean_sheets', 'bonus', 'bps', 'ict_index',
            'influence', 'creativity', 'threat',
            'expected_goals', 'expected_assists'
        ]
        
        # Filter columns that exist in the dataframe
        rolling_cols = [col for col in rolling_cols if col in df.columns]
        
        for window in windows:
            for col in rolling_cols:
                # Create rolling mean
                df[f'{col}_last_{window}_avg'] = (
                    df.groupby('name')[col]
                    .transform(lambda x: x.rolling(window=window, min_periods=1).mean().shift(1))
                )
                
                # Create rolling sum for some columns
                if col in ['total_points', 'minutes', 'goals_scored', 'assists']:
                    df[f'{col}_last_{window}_sum'] = (
                        df.groupby('name')[col]
                        .transform(lambda x: x.rolling(window=window, min_periods=1).sum().shift(1))
                    )
        
        # Special feature: last_3_avg_points (as requested)
        if 'total_points' in df.columns:
            df['last_3_avg_points'] = (
                df.groupby('name')['total_points']
                .transform(lambda x: x.rolling(window=3, min_periods=1).mean().shift(1))
            )
        
        print(f"  ✓ Created rolling features for {len(rolling_cols)} columns, {len(windows)} windows")
        return df
    
    def create_form_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create form-based features.
        
        Form is typically measured as recent performance relative to season average.
        """
        print("Creating form features...")
        
        if 'total_points' not in df.columns:
            return df
        
        # Points per game (season average)
        df['season_avg_points'] = (
            df.groupby(['name', 'season'])['total_points']
            .transform(lambda x: x.expanding().mean().shift(1))
        )
        
        # Form: recent performance vs season average
        if 'total_points_last_5_avg' in df.columns:
            df['form_vs_average'] = df['total_points_last_5_avg'] - df['season_avg_points']
        
        # Games played this season
        df['games_played'] = (
            df.groupby(['name', 'season'])
            .cumcount()
        )
        
        # Minutes per game
        if 'minutes' in df.columns:
            df['avg_minutes'] = (
                df.groupby(['name', 'season'])['minutes']
                .transform(lambda x: x.expanding().mean().shift(1))
            )
        
        # Consistency score (standard deviation of recent points)
        df['points_std_last_5'] = (
            df.groupby('name')['total_points']
            .transform(lambda x: x.rolling(window=5, min_periods=1).std().shift(1))
        )
        
        print("  ✓ Created form features")
        return df
    
    def create_per_minute_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create per-90-minute statistics to normalize for playing time.
        """
        print("Creating per-minute features...")
        
        if 'minutes' not in df.columns:
            return df
        
        # Columns to normalize per 90 minutes
        per_90_cols = [
            'total_points', 'goals_scored', 'assists', 'bonus',
            'expected_goals', 'expected_assists', 'ict_index'
        ]
        
        per_90_cols = [col for col in per_90_cols if col in df.columns]
        
        for col in per_90_cols:
            # Avoid division by zero
            df[f'{col}_per_90'] = np.where(
                df['minutes'] > 0,
                (df[col] / df['minutes']) * 90,
                0
            )
        
        print(f"  ✓ Created per-90 features for {len(per_90_cols)} columns")
        return df
    
    def create_home_away_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create features based on home/away performance.
        """
        print("Creating home/away features...")
        
        if 'was_home' not in df.columns or 'total_points' not in df.columns:
            return df
        
        # Average points at home vs away
        df['home_avg_points'] = (
            df[df['was_home'] == True]
            .groupby(['name', 'season'])['total_points']
            .transform(lambda x: x.expanding().mean().shift(1))
        )
        
        df['away_avg_points'] = (
            df[df['was_home'] == False]
            .groupby(['name', 'season'])['total_points']
            .transform(lambda x: x.expanding().mean().shift(1))
        )
        
        # Fill NaN values (for players who haven't played home/away yet)
        df['home_avg_points'] = df['home_avg_points'].fillna(df['season_avg_points'])
        df['away_avg_points'] = df['away_avg_points'].fillna(df['season_avg_points'])
        
        # Home/away advantage
        df['home_away_diff'] = df['home_avg_points'] - df['away_avg_points']
        
        print("  ✓ Created home/away features")
        return df
    
    def create_fixture_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create features based on opponent and fixture difficulty.
        """
        print("Creating fixture features...")
        
        if 'opponent_team' not in df.columns or 'total_points' not in df.columns:
            return df
        
        # Average points conceded by opponent (opponent strength)
        df['opponent_avg_points_conceded'] = (
            df.groupby(['opponent_team', 'season'])['total_points']
            .transform(lambda x: x.expanding().mean().shift(1))
        )
        
        # Clean sheets kept by opponent team
        if 'clean_sheets' in df.columns:
            df['opponent_clean_sheet_rate'] = (
                df.groupby(['opponent_team', 'season'])['clean_sheets']
                .transform(lambda x: x.expanding().mean().shift(1))
            )
        
        print("  ✓ Created fixture features")
        return df
    
    def create_cumulative_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create cumulative season statistics.
        """
        print("Creating cumulative features...")
        
        cumulative_cols = [
            'total_points', 'goals_scored', 'assists', 'clean_sheets',
            'yellow_cards', 'red_cards', 'bonus'
        ]
        
        cumulative_cols = [col for col in cumulative_cols if col in df.columns]
        
        for col in cumulative_cols:
            df[f'cumulative_{col}'] = (
                df.groupby(['name', 'season'])[col]
                .transform(lambda x: x.shift(1).expanding().sum())
            )
        
        print(f"  ✓ Created cumulative features for {len(cumulative_cols)} columns")
        return df
    
    def create_target_variable(self, df: pd.DataFrame, 
                              target_col: str = 'total_points',
                              forward_periods: int = 1) -> pd.DataFrame:
        """
        Create target variable for prediction (future points).
        
        Args:
            df (pd.DataFrame): Input data
            target_col (str): Column to use as target
            forward_periods (int): Number of periods to look ahead
            
        Returns:
            pd.DataFrame: Data with target variable added
        """
        df = df.copy()
        
        # Create target (next gameweek's points)
        df[f'target_next_{forward_periods}_gw'] = (
            df.groupby('name')[target_col]
            .transform(lambda x: x.shift(-forward_periods))
        )
        
        return df
    
    def get_feature_importance_cols(self) -> List[str]:
        """
        Get list of engineered features for model training.
        
        Returns:
            List[str]: List of feature column names
        """
        # Return common engineered features
        features = [
            'last_3_avg_points', 'last_5_avg_points', 'last_10_avg_points',
            'season_avg_points', 'form_vs_average', 'games_played',
            'avg_minutes', 'points_std_last_5',
            'total_points_per_90', 'goals_scored_per_90', 'assists_per_90',
            'home_avg_points', 'away_avg_points', 'home_away_diff',
            'opponent_avg_points_conceded', 'ict_index', 'influence',
            'creativity', 'threat', 'expected_goals', 'expected_assists',
            'position_encoded', 'value', 'was_home'
        ]
        return features


def main():
    """
    Example usage of the FPL Feature Engineer.
    """
    # Load and clean data
    try:
        from .data_ingestion import FPLDataLoader
        from .data_cleaning import FPLDataCleaner
    except ImportError:
        from data_ingestion import FPLDataLoader
        from data_cleaning import FPLDataCleaner
    
    # Load data
    loader = FPLDataLoader(base_path='./data')
    df_raw = loader.load_current_and_previous_season()
    
    # Clean data
    cleaner = FPLDataCleaner()
    df_clean = cleaner.clean_data(df_raw, fill_strategy='smart')
    
    # Engineer features
    engineer = FPLFeatureEngineer()
    df_engineered = engineer.create_all_features(df_clean)
    
    # Create target variable for modeling
    df_engineered = engineer.create_target_variable(df_engineered)
    
    # Display results
    print("\nEngineered Features Sample:")
    print(df_engineered[['name', 'GW', 'total_points', 'last_3_avg_points', 
                         'last_5_avg_points', 'season_avg_points']].head(20))
    
    print("\nNew columns created:")
    original_cols = set(df_clean.columns)
    new_cols = set(df_engineered.columns) - original_cols
    print(f"Total new features: {len(new_cols)}")
    for col in sorted(new_cols):
        print(f"  - {col}")
    
    return df_engineered


if __name__ == "__main__":
    df = main()
