"""
update_data.py
==============
Weekly data refresh script for the FPL Stats Agent.
Executed automatically by a GitHub Action every week.

Pipeline (in order):
    1. FETCH    — placeholder function that returns the latest GW data as a DataFrame
    2. LOAD     — read the existing master CSV from data/processed_fpl_data.csv
    3. MERGE    — append the new GW rows to the existing dataset
    4. ENGINEER — re-run MasterFPLFeatureEngineer so all rolling features
                  (last_5_avg_points, xP_last_3, ewm_points, etc.) are
                  recalculated across the full updated dataset
    5. SAVE     — overwrite data/processed_fpl_data.csv with the result

Constraints:
    - Do NOT modify master_feature_engineering.py — only import and call it.
    - This script must be runnable as a standalone process (no Flask/FastAPI).
    - All output goes to stdout so the GitHub Actions log captures it.

Usage (locally):
    python update_data.py

Usage (GitHub Actions — see .github/workflows/weekly_update.yml):
    - uses: actions/checkout@v4
    - run: pip install -r requirements.txt
    - run: python update_data.py
"""

from __future__ import annotations

import os
import sys
import shutil
import logging

import io

import pandas as pd
import requests

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# Using Python's logging module (not bare print) so every line has a timestamp.
# GitHub Actions captures stdout/stderr and shows it in the workflow run log,
# so this gives junior devs a clear audit trail of what happened and when.
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("update_data")


# ─────────────────────────────────────────────────────────────────────────────
# PATHS
# os.path.abspath(__file__) gives the absolute path of THIS script,
# regardless of which directory you launch it from.
# dirname() strips the filename, leaving the repo root.
# This means DATA_PATH and ANALYSIS_DIR are always correct even when
# GitHub Actions checks out the repo to an unexpected working directory.
# ─────────────────────────────────────────────────────────────────────────────
REPO_ROOT    = os.path.dirname(os.path.abspath(__file__))
DATA_PATH    = os.path.join(REPO_ROOT, "data", "processed_fpl_data.csv")
ANALYSIS_DIR = os.path.join(REPO_ROOT, "analysis")

# Add the analysis/ folder to Python's module search path so that
# `from master_feature_engineering import MasterFPLFeatureEngineer` works
# without needing an __init__.py or package installation.
if ANALYSIS_DIR not in sys.path:
    sys.path.insert(0, ANALYSIS_DIR)


# =============================================================================
# STEP 1 — FETCH
# =============================================================================
# Two sub-steps:
#
#   1a. Hit the official FPL bootstrap-static API to find the highest GW
#       whose `finished` flag is True.  This tells us which GW has fully
#       completed results available — we never try to pull a GW that is
#       still in progress or hasn't kicked off yet.
#
#   1b. Build the raw GitHub URL for that specific GW's CSV in the
#       olbauday/FPL-Core-Insights repo and download it.
#       raw.githubusercontent.com serves the plain file content (no HTML
#       wrapper), which is exactly what pd.read_csv() expects.
#
# If either HTTP call fails we raise immediately — the GitHub Action will
# mark the workflow run as FAILED and the existing CSV stays untouched.
# =============================================================================

