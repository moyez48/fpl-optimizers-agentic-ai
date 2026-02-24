"""
Data Cleaning Module for FPL Optimizer
======================================
This module handles data cleaning, preprocessing, and type conversions for FPL data.
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional


class FPLDataCleaner:
    """
    A class to clean and preprocess FPL gameweek data.
    
    This includes:
    - Handling missing values
    - Converting categorical variables to numerical formats
    - Ensuring correct data types
    - Removing duplicates and invalid records
    """
    
    # Define key numeric columns that should not have missing values
    KEY_NUMERIC_COLUMNS = [
        'total_points', 'minutes', 'opponent_team', 'GW', 
        'assists', 'bonus', 'goals_scored', 'clean_sheets'
    ]
    
    # Define categorical columns
    CATEGORICAL_COLUMNS = ['position', 'team', 'name']
    
    # Define columns that should be numeric
    NUMERIC_COLUMNS = [
        'xP', 'assists', 'bonus', 'bps', 'clean_sheets', 'creativity',
        'expected_assists', 'expected_goal_involvements', 'expected_goals',
        'expected_goals_conceded', 'goals_conceded', 'goals_scored',
        'ict_index', 'influence', 'minutes', 'threat', 'total_points',
        'value', 'yellow_cards', 'red_cards', 'saves', 'selected',
        'GW', 'element', 'fixture', 'opponent_team'
    ]
    
    # Define boolean columns
    BOOLEAN_COLUMNS = ['was_home']
    
    def __init__(self):
        """Initialize the data cleaner."""
        self.cleaning_report = {
            'initial_shape': None,
            'final_shape': None,
            'missing_values_before': {},
            'missing_values_after': {},
            'duplicates_removed': 0,
            'invalid_rows_removed': 0
        }
    
    def clean_data(self, df: pd.DataFrame, 
                   fill_strategy: str = 'smart',
                   drop_duplicates: bool = True,
                   create_dummies: bool = False) -> pd.DataFrame:
        """
        Main cleaning pipeline that applies all cleaning operations.
        
        Args:
            df (pd.DataFrame): Raw FPL data
            fill_strategy (str): Strategy for handling missing values 
                               ('smart', 'zero', 'median', 'drop')
            drop_duplicates (bool): Whether to remove duplicate rows
            create_dummies (bool): Whether to create dummy variables for categorical columns
            
        Returns:
            pd.DataFrame: Cleaned data
        """
        print("Starting data cleaning pipeline...")
        print("="*60)
        
        # Store initial state
        self.cleaning_report['initial_shape'] = df.shape
        self.cleaning_report['missing_values_before'] = self._get_missing_summary(df)
        
        # Make a copy to avoid modifying original
        df_clean = df.copy()
        
        # Step 1: Remove duplicates
        if drop_duplicates:
            df_clean = self._remove_duplicates(df_clean)
        
        # Step 2: Fix data types
        df_clean = self._fix_data_types(df_clean)
        
        # Step 3: Handle missing values
        df_clean = self._handle_missing_values(df_clean, strategy=fill_strategy)
        
        # Step 4: Handle categorical variables
        if create_dummies:
            df_clean = self._create_dummy_variables(df_clean)
        else:
            df_clean = self._encode_categorical(df_clean)
        
        # Step 5: Handle boolean columns
        df_clean = self._fix_boolean_columns(df_clean)
        
        # Step 6: Remove invalid rows
        df_clean = self._remove_invalid_rows(df_clean)
        
        # Store final state
        self.cleaning_report['final_shape'] = df_clean.shape
        self.cleaning_report['missing_values_after'] = self._get_missing_summary(df_clean)
        
        # Print report
        self._print_cleaning_report()
        
        return df_clean
    
    def _get_missing_summary(self, df: pd.DataFrame) -> Dict:
        """Get summary of missing values."""
        missing = df.isnull().sum()
        missing = missing[missing > 0]
        return missing.to_dict() if len(missing) > 0 else {}
    
    def _remove_duplicates(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove duplicate rows."""
        initial_count = len(df)
        
        # Remove exact duplicates
        df = df.drop_duplicates()
        
        # Remove duplicates based on key columns (player, gameweek, season)
        if all(col in df.columns for col in ['name', 'GW', 'season']):
            df = df.drop_duplicates(subset=['name', 'GW', 'season'], keep='last')
        
        duplicates_removed = initial_count - len(df)
        self.cleaning_report['duplicates_removed'] = duplicates_removed
        
        if duplicates_removed > 0:
            print(f"✓ Removed {duplicates_removed} duplicate rows")
        
        return df
    
    def _fix_data_types(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert columns to appropriate data types."""
        print("\nFixing data types...")
        
        # Convert numeric columns
        for col in self.NUMERIC_COLUMNS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Convert boolean columns
        for col in self.BOOLEAN_COLUMNS:
            if col in df.columns:
                df[col] = df[col].astype(bool)
        
        # Convert kickoff_time to datetime if present
        if 'kickoff_time' in df.columns:
            df['kickoff_time'] = pd.to_datetime(df['kickoff_time'], errors='coerce')
        
        print("✓ Data types fixed")
        return df
    
    def _handle_missing_values(self, df: pd.DataFrame, strategy: str = 'smart') -> pd.DataFrame:
        """
        Handle missing values based on specified strategy.
        
        Args:
            df (pd.DataFrame): Input data
            strategy (str): Filling strategy
                - 'smart': Use context-aware filling
                - 'zero': Fill with 0
                - 'median': Fill with median
                - 'drop': Drop rows with missing values
        """
        print(f"\nHandling missing values (strategy: {strategy})...")
        
        if strategy == 'drop':
            initial_count = len(df)
            df = df.dropna(subset=self.KEY_NUMERIC_COLUMNS)
            print(f"✓ Dropped {initial_count - len(df)} rows with missing key values")
            return df
        
        # Smart filling based on column context
        if strategy == 'smart':
            # For counting stats, fill with 0
            count_cols = ['assists', 'goals_scored', 'clean_sheets', 'yellow_cards', 
                         'red_cards', 'saves', 'bonus', 'own_goals', 'penalties_missed',
                         'penalties_saved']
            for col in count_cols:
                if col in df.columns:
                    df[col] = df[col].fillna(0)
            
            # For minutes, if NaN, player didn't play
            if 'minutes' in df.columns:
                df['minutes'] = df['minutes'].fillna(0)
            
            # For total_points, fill with 0 (if NaN, likely didn't play)
            if 'total_points' in df.columns:
                df['total_points'] = df['total_points'].fillna(0)
            
            # For expected stats, fill with 0
            expected_cols = ['expected_goals', 'expected_assists', 
                           'expected_goal_involvements', 'expected_goals_conceded', 'xP']
            for col in expected_cols:
                if col in df.columns:
                    df[col] = df[col].fillna(0)
            
            # For ICT index components, fill with 0
            ict_cols = ['ict_index', 'influence', 'creativity', 'threat']
            for col in ict_cols:
                if col in df.columns:
                    df[col] = df[col].fillna(0)
            
            # For bps, fill with 0
            if 'bps' in df.columns:
                df['bps'] = df['bps'].fillna(0)
            
            # For goals_conceded, use forward fill within player groups
            if 'goals_conceded' in df.columns:
                df['goals_conceded'] = df['goals_conceded'].fillna(0)
            
            # For value (price), forward fill or use median
            if 'value' in df.columns:
                df['value'] = df.groupby('name')['value'].fillna(method='ffill')
                df['value'] = df['value'].fillna(df['value'].median())
            
            # For was_home, fill with False if missing
            if 'was_home' in df.columns:
                df['was_home'] = df['was_home'].fillna(False)
        
        elif strategy == 'zero':
            # Fill all numeric columns with 0
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            df[numeric_cols] = df[numeric_cols].fillna(0)
        
        elif strategy == 'median':
            # Fill numeric columns with median
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            for col in numeric_cols:
                df[col] = df[col].fillna(df[col].median())
        
        print("✓ Missing values handled")
        return df
    
    def _encode_categorical(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Encode categorical variables as numerical codes.
        Creates both encoded versions and keeps original columns.
        """
        print("\nEncoding categorical variables...")
        
        # Encode position
        if 'position' in df.columns:
            position_map = {'GK': 1, 'DEF': 2, 'MID': 3, 'FWD': 4}
            df['position_encoded'] = df['position'].map(position_map)
            # Handle any positions not in the map
            df['position_encoded'] = df['position_encoded'].fillna(0).astype(int)
        
        # Encode team (keep team names, create numeric codes)
        if 'team' in df.columns:
            df['team_encoded'] = pd.factorize(df['team'])[0] + 1
        
        # Encode opponent_team if not already numeric
        if 'opponent_team' in df.columns:
            if df['opponent_team'].dtype == 'object':
                df['opponent_team_encoded'] = pd.factorize(df['opponent_team'])[0] + 1
        
        print("✓ Categorical variables encoded")
        return df
    
    def _create_dummy_variables(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create dummy variables for categorical columns.
        """
        print("\nCreating dummy variables...")
        
        categorical_cols = []
        if 'position' in df.columns:
            categorical_cols.append('position')
        if 'team' in df.columns:
            categorical_cols.append('team')
        
        if categorical_cols:
            df = pd.get_dummies(df, columns=categorical_cols, prefix=categorical_cols, drop_first=False)
            print(f"✓ Dummy variables created for: {categorical_cols}")
        
        return df
    
    def _fix_boolean_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Ensure boolean columns are properly formatted."""
        for col in self.BOOLEAN_COLUMNS:
            if col in df.columns:
                # Convert to numeric (1/0) for easier processing
                df[f'{col}_numeric'] = df[col].astype(int)
        
        return df
    
    def _remove_invalid_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Remove rows with invalid data (e.g., negative points in impossible scenarios).
        """
        initial_count = len(df)
        
        # Remove rows where GW is missing or invalid
        if 'GW' in df.columns:
            df = df[df['GW'].notna()]
            df = df[df['GW'] > 0]
        
        # Remove rows where player name is missing
        if 'name' in df.columns:
            df = df[df['name'].notna()]
            df = df[df['name'] != '']
        
        invalid_removed = initial_count - len(df)
        self.cleaning_report['invalid_rows_removed'] = invalid_removed
        
        if invalid_removed > 0:
            print(f"✓ Removed {invalid_removed} invalid rows")
        
        return df
    
    def _print_cleaning_report(self):
        """Print a summary report of the cleaning operations."""
        print("\n" + "="*60)
        print("CLEANING REPORT")
        print("="*60)
        print(f"Initial shape: {self.cleaning_report['initial_shape']}")
        print(f"Final shape: {self.cleaning_report['final_shape']}")
        print(f"Rows removed: {self.cleaning_report['initial_shape'][0] - self.cleaning_report['final_shape'][0]}")
        print(f"  - Duplicates: {self.cleaning_report['duplicates_removed']}")
        print(f"  - Invalid rows: {self.cleaning_report['invalid_rows_removed']}")
        
        missing_before = self.cleaning_report['missing_values_before']
        missing_after = self.cleaning_report['missing_values_after']
        
        if missing_before:
            print(f"\nMissing values before: {len(missing_before)} columns affected")
        if missing_after:
            print(f"Missing values after: {len(missing_after)} columns still have missing values")
            for col, count in missing_after.items():
                print(f"  - {col}: {count}")
        else:
            print("\n✓ No missing values in final dataset!")
        
        print("="*60 + "\n")


def main():
    """
    Example usage of the FPL Data Cleaner.
    """
    # First, load data using the ingestion module
    try:
        from .data_ingestion import FPLDataLoader
    except ImportError:
        from data_ingestion import FPLDataLoader
    
    loader = FPLDataLoader(base_path='./data')
    df_raw = loader.load_current_and_previous_season()
    
    # Clean the data
    cleaner = FPLDataCleaner()
    df_clean = cleaner.clean_data(
        df_raw,
        fill_strategy='smart',
        drop_duplicates=True,
        create_dummies=False  # Set to True if you want dummy variables
    )
    
    # Display results
    print("\nCleaned Data Sample:")
    print(df_clean.head())
    print("\nData Types:")
    print(df_clean.dtypes)
    print("\nData Info:")
    print(df_clean.info())
    
    return df_clean


if __name__ == "__main__":
    df = main()
