"""
ingest_2026_27.py
=================
One-off season rollover ingest: pull every finished 2026-27 gameweek from
olbauday/FPL-Core-Insights into data/processed_fpl_data.csv, add the GW8
planning skeleton, and rebuild features so the new season is consistent
with the rest of the dataset.

Why this exists: update_data.py's weekly pipeline only ever fetches the
*latest* finished GW, so it cannot backfill a whole new season. This script
loops GW1..latest-finished, reusing update_data.py's own helpers
(``enrich_gw_rows``, ``merge_data``, ``build_planning_gw_skeleton``,
``engineer_features``, ``save_data``) so the result is identical in shape
to a season of weekly runs.

Feature consistency note: the shipped CSV's base rolling columns
(``total_points_last_3_avg`` etc.) are stale/all-NaN for the most recent
season — analysis/compute_cv_metrics.py already works around this by
dropping them and recomputing with ``add_base_rolling_features``. We do
the same here for the whole dataset before MasterFPLFeatureEngineer runs,
so every season's rolling features are computed the same way.

Run from repo root:
    python scripts/ingest_2026_27.py
"""

from __future__ import annotations

import io
import os
import sys

import pandas as pd
import requests

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "analysis"))

import update_data as ud  # noqa: E402
from train_with_history import add_base_rolling_features  # noqa: E402

# Base rolling columns recomputed from raw stats (mirrors compute_cv_metrics.py).
_STALE_ROLL: list[str] = []
for _col, _windows in [
    ("total_points", [3, 5, 10]),
    ("minutes", [3, 5]),
    ("ict_index", [3, 5]),
    ("creativity", [3, 5]),
    ("threat", [3, 5]),
    ("influence", [3, 5]),
    ("bps", [3, 5]),
    ("bonus", [3]),
    ("clean_sheets", [3, 5]),
]:
    for _w in _windows:
        _STALE_ROLL.append(f"{_col}_last_{_w}_avg")
_STALE_ROLL += ["season_avg_points", "points_std_last_5", "games_played"]


def fetch_gw(gw: int, bootstrap: dict, fixtures: list) -> pd.DataFrame:
    """Download one finished GW from olbauday and enrich to master schema."""
    url = (
        "https://raw.githubusercontent.com/olbauday/FPL-Core-Insights/main"
        f"/data/{ud._INGEST_SEASON_DIR}/By%20Gameweek/GW{gw}/player_gameweek_stats.csv"
    )
    resp = requests.get(url, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"GW{gw}: HTTP {resp.status_code} for {url}")
    df = pd.read_csv(io.StringIO(resp.text))
    rename_map = {"web_name": "name", "gw": "GW", "now_cost": "value", "id": "element"}
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    df["season"] = ud.ACTIVE_INGEST_SEASON
    df = ud.enrich_gw_rows(df, gw, bootstrap=bootstrap, fixtures=fixtures)
    print(f"  GW{gw}: {len(df):,} rows enriched "
          f"(team nulls: {int(df['team'].isna().sum())}, "
          f"position nulls: {int(df['position'].isna().sum())})")
    return df


def main() -> None:
    season = ud.ACTIVE_INGEST_SEASON
    print(f"Ingesting season {season} (dir {ud._INGEST_SEASON_DIR})")

    bootstrap = ud.fetch_bootstrap_static()
    latest_finished = ud._latest_finished_gw_from_bootstrap(bootstrap)
    print(f"Latest finished GW per FPL API: {latest_finished}")

    fx_resp = requests.get(ud.FPL_FIXTURES_URL, timeout=60)
    fixtures = fx_resp.json() if fx_resp.status_code == 200 else []

    frames = [fetch_gw(gw, bootstrap, fixtures)
              for gw in range(1, latest_finished + 1)]
    new_df = pd.concat(frames, ignore_index=True, sort=False)
    print(f"Fetched {len(new_df):,} rows for {season} "
          f"GW1-{latest_finished}")

    existing = ud.load_existing_data()
    existing = ud.drop_planning_placeholder_rows(existing)

    # Unit repair (pre-existing bug in the shipped CSV): part of 2025-26 was
    # ingested from the olbauday export without unit conversion, leaving
    # £m-scale prices (e.g. 14.0) among tenths-scale ones (e.g. 140). Any
    # value < 30 is unambiguously £m-scale — the cheapest legitimate
    # tenths price is ~38 — so scale those rows up to tenths.
    if "value" in existing.columns:
        v = pd.to_numeric(existing["value"], errors="coerce")
        mask = v < 30
        print(f"  Repairing price units on {int(mask.sum()):,} existing rows "
              f"(£m -> tenths)")
        existing.loc[mask, "value"] = v[mask] * 10
    # Remove any pre-existing rows for the target season (idempotent re-runs).
    before = len(existing)
    existing = existing[existing["season"].astype(str) != season]
    if len(existing) != before:
        print(f"  Dropped {before - len(existing):,} pre-existing {season} rows")

    merged = ud.merge_data(existing, new_df)

    planning = ud.build_planning_gw_skeleton(merged)
    if not planning.empty:
        merged = ud.merge_data(merged, planning)

    # Recompute base rolling features dataset-wide (see module docstring).
    drop_cols = [c for c in _STALE_ROLL if c in merged.columns]
    print(f"Recomputing base rolling features (dropping {len(drop_cols)} stale cols)")
    merged = merged.drop(columns=drop_cols)
    merged = add_base_rolling_features(merged)

    engineered = ud.engineer_features(merged)
    ud.save_data(engineered)

    # ── Verification summary ──────────────────────────────────────────────
    sub = engineered[engineered["season"].astype(str) == season]
    print("\nVerification — rows per GW for", season)
    print(sub.groupby("GW").size().to_string())
    real = sub[sub["is_planning_gw"].fillna(False).astype(bool) == False]  # noqa: E712
    print(f"Real rows: {len(real):,} | planning rows: {len(sub) - len(real):,}")
    dupes = real[real.duplicated(subset=["name", "GW"], keep=False)]
    print(f"(name, GW) duplicate rows among real rows: {len(dupes)}")
    if len(dupes):
        print(dupes[["name", "GW", "element"]].head(20).to_string())
    print(f"Unique elements GW7: "
          f"{real.loc[real['GW'] == latest_finished, 'element'].nunique()}")


if __name__ == "__main__":
    main()
