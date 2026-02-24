"""
FPL Pipeline - Main Runner Script
==================================
Complete pipeline for FPL data processing, cleaning, and feature engineering.
"""

import pandas as pd
from pathlib import Path
from typing import Optional

try:
    # Relative imports (when used as a package)
    from .data_ingestion import FPLDataLoader
    from .data_cleaning import FPLDataCleaner
    from .feature_engineering import FPLFeatureEngineer
except ImportError:
    # Absolute imports (when run as a script)
    from data_ingestion import FPLDataLoader
    from data_cleaning import FPLDataCleaner
    from feature_engineering import FPLFeatureEngineer


class FPLPipeline:
    """
    Main pipeline that orchestrates the entire FPL data processing workflow.
    
    This class combines data ingestion, cleaning, and feature engineering
    into a single, easy-to-use pipeline.
    """
    
    def __init__(self, base_path: str = './data'):
        """
        Initialize the FPL Pipeline.
        
        Args:
            base_path (str): Path to the data directory
        """
        self.base_path = base_path
        self.loader = FPLDataLoader(base_path=base_path)
        self.cleaner = FPLDataCleaner()
        self.engineer = FPLFeatureEngineer()
        
        self.df_raw = None
        self.df_clean = None
        self.df_features = None
    
    def run_full_pipeline(self, 
                         seasons: Optional[list] = None,
                         fill_strategy: str = 'smart',
                         create_dummies: bool = False,
                         save_output: bool = True) -> pd.DataFrame:
        """
        Run the complete data pipeline.
        
        Args:
            seasons (list, optional): Seasons to load. If None, loads current and previous.
            fill_strategy (str): Missing value strategy ('smart', 'zero', 'median', 'drop')
            create_dummies (bool): Whether to create dummy variables for categoricals
            save_output (bool): Whether to save the processed data
            
        Returns:
            pd.DataFrame: Fully processed data with all features
        """
        print("\n" + "="*70)
        print(" "*20 + "FPL OPTIMIZER PIPELINE")
        print("="*70 + "\n")
        
        # Step 1: Load Data
        print("STEP 1: DATA INGESTION")
        print("-" * 70)
        if seasons is None:
            self.df_raw = self.loader.load_current_and_previous_season()
        else:
            self.df_raw = self.loader.load_multiple_seasons(seasons)
        
        # Step 2: Clean Data
        print("\nSTEP 2: DATA CLEANING")
        print("-" * 70)
        self.df_clean = self.cleaner.clean_data(
            self.df_raw,
            fill_strategy=fill_strategy,
            drop_duplicates=True,
            create_dummies=create_dummies
        )
        
        # Step 3: Feature Engineering
        print("\nSTEP 3: FEATURE ENGINEERING")
        print("-" * 70)
        self.df_features = self.engineer.create_all_features(self.df_clean)
        
        # Step 4: Add target variable
        print("\nSTEP 4: CREATE TARGET VARIABLE")
        print("-" * 70)
        self.df_features = self.engineer.create_target_variable(self.df_features)
        print("✓ Target variable created: target_next_1_gw")
        
        # Step 5: Save output
        if save_output:
            print("\nSTEP 5: SAVE PROCESSED DATA")
            print("-" * 70)
            output_path = Path(self.base_path) / 'processed_fpl_data.csv'
            self.df_features.to_csv(output_path, index=False)
            print(f"✓ Data saved to: {output_path}")
            print(f"  Rows: {len(self.df_features):,}")
            print(f"  Columns: {len(self.df_features.columns)}")
        
        # Print summary
        print("\n" + "="*70)
        print("PIPELINE COMPLETE!")
        print("="*70)
        self._print_pipeline_summary()
        
        return self.df_features
    
    def _print_pipeline_summary(self):
        """Print a summary of the pipeline results."""
        if self.df_features is None:
            print("Pipeline has not been run yet.")
            return
        
        print("\nPIPELINE SUMMARY:")
        print("-" * 70)
        print(f"Total Records: {len(self.df_features):,}")
        print(f"Total Features: {len(self.df_features.columns)}")
        print(f"Seasons: {self.df_features['season'].unique().tolist()}")
        print(f"Gameweeks: GW{self.df_features['GW'].min()} to GW{self.df_features['GW'].max()}")
        print(f"Unique Players: {self.df_features['name'].nunique():,}")
        print(f"Date Range: {self.df_features['kickoff_time'].min()} to {self.df_features['kickoff_time'].max()}")
        
        print("\nKEY FEATURES CREATED:")
        key_features = [
            'last_3_avg_points', 'last_5_avg_points', 'season_avg_points',
            'form_vs_average', 'total_points_per_90', 'home_avg_points',
            'away_avg_points', 'opponent_avg_points_conceded'
        ]
        available_features = [f for f in key_features if f in self.df_features.columns]
        for feature in available_features:
            print(f"  ✓ {feature}")
        
        print("\nDATA QUALITY:")
        missing_count = self.df_features.isnull().sum().sum()
        print(f"  Missing values: {missing_count}")
        print(f"  Completeness: {(1 - missing_count / self.df_features.size) * 100:.2f}%")
        
    def get_modeling_dataset(self, drop_na_target: bool = True) -> pd.DataFrame:
        """
        Get a dataset ready for modeling.
        
        Args:
            drop_na_target (bool): Whether to drop rows with missing target values
            
        Returns:
            pd.DataFrame: Dataset ready for machine learning
        """
        if self.df_features is None:
            raise ValueError("Pipeline has not been run yet. Call run_full_pipeline() first.")
        
        df_model = self.df_features.copy()
        
        # Drop rows with missing target
        if drop_na_target and 'target_next_1_gw' in df_model.columns:
            initial_count = len(df_model)
            df_model = df_model.dropna(subset=['target_next_1_gw'])
            print(f"Dropped {initial_count - len(df_model)} rows with missing target")
        
        return df_model
    
    def get_latest_gameweek_data(self, season: str = '2025-26') -> pd.DataFrame:
        """
        Get data for the most recent gameweek in a season.
        Useful for making predictions for the next gameweek.
        
        Args:
            season (str): Season identifier
            
        Returns:
            pd.DataFrame: Data for the latest gameweek
        """
        if self.df_features is None:
            raise ValueError("Pipeline has not been run yet. Call run_full_pipeline() first.")
        
        season_data = self.df_features[self.df_features['season'] == season]
        latest_gw = season_data['GW'].max()
        
        latest_data = season_data[season_data['GW'] == latest_gw].copy()
        
        print(f"Latest gameweek data for {season}:")
        print(f"  Gameweek: {latest_gw}")
        print(f"  Players: {len(latest_data)}")
        
        return latest_data


