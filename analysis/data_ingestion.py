"""
Data Ingestion Module for FPL Optimizer
========================================
This module handles loading historical FPL gameweek data from multiple seasons.
"""

import pandas as pd
import os
from pathlib import Path
from typing import List, Optional


class FPLDataLoader:
    """
    A class to handle loading FPL data from the Vaastav GitHub repo structure.
    
    Attributes:
        base_path (Path): Base directory containing season folders
        seasons (List[str]): List of seasons to load (e.g., ['2023-24', '2024-25'])
    """
    
    def __init__(self, base_path: str = './data'):
        """
        Initialize the FPL Data Loader.
        
        Args:
            base_path (str): Path to the data directory containing season folders
        """
        self.base_path = Path(base_path)
        
    def get_available_seasons(self) -> List[str]:
        """
        Get all available seasons in the data directory.
        
        Returns:
            List[str]: List of season folder names (e.g., ['2023-24', '2024-25'])
        """
        if not self.base_path.exists():
            raise FileNotFoundError(f"Data directory not found: {self.base_path}")
        
        # Get all directories that match the season pattern (YYYY-YY)
        seasons = [d.name for d in self.base_path.iterdir() 
                  if d.is_dir() and '-' in d.name]
        return sorted(seasons)
    
    def load_season_data(self, season: str, use_merged: bool = True) -> pd.DataFrame:
        """
        Load gameweek data for a single season.
        
        Args:
            season (str): Season identifier (e.g., '2023-24')
            use_merged (bool): If True, load merged_gw.csv; otherwise load individual GW files
            
        Returns:
            pd.DataFrame: DataFrame containing all gameweek data for the season
        """
        season_path = self.base_path / season / 'gws'
        
        if not season_path.exists():
            raise FileNotFoundError(f"Season path not found: {season_path}")
        
        if use_merged:
            # Load the pre-merged file if available
            merged_file = season_path / 'merged_gw.csv'
            if merged_file.exists():
                df = pd.read_csv(merged_file)
                # Add season column if not present
                if 'season' not in df.columns:
                    df['season'] = season
                print(f"✓ Loaded {season}: {len(df)} records from merged file")
                return df
            else:
                print(f"Warning: merged_gw.csv not found for {season}, loading individual files...")
        
        # Load individual gameweek files
        gw_files = sorted(season_path.glob('gw*.csv'))
        if not gw_files:
            raise FileNotFoundError(f"No gameweek files found in {season_path}")
        
        dfs = []
        for gw_file in gw_files:
            # Extract gameweek number from filename
            gw_num = int(gw_file.stem.replace('gw', ''))
            df_gw = pd.read_csv(gw_file)
            
            # Add GW column if not present
            if 'GW' not in df_gw.columns:
                df_gw['GW'] = gw_num
            
            dfs.append(df_gw)
        
        df = pd.concat(dfs, ignore_index=True)
        df['season'] = season
        print(f"✓ Loaded {season}: {len(df)} records from {len(gw_files)} gameweek files")
        return df
    
    def load_multiple_seasons(self, seasons: Optional[List[str]] = None, 
                             use_merged: bool = True) -> pd.DataFrame:
        """
        Load and combine data from multiple seasons.
        
        Args:
            seasons (List[str], optional): List of seasons to load. 
                                          If None, loads all available seasons.
            use_merged (bool): If True, use merged_gw.csv files
            
        Returns:
            pd.DataFrame: Combined DataFrame with data from all specified seasons
        """
        if seasons is None:
            seasons = self.get_available_seasons()
            print(f"Loading all available seasons: {seasons}")
        
        if not seasons:
            raise ValueError("No seasons specified or found")
        
        all_data = []
        for season in seasons:
            try:
                df = self.load_season_data(season, use_merged=use_merged)
                all_data.append(df)
            except Exception as e:
                print(f"✗ Error loading {season}: {e}")
                continue
        
        if not all_data:
            raise ValueError("No data was successfully loaded")
        
        combined_df = pd.concat(all_data, ignore_index=True)
        print(f"\n{'='*60}")
        print(f"Total records loaded: {len(combined_df):,}")
        print(f"Seasons included: {combined_df['season'].unique().tolist()}")
        print(f"Gameweeks range: {combined_df['GW'].min()} to {combined_df['GW'].max()}")
        print(f"{'='*60}\n")
        
        return combined_df
    
    def load_current_and_previous_season(self) -> pd.DataFrame:
        """
        Load data for the current season and the previous season.
        This is useful for recent data analysis and model training.
        
        Returns:
            pd.DataFrame: Combined DataFrame with current and previous season data
        """
        available_seasons = self.get_available_seasons()
        
        if len(available_seasons) < 1:
            raise ValueError("No seasons found in data directory")
        
        # Get the two most recent seasons
        if len(available_seasons) >= 2:
            recent_seasons = available_seasons[-2:]
        else:
            recent_seasons = available_seasons[-1:]
        
        print(f"Loading recent seasons: {recent_seasons}")
        return self.load_multiple_seasons(recent_seasons)


def main():
    """
    Example usage of the FPL Data Loader.
    """
    # Initialize the loader
    loader = FPLDataLoader(base_path='./data')
    
    # Option 1: Load current and previous season
    df = loader.load_current_and_previous_season()
    
    # Display basic info
    print("\nDataFrame Info:")
    print(f"Shape: {df.shape}")
    print(f"\nColumns: {df.columns.tolist()}")
    print(f"\nFirst few rows:")
    print(df.head())
    
    # Option 2: Load specific seasons
    # df = loader.load_multiple_seasons(['2023-24', '2024-25'])
    
    # Option 3: Load all available seasons
    # df = loader.load_multiple_seasons()
    
    return df


if __name__ == "__main__":
    df = main()