def fetch_latest_gameweek_data() -> pd.DataFrame:
    """
    Dynamically find the latest finished Gameweek via the FPL API, then
    download that GW's CSV from the olbauday/FPL-Core-Insights GitHub repo.

    Returns
    -------
    pd.DataFrame
        One row per player for the latest finished gameweek.

    Raises
    ------
    Exception
        If the FPL API is unreachable or the GitHub CSV returns a non-200
        status (e.g. the GW file hasn't been pushed to the repo yet).
    """
    log.info("STEP 1 — FETCH: retrieving latest gameweek data...")

    # ── 1a. Ask the official FPL API which GW is the latest finished one ──
    # bootstrap-static/ returns a large JSON blob that contains (among other
    # things) an "events" list — one entry per gameweek of the season.
    # Each event has a boolean `finished` field.  We iterate through all
    # events and keep track of the highest GW ID where finished == True.
    log.info("  Checking official FPL API for the latest finished Gameweek...")

    fpl_url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    response = requests.get(fpl_url)

    if response.status_code != 200:
        # Raise loudly — do not silently fall back to stale data, because
        # that would overwrite the CSV with re-engineered but unchanged rows
        # and waste the GitHub Actions minutes.
        raise Exception(
            f"Failed to connect to FPL Bootstrap API. "
            f"Status code: {response.status_code}"
        )

    data = response.json()

    # Walk through every event (GW) and find the latest one that is finished.
    # We start at 1 so that if no GW is finished yet (pre-season) the
    # variable still has a safe default value rather than None.
    latest_gw = 1
    for event in data["events"]:
        if event["finished"] is True:
            # event["id"] is the GW number (1-38)
            latest_gw = event["id"]

    log.info(f"  Latest finished Gameweek is GW{latest_gw}.")

    # ── 1b. Fetch player_gameweek_stats.csv for that GW from the repo ────
    # Repo path structure (actual filenames as of 2025-26):
    #   data/2025-2026/By Gameweek/GW{N}/player_gameweek_stats.csv
    # Spaces in the path must be URL-encoded as %20.
    repo_url = (
        f"https://raw.githubusercontent.com/olbauday/FPL-Core-Insights/main"
        f"/data/2025-2026/By%20Gameweek/GW{latest_gw}/player_gameweek_stats.csv"
    )

    log.info(f"  Fetching raw CSV from: {repo_url}")
    csv_response = requests.get(repo_url)

    if csv_response.status_code != 200:
        raise Exception(
            f"Failed to fetch CSV from GitHub. "
            f"Status code: {csv_response.status_code}. "
            f"URL attempted: {repo_url}"
        )

    df = pd.read_csv(io.StringIO(csv_response.text))

    # ── 1c. Normalise column names to match the master CSV schema ──────────
    # player_gameweek_stats.csv uses different column names than the master
    # CSV that the Stats Agent was trained on.  Map them here so MERGE works.
    rename_map = {
        "web_name":    "name",
        "gw":          "GW",
        "now_cost":    "value",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    # Add season column so the dedup key (name, GW, season) works correctly
    df["season"] = "2025-26"

    log.info(
        f"  Successfully loaded GW{latest_gw} data: "
        f"{len(df)} rows, {len(df.columns)} columns."
    )

    return df


# =============================================================================
# STEP 2 — LOAD
# =============================================================================
# Read the existing master CSV.  This file is the single source of truth
# for the Stats Agent — it contains every season's cleaned and
# feature-engineered player-gameweek rows.
#
# WHY load it fresh each run (rather than caching in memory)?
#   This script is stateless — it starts from scratch every time the GitHub
#   Action triggers it.  Loading fresh guarantees we always work from the
#   latest committed version of the file, not a stale in-memory copy.
# =============================================================================

def load_existing_data() -> pd.DataFrame:
    """
    Load the current master dataset from disk.

    Returns
    -------
    pd.DataFrame
        The full existing dataset with all engineered feature columns.

    Raises
    ------
    FileNotFoundError
        If processed_fpl_data.csv does not exist at the expected path.
        This should never happen in CI because the file is committed to the repo.
    """
    log.info("STEP 2 — LOAD: reading existing master CSV...")

    if not os.path.exists(DATA_PATH):
        # This would only happen if someone accidentally deleted the file from
        # the repo.  Raise loudly so the GitHub Action fails visibly.
        raise FileNotFoundError(
            f"Master CSV not found at: {DATA_PATH}\n"
            "Make sure data/processed_fpl_data.csv is committed to the repo."
        )

    existing_df = pd.read_csv(DATA_PATH)

    log.info(
        f"  Loaded {len(existing_df):,} existing rows | "
        f"seasons: {existing_df['season'].unique().tolist()} | "
        f"columns: {len(existing_df.columns)}"
    )

    return existing_df


# =============================================================================
# STEP 3 — MERGE
# =============================================================================
# Append the newly fetched gameweek rows to the existing dataset.
#
# WHY append rather than replace?
#   The feature engineering in Step 4 computes ROLLING averages
#   (last_5_avg_points, ewm_points, etc.) using every previous gameweek for
#   each player.  If we only kept the new GW rows we'd lose all the history
#   that the rolling windows depend on, and every rolling feature would be NaN.
#
# DUPLICATE SAFETY:
#   If this script runs twice in the same week (e.g. the Action is re-run
#   manually), the same GW rows would be appended twice.  The
#   drop_duplicates() call below prevents that by deduplicating on the
#   natural key (player name × GW × season).
# =============================================================================

def merge_data(existing_df: pd.DataFrame, new_df: pd.DataFrame) -> pd.DataFrame:
    """
    Append new gameweek rows to the existing dataset, deduplicating on
    (name, GW, season) to guard against double-runs.

    Parameters
    ----------
    existing_df : pd.DataFrame
        The full existing master dataset loaded from disk.
    new_df : pd.DataFrame
        The freshly fetched gameweek rows from fetch_latest_gameweek_data().

    Returns
    -------
    pd.DataFrame
        Combined DataFrame sorted by player → season → GW, ready for
        feature engineering.
    """
    log.info("STEP 3 — MERGE: appending new rows to existing dataset...")

    # If the fetch step returned nothing (placeholder behaviour, or a failed
    # network call), skip the append entirely and just return existing data.
    # The pipeline still runs to completion — it just won't add new rows.
    if new_df.empty:
        log.warning(
            "  New data is empty — skipping append.  "
            "Existing dataset will be re-engineered as-is."
        )
        return existing_df

    # pd.concat stacks the two DataFrames vertically (row-wise).
    # ignore_index=True resets the integer index so there are no duplicate
    # index values, which would confuse rolling() and groupby() operations.
    # sort=False preserves the column order of existing_df.
    merged_df = pd.concat([existing_df, new_df], ignore_index=True, sort=False)

    rows_before_dedup = len(merged_df)

    # Deduplicate on the natural key.
    # keep="last" means if the same player-GW-season appears twice we keep
    # the newer row (the one we just fetched), which may have corrected values.
    if all(col in merged_df.columns for col in ["name", "GW", "season"]):
        merged_df = merged_df.drop_duplicates(
            subset=["name", "GW", "season"],
            keep="last",
        )

    dupes_removed = rows_before_dedup - len(merged_df)
    if dupes_removed:
        log.info(f"  Removed {dupes_removed} duplicate rows (same player-GW-season).")

    # Sort by player → season → GW so pandas rolling() windows operate on
    # consecutive gameweeks in the correct order.
    # If the data is unsorted, last_5_avg_points would be computed over
    # random non-consecutive rows — a silent, hard-to-debug bug.
    merged_df = merged_df.sort_values(
        ["name", "season", "GW"]
    ).reset_index(drop=True)

    log.info(
        f"  Merged dataset: {len(merged_df):,} rows "
        f"(+{len(new_df):,} new, {dupes_removed} dupes removed)"
    )

    return merged_df


# =============================================================================
# STEP 4 — ENGINEER
# =============================================================================
# Re-run MasterFPLFeatureEngineer over the ENTIRE merged dataset.
#
# WHY re-run over all rows (not just the new ones)?
#   Rolling features like last_5_avg_points for the NEW gameweek depend on
#   the previous 5 rows for each player.  But rolling features for EXISTING
#   rows don't change — they were already computed correctly.
#
#   MasterFPLFeatureEngineer is designed to be idempotent:
#   most methods check `if col not in self.df.columns` before adding a
#   feature.  So re-running it doesn't break or duplicate existing features
#   — it only fills in new ones (e.g. for the freshly appended rows).
#
# DO NOT MODIFY master_feature_engineering.py.
#   We import it as a black box.  Any changes to how features are computed
#   should go in that file, and this script will automatically pick them up
#   on the next run.
# =============================================================================

def engineer_features(merged_df: pd.DataFrame) -> pd.DataFrame:
    """
    Pass the merged DataFrame through MasterFPLFeatureEngineer to
    recalculate all rolling and advanced features.

    Parameters
    ----------
    merged_df : pd.DataFrame
        Combined dataset from merge_data() — raw + existing engineered columns.

    Returns
    -------
    pd.DataFrame
        Fully re-engineered DataFrame ready to be saved as the new master CSV.
    """
    log.info("STEP 4 — ENGINEER: running MasterFPLFeatureEngineer...")

    # Import here (not at the top of the file) so that if the analysis/ path
    # injection above ever fails, the error appears here with a clear message
    # rather than silently causing a NameError later in the pipeline.
    try:
        from master_feature_engineering import MasterFPLFeatureEngineer
    except ImportError as exc:
        raise ImportError(
            f"Could not import MasterFPLFeatureEngineer: {exc}\n"
            f"Expected it at: {ANALYSIS_DIR}/master_feature_engineering.py"
        ) from exc

    # Drop columns that MasterFPLFeatureEngineer creates internally via merges.
    # If these already exist in the DataFrame (because a previous run of this
    # script saved them to the CSV), the internal merge produces _x/_y suffix
    # duplicates and the engineer crashes with "Column not found: opponent_strength".
    _merge_created = [
        "opponent_strength",           # add_fixture_difficulty_elo
        "opponent_team_name",          # intermediate used by elo + defensive merges
        "opponent_xGC_last_3",         # add_defensive_features (opponent xGC merge)
        "opponent_xGC_last_5",         # add_defensive_features (opponent xGC merge)

        "team_total_points_last_gw",   # add_teammate_synergy
        "team_goals_last_3",           # add_attacking_features
        "team_xG_last_3",              # add_attacking_features
        "team_cs_rate_last_3",         # add_defensive_features
        "team_cs_rate_last_5",         # add_defensive_features
    ]
    merged_df = merged_df.drop(columns=[c for c in _merge_created if c in merged_df.columns])

    # Instantiate the engineer.
    # The constructor copies the DataFrame internally (df.copy()) so our
    # merged_df variable is not mutated — safe for debugging if needed.
    engineer = MasterFPLFeatureEngineer(merged_df)

    # create_all_master_features() runs all 14 feature engineering steps
    # in the correct order and returns the enriched DataFrame.
    # Features added include (among others):
    #   - ewm_points           : exponentially weighted form (decay-weighted)
    #   - avg_minutes_last_3/5 : rotation risk proxy
    #   - xP_last_3, xP_last_5: FPL's expected-points metric, rolling
    #   - xGI_last_3           : expected goal involvements last 3 GWs
    #   - blank_rate_last_5    : fraction of last 5 GWs with 0 minutes played
    #   - ict_index_last_3/5   : ICT rolling averages
    #   - team_goals_last_3    : team-level attacking strength proxy
    #   - team_cs_rate_last_3  : team-level clean sheet rate (for defenders)
    #   - transfer_momentum    : community buy/sell signal
    #   - availability_weight  : injury probability from FPL's own field
    engineered_df = engineer.create_all_master_features()

    log.info(
        f"  Feature engineering complete: "
        f"{len(engineered_df):,} rows | {len(engineered_df.columns)} columns"
    )

    return engineered_df


# =============================================================================
# STEP 5 — SAVE
# =============================================================================
# Overwrite data/processed_fpl_data.csv with the re-engineered DataFrame.
#
# SAFE WRITE PATTERN (write → backup → replace):
#   1. Write the new data to a temp file (.tmp) first.
#      If something goes wrong mid-write (disk full, process killed), the
#      original CSV is still intact.
#   2. Back up the current CSV to .bak — one-step rollback if needed.
#   3. Atomically rename the .tmp file to the live CSV path.
#
# After this step, the Stats Agent automatically uses the fresh data on its
# next invocation — no restart of the backend server is needed because the
# agent reads the CSV fresh on every API call.
# =============================================================================

def save_data(engineered_df: pd.DataFrame) -> None:
    """
    Safely overwrite data/processed_fpl_data.csv, keeping one .bak rollback.

    Parameters
    ----------
    engineered_df : pd.DataFrame
        Fully engineered DataFrame returned by engineer_features().
    """
    log.info("STEP 5 — SAVE: writing updated master CSV to disk...")

    tmp_path = DATA_PATH + ".tmp"
    bak_path = DATA_PATH + ".bak"

    # Write to a temp file first — if this crashes, the live CSV is unharmed
    engineered_df.to_csv(tmp_path, index=False)
    log.info(f"  New data written to temp file: {tmp_path}")

    # Backup the current live CSV before we replace it
    if os.path.exists(DATA_PATH):
        shutil.copy2(DATA_PATH, bak_path)
        log.info(f"  Previous version backed up to: {bak_path}")

    # Replace the live CSV with the new one
    # shutil.move is effectively atomic on most file systems — the agent
    # will never read a half-written file even if it's running concurrently
    shutil.move(tmp_path, DATA_PATH)

    log.info(f"  ✓ data/processed_fpl_data.csv updated successfully.")
    log.info(
        f"\n  Final dataset:"
        f"\n    Rows     : {len(engineered_df):,}"
        f"\n    Columns  : {len(engineered_df.columns)}"
        f"\n    Seasons  : {engineered_df['season'].unique().tolist()}"
        f"\n    GW range : GW{int(engineered_df['GW'].min())} → GW{int(engineered_df['GW'].max())}"
        f"\n    Players  : {engineered_df['name'].nunique():,} unique"
    )


# =============================================================================
# MAIN — orchestrates the five steps in order
# =============================================================================

def main() -> None:
    """
    Entry point.  Runs all five pipeline steps sequentially.
    Exits with code 1 on any unrecoverable error so that the GitHub Action
    marks the workflow run as FAILED and can send an alert.
    """
    log.info("=" * 62)
    log.info("   FPL WEEKLY DATA UPDATE PIPELINE")
    log.info("=" * 62)

    try:
        # Step 1: get the latest GW data (placeholder for now)
        new_df = fetch_latest_gameweek_data()

        # Step 2: load what's already on disk
        existing_df = load_existing_data()

        # Step 3: combine old + new
        merged_df = merge_data(existing_df, new_df)

        # Step 4: recalculate all rolling / advanced features
        engineered_df = engineer_features(merged_df)

        # Step 5: persist to disk
        save_data(engineered_df)

    except Exception as exc:
        # Log the full traceback so it appears in the GitHub Actions log,
        # then exit with code 1 so the workflow is marked as failed.
        log.exception(f"Pipeline failed: {exc}")
        sys.exit(1)

    log.info("=" * 62)
    log.info("   PIPELINE COMPLETE — Stats Agent will use fresh data")
    log.info("   on its next run. No backend restart needed.")
    log.info("=" * 62)


if __name__ == "__main__":
    main()