def main():
    """
    Example usage of the FPL Pipeline.
    """
    # Initialize and run the pipeline
    pipeline = FPLPipeline(base_path='./data')
    
    # Run complete pipeline
    df_processed = pipeline.run_full_pipeline(
        seasons=None,  # None = current and previous season
        fill_strategy='smart',
        create_dummies=False,
        save_output=True
    )
    
    # Get modeling dataset
    print("\n" + "="*70)
    print("PREPARING MODELING DATASET")
    print("="*70)
    df_model = pipeline.get_modeling_dataset(drop_na_target=True)
    
    # Display sample
    print("\nSample of processed data:")
    display_cols = [
        'name', 'position', 'team', 'GW', 'total_points',
        'last_3_avg_points', 'last_5_avg_points', 'season_avg_points',
        'form_vs_average', 'target_next_1_gw'
    ]
    available_cols = [col for col in display_cols if col in df_model.columns]
    print(df_model[available_cols].head(20))
    
    # Get latest gameweek data for predictions
    print("\n" + "="*70)
    print("LATEST GAMEWEEK DATA")
    print("="*70)
    latest = pipeline.get_latest_gameweek_data(season='2025-26')
    print("\nTop players by last_3_avg_points (current form):")
    form_cols = ['name', 'position', 'team', 'last_3_avg_points', 
                 'last_5_avg_points', 'value']
    available_form_cols = [col for col in form_cols if col in latest.columns]
    print(latest.nlargest(10, 'last_3_avg_points')[available_form_cols])
    
    return df_processed


if __name__ == "__main__":
    df = main()
