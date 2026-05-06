"""
update_data.py
==============
Data refresh pipeline for the FPL Stats Agent.
- Run locally: ``python update_data.py``          (cheap no-op if CSV already caught up)
- GitHub Action: ``.github/workflows/weekly_update.yml`` (twice daily + manual dispatch)
- Optional **backend sweep**: ``AUTO_REFRESH_FPL_DATA=1`` (see backend/main.py)

Pipeline (in order):
    1. FETCH    — bootstrap latest finished GW, download that GW CSV from GitHub helper repo
    2. LOAD     — read the existing master CSV from data/processed_fpl_data.csv
    3. MERGE    — append the new GW rows to the existing dataset; drop prior
                  ``is_planning_gw`` preview rows; merge an ``is_next`` planning
                  skeleton (outcomes zeroed; fixtures + ep_next from live FPL API)
    4. ENGINEER — re-run MasterFPLFeatureEngineer so all rolling features
                  (last_5_avg_points, xP_last_3, ewm_points, etc.) are
                  recalculated across the full updated dataset; re-zero realised
                  stats on planning rows after FE
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

import numpy as np
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

# Season label applied to fetched rows — aligned with olbauday/FPL-Core-Insights
# path `data/2025-2026/`. Bump annually when ingest targets a new season.
ACTIVE_INGEST_SEASON = "2025-26"


FPL_BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_FIXTURES_URL = "https://fantasy.premierleague.com/api/fixtures/"


def bootstrap_latest_finished_gw() -> int:
    """Highest GW id with `finished: true` in official bootstrap-static."""
    log.info("  Checking official FPL API for the latest finished Gameweek...")
    response = requests.get(FPL_BOOTSTRAP_URL, timeout=45)
    if response.status_code != 200:
        raise Exception(f"Failed to connect to FPL Bootstrap API ({response.status_code}).")

    latest_gw = 1
    for event in response.json().get("events") or []:
        if event.get("finished") is True:
            latest_gw = int(event["id"])
    log.info(f"  Latest finished Gameweek is GW{latest_gw}.")
    return latest_gw


def fetch_bootstrap_static() -> dict:
    r = requests.get(FPL_BOOTSTRAP_URL, timeout=45)
    if r.status_code != 200:
        raise Exception(f"FPL bootstrap-static failed ({r.status_code}).")
    return r.json()


def bootstrap_planning_gw_id(bootstrap: dict | None = None) -> int | None:
    """FPL ``is_next`` event id — the upcoming deadline GW (preview / xP target)."""
    data = bootstrap if bootstrap is not None else fetch_bootstrap_static()
    for ev in data.get("events") or []:
        if ev.get("is_next") is True and ev.get("id") is not None:
            return int(ev["id"])
    return None


def _latest_finished_gw_from_bootstrap(bootstrap: dict) -> int:
    """Highest event id with ``finished: true`` (same semantics as bootstrap_latest_finished_gw)."""
    latest_gw = 1
    for event in bootstrap.get("events") or []:
        if event.get("finished") is True and event.get("id") is not None:
            latest_gw = max(latest_gw, int(event["id"]))
    return latest_gw


def csv_planning_preview_ok_for_bootstrap(season: str, bootstrap: dict) -> bool:
    """
    True if the CSV already has rows for FPL's current ``is_next`` GW (preview or real).
    When False, we re-run the pipeline even if finished GWs are up to date, so xP / fixtures
    stay on-disk for the Stats Agent.
    """
    pgw = bootstrap_planning_gw_id(bootstrap)
    if pgw is None:
        return True
    if not os.path.exists(DATA_PATH):
        return False
    header = pd.read_csv(DATA_PATH, nrows=0)
    cols = ["season", "GW"]
    if "is_planning_gw" in header.columns:
        cols.append("is_planning_gw")
    df = pd.read_csv(DATA_PATH, usecols=cols, low_memory=False)
    sub = df.loc[(df["season"].astype(str) == season) & (df["GW"] == pgw)]
    if sub.empty:
        return False
    if "is_planning_gw" in sub.columns:
        return bool(sub["is_planning_gw"].fillna(False).astype(bool).any())
    return True


def csv_max_gw_for_season(season: str) -> int | None:
    """Cheap read — max GW including optional planning placeholder rows."""
    if not os.path.exists(DATA_PATH):
        return None
    df = pd.read_csv(DATA_PATH, usecols=["season", "GW"])
    sub = df.loc[df["season"].astype(str) == season, "GW"]
    if sub.empty:
        return None
    return int(sub.max())


def csv_max_finished_gw_for_season(season: str) -> int | None:
    """
    Max GW for `season` counting only **finished** ingested gameweeks.

    Rows with ``is_planning_gw == True`` are the upcoming-GW preview skeleton
    (no real results yet). They must not satisfy the staleness check, otherwise
    we'd skip re-ingest after the next GW completes while the CSV still shows
    a higher GW number from placeholders.
    """
    if not os.path.exists(DATA_PATH):
        return None
    header = pd.read_csv(DATA_PATH, nrows=0)
    cols = ["season", "GW"]
    if "is_planning_gw" in header.columns:
        cols.append("is_planning_gw")
    df = pd.read_csv(DATA_PATH, usecols=cols, low_memory=False)
    sub = df.loc[df["season"].astype(str) == season]
    if sub.empty:
        return None
    if "is_planning_gw" in sub.columns:
        planning = sub["is_planning_gw"].fillna(False).astype(bool)
        sub = sub.loc[~planning]
        if sub.empty:
            return None
    return int(sub["GW"].max())


def drop_planning_placeholder_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Remove prior ``is_planning_gw`` rows before re-merging fresh finished data."""
    if df.empty or "is_planning_gw" not in df.columns:
        return df
    mask = df["is_planning_gw"].fillna(False).astype(bool)
    n = int(mask.sum())
    if n:
        log.info(f"  Dropping {n} prior is_planning_gw preview row(s) before refresh.")
    return df.loc[~mask].reset_index(drop=True)


# Columns that are unknown before a gameweek kicks off — zero or clear for preview rows.
_PLANNING_CLEAR_NUMERIC = [
    "total_points", "minutes", "goals_scored", "assists", "clean_sheets",
    "goals_conceded", "own_goals", "penalties_saved", "penalties_missed",
    "yellow_cards", "red_cards", "saves", "starts", "bonus", "bps",
    "dreamteam_count", "expected_goals", "expected_assists",
    "expected_goal_involvements", "expected_goals_conceded",
    "influence", "creativity", "threat", "ict_index",
    "tackles", "clearances_blocks_interceptions", "recoveries",
    "defensive_contribution",
    "team_a_score", "team_h_score", "event_points",
]


def _fixture_team_maps_for_event(
    fixtures: list,
    planning_gw: int,
    team_id_to_name: dict[int, str],
) -> tuple[dict[int, bool], dict[int, int], dict[int, str]]:
    """Per FPL team id: was_home, opponent_team id, kickoff iso string."""
    was_home: dict[int, bool] = {}
    opp_id: dict[int, int] = {}
    ko: dict[int, str] = {}
    for fx in fixtures or []:
        if fx.get("event") != planning_gw:
            continue
        hid, aid = fx.get("team_h"), fx.get("team_a")
        if hid is None or aid is None:
            continue
        hid_i, aid_i = int(hid), int(aid)
        was_home[hid_i] = True
        was_home[aid_i] = False
        opp_id[hid_i] = aid_i
        opp_id[aid_i] = hid_i
        kt = fx.get("kickoff_time")
        if kt:
            ko[hid_i] = kt
            ko[aid_i] = kt
    _ = team_id_to_name  # reserved if we log missing teams
    return was_home, opp_id, ko


def build_planning_gw_skeleton(merged_df: pd.DataFrame) -> pd.DataFrame:
    """
    One row per player for FPL ``is_next`` GW: copy the latest finished-GW snapshot,
    strip unknown outcomes (points / minutes / xG stats), attach live opponent + xP.

    Does not replace real rows if that GW already exists in ``merged_df`` (e.g. rare
    early GitHub publishes).
    """
    try:
        bootstrap = fetch_bootstrap_static()
        planning_gw = bootstrap_planning_gw_id(bootstrap)
    except Exception as exc:
        log.warning(f"  Planning GW skeleton skipped — bootstrap failed: {exc}")
        return pd.DataFrame()

    if planning_gw is None:
        log.info("  No is_next event in bootstrap — skipping planning skeleton.")
        return pd.DataFrame()

    season_mask = merged_df["season"].astype(str) == ACTIVE_INGEST_SEASON
    if season_mask.any():
        exists = merged_df.loc[season_mask & (merged_df["GW"] == planning_gw)]
        if len(exists) > 0:
            log.info(
                f"  GW{planning_gw} rows already present for {ACTIVE_INGEST_SEASON} "
                "— skipping planning skeleton."
            )
            return pd.DataFrame()

    finished_gw = _latest_finished_gw_from_bootstrap(bootstrap)
    tpl = merged_df.loc[season_mask & (merged_df["GW"] == finished_gw)].copy()
    if tpl.empty:
        mx = merged_df.loc[season_mask, "GW"].max()
        if pd.isna(mx):
            log.warning(
                "  Planning skeleton skipped — no rows for "
                f"{ACTIVE_INGEST_SEASON} GW{finished_gw}."
            )
            return pd.DataFrame()
        mx_i = int(mx)
        tpl = merged_df.loc[season_mask & (merged_df["GW"] == mx_i)].copy()
        log.info(f"  Planning template: GW{mx_i} (fallback; GW{finished_gw} missing).")

    skel = tpl.copy()
    skel["GW"] = planning_gw
    skel["is_planning_gw"] = True

    for col in _PLANNING_CLEAR_NUMERIC:
        if col in skel.columns:
            # Must force 0 — pd.to_numeric(...).fillna(0) preserves real scores such as "116".
            skel.loc[:, col] = 0.0

    # Live element → team id, ep_next (this GW expected points preview)
    el_tbl = pd.DataFrame(bootstrap.get("elements") or [])
    if el_tbl.empty or "id" not in el_tbl.columns:
        log.warning("  Planning skeleton: no elements table — dropping skeleton.")
        return pd.DataFrame()

    ep = pd.to_numeric(el_tbl["ep_next"], errors="coerce") if "ep_next" in el_tbl.columns else None
    el_merge = pd.DataFrame({
        "element": pd.to_numeric(el_tbl["id"], errors="coerce"),
        "_bs_team_id": pd.to_numeric(el_tbl["team"], errors="coerce"),
        "_ep_next_live": ep,
    }).drop_duplicates(subset=["element"])

    if "element" not in skel.columns:
        if "id" in skel.columns:
            skel = skel.rename(columns={"id": "element"})
        else:
            log.warning("  Planning skeleton: no element/id column — aborted.")
            return pd.DataFrame()

    skel["element"] = pd.to_numeric(skel["element"], errors="coerce")
    skel = skel.merge(el_merge, on="element", how="left")

    if "xP" in skel.columns and "_ep_next_live" in skel.columns:
        skel["xP"] = skel["_ep_next_live"].fillna(skel["xP"]).fillna(0.0)
    elif "_ep_next_live" in skel.columns:
        skel["xP"] = skel["_ep_next_live"].fillna(0.0)

    # Team names + opponent from fixtures API
    team_id_to_name = {
        int(t["id"]): str(t.get("name") or "").strip()
        for t in bootstrap.get("teams") or []
        if t.get("id") is not None
    }
    pos_map = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}

    try:
        fx_resp = requests.get(FPL_FIXTURES_URL, timeout=60)
        fixtures = fx_resp.json() if fx_resp.status_code == 200 else []
    except Exception:
        fixtures = []

    was_h, opp_i, ko_by_team = _fixture_team_maps_for_event(
        fixtures, planning_gw, team_id_to_name
    )

    def _row_team_id(r) -> float | None:
        v = r.get("_bs_team_id")
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    team_ids = skel.apply(_row_team_id, axis=1)
    skel["team"] = [team_id_to_name.get(int(t)) if pd.notna(t) else np.nan for t in team_ids]

    wh_list: list[float] = []
    opp_list: list[float] = []
    ko_list: list[str] = []
    for tid in team_ids:
        if tid is None or (isinstance(tid, float) and np.isnan(tid)):
            wh_list.append(float("nan"))
            opp_list.append(float("nan"))
            ko_list.append("")
            continue
        ti = int(tid)
        wh_list.append(1.0 if was_h.get(ti) else (0.0 if ti in was_h else float("nan")))
        opp_list.append(float(opp_i[ti]) if ti in opp_i else float("nan"))
        ko_list.append(ko_by_team.get(ti) or "")

    if "was_home" in skel.columns:
        skel["was_home"] = wh_list
    if "opponent_team" in skel.columns:
        skel["opponent_team"] = opp_list
    elif opp_list:
        skel["opponent_team"] = opp_list

    if "kickoff_time" in skel.columns:
        skel["kickoff_time"] = ko_list

    drop_misc = [c for c in ("_bs_team_id", "_ep_next_live") if c in skel.columns]
    if drop_misc:
        skel = skel.drop(columns=drop_misc)

    if "fixture" in skel.columns:
        skel["fixture"] = np.nan

    # Normalize position strings from bootstrap
    if "element_type" in el_tbl.columns:
        et_map = (
            pd.DataFrame({
                "element": pd.to_numeric(el_tbl["id"], errors="coerce"),
                "element_type": el_tbl["element_type"],
            })
            .assign(_pos_bs=lambda d: pd.to_numeric(d["element_type"], errors="coerce").map(pos_map))
            [["element", "_pos_bs"]]
            .drop_duplicates(subset=["element"])
        )
        skel = skel.merge(et_map, on="element", how="left")
        if "position" in skel.columns:
            skel["position"] = skel["_pos_bs"].fillna(skel["position"])
        skel = skel.drop(columns=[c for c in ["_pos_bs"] if c in skel.columns])

    live_val = pd.to_numeric(el_tbl.get("now_cost"), errors="coerce")
    vm = pd.DataFrame({"element": pd.to_numeric(el_tbl["id"], errors="coerce"), "_nc": live_val})
    skel = skel.merge(vm, on="element", how="left")
    if "value" in skel.columns and "_nc" in skel.columns:
        skel["value"] = skel["_nc"].fillna(skel["value"])
    skel = skel.drop(columns=[c for c in ["_nc"] if c in skel.columns])

    tin = pd.to_numeric(el_tbl.get("transfers_in_event"), errors="coerce").fillna(0)
    tout = pd.to_numeric(el_tbl.get("transfers_out_event"), errors="coerce").fillna(0)
    tm = pd.DataFrame({
        "element": pd.to_numeric(el_tbl["id"], errors="coerce"),
        "_ti": tin,
        "_to": tout,
    })
    skel = skel.merge(tm, on="element", how="left")
    for col, src in (("transfers_in", "_ti"), ("transfers_out", "_to")):
        if src in skel.columns:
            if col in skel.columns:
                skel[col] = skel[src].fillna(skel[col]).fillna(0)
            else:
                skel[col] = skel[src].fillna(0)
    skel = skel.drop(columns=[c for c in ["_ti", "_to"] if c in skel.columns])

    log.info(
        f"  Built planning GW{planning_gw} skeleton: {len(skel)} rows "
        f"(outcomes cleared; fixtures/xP from live API)."
    )
    return skel.reset_index(drop=True)


def processed_csv_already_current(force: bool) -> tuple[bool, str]:
    """If True, skip the merge + feature-engineering step (cheap noop)."""
    if force:
        return False, "--force rebuild requested"
    try:
        bootstrap = fetch_bootstrap_static()
        fpl_mx = _latest_finished_gw_from_bootstrap(bootstrap)
    except Exception as exc:
        return False, f"bootstrap check failed ({exc}), running full pipeline"

    csv_mx = csv_max_finished_gw_for_season(ACTIVE_INGEST_SEASON)
    csv_any = csv_max_gw_for_season(ACTIVE_INGEST_SEASON)
    if csv_mx is None:
        return False, f"no finished {ACTIVE_INGEST_SEASON} rows in CSV — running pipeline"

    if csv_mx < fpl_mx:
        return False, f"{ACTIVE_INGEST_SEASON}: finished CSV GW{csv_mx} < GW{fpl_mx}; refreshing"

    if not csv_planning_preview_ok_for_bootstrap(ACTIVE_INGEST_SEASON, bootstrap):
        pgw = bootstrap_planning_gw_id(bootstrap)
        return False, (
            f"{ACTIVE_INGEST_SEASON}: finished data GW{csv_mx} is current, "
            f"but is_next GW{pgw} preview rows are missing — running pipeline"
        )

    note = ""
    if csv_any is not None and csv_any > csv_mx:
        note = f" (CSV max GW{csv_any} includes planning preview — ignored for freshness)"
    return True, (
        f"{ACTIVE_INGEST_SEASON}: finished data GW{csv_mx} >= latest finished GW{fpl_mx}; "
        f"planning preview ok{note}"
    )


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

    latest_gw = bootstrap_latest_finished_gw()

    # ── 1b. Fetch player_gameweek_stats.csv for that GW from the repo ────
    # Repo path structure (actual filenames as of 2025-26):
    #   data/2025-2026/By Gameweek/GW{N}/player_gameweek_stats.csv
    # Spaces in the path must be URL-encoded as %20.
    repo_url = (
        f"https://raw.githubusercontent.com/olbauday/FPL-Core-Insights/main"
        f"/data/2025-2026/By%20Gameweek/GW{latest_gw}/player_gameweek_stats.csv"
    )

    log.info(f"  Fetching raw CSV from: {repo_url}")
    csv_response = requests.get(repo_url, timeout=60)

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
        "web_name": "name",
        "gw":       "GW",
        "now_cost": "value",
        "id":       "element",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    # Add season column so the dedup key (name, GW, season) works correctly
    df["season"] = ACTIVE_INGEST_SEASON

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

    pm = (
        engineered_df["is_planning_gw"].fillna(False).astype(bool)
        if "is_planning_gw" in engineered_df.columns
        else pd.Series(False, index=engineered_df.index)
    )
    if bool(pm.any()):
        for col in _PLANNING_CLEAR_NUMERIC:
            if col in engineered_df.columns:
                engineered_df.loc[pm, col] = 0.0
        log.info(
            "  Cleared realised-stat columns on "
            f"{int(pm.sum())} is_planning_gw preview row(s) after FE."
        )

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


def _force_refresh_requested() -> bool:
    return (
        "--force" in sys.argv
        or os.getenv("FORCE_FPL_CSV_UPDATE", "").strip().lower()
        in ("1", "true", "yes")
    )


def run_full_refresh_pipeline() -> None:
    """Fetch-merge-engineer-save (no staleness guards). Raises on failure."""
    new_df = fetch_latest_gameweek_data()
    existing_df = load_existing_data()
    existing_df = drop_planning_placeholder_rows(existing_df)
    merged_df = merge_data(existing_df, new_df)

    planning_df = build_planning_gw_skeleton(merged_df)
    if not planning_df.empty:
        merged_df = merge_data(merged_df, planning_df)

    engineered_df = engineer_features(merged_df)
    save_data(engineered_df)


def maybe_refresh_processed_csv(force: bool = False) -> bool:
    """
    Called from FastAPI AUTO_REFRESH_* path. If the CSV already includes every
    finished gameweek for ACTIVE_INGEST_SEASON, skips work and returns False.
    Returns True after a successful rewrite.
    """
    skip, msg = processed_csv_already_current(force)
    log.info(msg)
    if skip:
        return False
    try:
        run_full_refresh_pipeline()
    except Exception as exc:
        log.exception("maybe_refresh_processed_csv failed: %s", exc)
        return False

    log.info(
        "maybe_refresh_processed_csv: pipeline complete "
        "(Stats Agent reads CSV from disk — no uvicorn restart required)."
    )
    return True


def main() -> None:
    """
    Entry point.  Runs fetch→merge→FE→save unless the CSV already matches FPL.

    Override skip with `--force` or env `FORCE_FPL_CSV_UPDATE=1`.
    Exits with code 1 if the pipeline fails (GitHub Actions will show red).
    """
    force = _force_refresh_requested()
    log.info("=" * 62)
    log.info("   FPL WEEKLY DATA UPDATE PIPELINE")
    log.info("=" * 62)

    try:
        skip, msg = processed_csv_already_current(force)
        log.info(msg)
        if skip:
            log.info("=" * 62)
            return
        run_full_refresh_pipeline()
    except Exception as exc:
        log.exception(f"Pipeline failed: {exc}")
        sys.exit(1)

    log.info("=" * 62)
    log.info("   PIPELINE COMPLETE — Stats Agent will use fresh data")
    log.info("   on its next run. No backend restart needed.")
    log.info("=" * 62)


if __name__ == "__main__":
    main()
