"""
Compare model predictions to realised FPL points for one gameweek.

The Stats Agent loads **XGBoost** from ``models/xgb_history_v2.pkl`` in ``run_model`` and sets
``predicted_pts = model.predict(X)``. The UI "xPts" uses ``expected_pts = predicted_pts × start_prob``.

This script can report MAE / R² for:
  * **predicted_pts** — raw XGBoost output (what you want to match training-style metrics)
  * **expected_pts** — risk-adjusted (matches the app)

It also prints **position-stratified** metrics (GK / DEF / MID / FWD): Spearman correlation
(rank alignment), MAE / R² on ``expected_pts``, and **Precision@K** (overlap of top-K by prediction
vs top-K by actual within each position). See ``analysis/position_stratified_evaluation.md``.

**Important:** Metrics on **all ~800 assets** include ~500+ players with **0 minutes** (actual 0,
model often ~2–5). That inflates MAE and can make R² look oddly good or bad depending on the week.
Use ``--played-only`` to restrict to players with **minutes > 0** in FPL live for that GW.

Training metadata (walk-forward CV R² ~0.44) is **not** the same as live one-off evaluation here.

Usage (from repo root)::

  python analysis/gw_prediction_metrics.py --gameweek 30 --season 2025-26
  python analysis/gw_prediction_metrics.py --gameweek 30 --season 2025-26 --played-only
  python analysis/gw_prediction_metrics.py --gameweek 30 --precision-k 5
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from sklearn.metrics import mean_squared_error

POSITIONS: tuple[str, ...] = ("GK", "DEF", "MID", "FWD")
MIN_SPEARMAN_N = 3


def r2_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    y_mean = float(np.mean(y_true))
    ss_tot = float(np.sum((y_true - y_mean) ** 2))
    if ss_tot == 0.0:
        return 1.0 if ss_res == 0.0 else float("-inf")
    return 1.0 - ss_res / ss_tot


def fetch_fpl_live_minutes(event_id: int, timeout: float = 25.0) -> dict[int, int]:
    """element_id -> minutes in that gameweek (0 if did not play)."""
    url = f"https://fantasy.premierleague.com/api/event/{int(event_id)}/live/"
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return {}
    out: dict[int, int] = {}
    for row in data.get("elements") or []:
        eid = row.get("id")
        st = row.get("stats") or {}
        if eid is None:
            continue
        try:
            out[int(eid)] = int(st.get("minutes") or 0)
        except (TypeError, ValueError):
            continue
    return out


def _passes_likely_to_play(row: dict, threshold: float) -> bool:
    """Match Stats Agent + app: ``likely_to_play`` or ``start_prob`` ≥ threshold."""
    lt = row.get("likely_to_play")
    if lt is True:
        return True
    if lt is False:
        return False
    sp = row.get("start_prob")
    if sp is None:
        return False
    try:
        return float(sp) >= threshold
    except (TypeError, ValueError):
        return False


def _normalize_position(pos: object) -> str | None:
    if pos is None:
        return None
    s = str(pos).strip().upper()
    if s == "GKP":
        return "GK"
    if s == "AM":
        return "MID"
    if s in POSITIONS:
        return s
    return None


def _iter_metric_rows(
    rows: list,
    minutes_by_el: dict[int, int] | None,
    played_only: bool,
    likely_only: bool,
    likely_threshold: float,
):
    """Yields (actual, predicted_pts, expected_pts, position) for rows that pass filters."""
    for row in rows:
        if likely_only and not _passes_likely_to_play(row, likely_threshold):
            continue

        el = row.get("element")
        if played_only:
            if el is None:
                continue
            try:
                eid = int(float(el))
            except (TypeError, ValueError):
                continue
            if minutes_by_el is None or minutes_by_el.get(eid, 0) <= 0:
                continue

        ap = row.get("actual_points")
        pr = row.get("predicted_pts")
        ep = row.get("expected_pts")
        if ap is None or pr is None or ep is None:
            continue
        try:
            a = float(ap)
            p = float(pr)
            e = float(ep)
        except (TypeError, ValueError):
            continue
        if math.isnan(a) or math.isnan(p) or math.isnan(e):
            continue
        pos = _normalize_position(row.get("position"))
        yield (a, p, e, pos)


def _collect_pairs(
    rows: list,
    minutes_by_el: dict[int, int] | None,
    played_only: bool,
    likely_only: bool,
    likely_threshold: float,
) -> tuple[list[float], list[float], list[float]]:
    y_true: list[float] = []
    y_pred_raw: list[float] = []
    y_pred_exp: list[float] = []
    for a, p, e, _ in _iter_metric_rows(
        rows, minutes_by_el, played_only, likely_only, likely_threshold
    ):
        y_true.append(a)
        y_pred_raw.append(p)
        y_pred_exp.append(e)
    return y_true, y_pred_raw, y_pred_exp


def _spearman_corr(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    if len(y_true) < MIN_SPEARMAN_N:
        return float("nan")
    c = pd.Series(y_true).corr(pd.Series(y_pred), method="spearman")
    return float(c) if c == c else float("nan")


def _precision_at_k(y_true: np.ndarray, y_pred: np.ndarray, k: int) -> float:
    """Share of top-K by prediction that also appear in top-K by actual (same position pool)."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    n = len(y_true)
    if k <= 0 or n < k:
        return float("nan")
    top_pred = set(np.argsort(-y_pred)[:k].tolist())
    top_act = set(np.argsort(-y_true)[:k].tolist())
    return len(top_pred & top_act) / k


def _print_position_strata(
    rows: list,
    minutes_by_el: dict[int, int] | None,
    played_only: bool,
    likely_only: bool,
    likely_threshold: float,
    precision_k: int,
) -> None:
    """GK/DEF/MID/FWD: Spearman(pred/exp), MAE/R² on expected_pts, Precision@K."""
    by_pos: dict[str, list[tuple[float, float, float]]] = {p: [] for p in POSITIONS}
    for a, p, e, pos in _iter_metric_rows(
        rows, minutes_by_el, played_only, likely_only, likely_threshold
    ):
        if pos is None or pos not in by_pos:
            continue
        by_pos[pos].append((a, p, e))

    print("  --- Per position (stratified) ---")
    pk = precision_k
    hdr = (
        f"  {'Pos':<4} {'n':>4}  {'Sp(pred)':>8} {'Sp(exp)':>8} "
        f"{'MAE(exp)':>9} {'R2(exp)':>8}  P@{pk}"
    )
    print(hdr)
    print("  " + "-" * 56)
    for pos in POSITIONS:
        triples = by_pos[pos]
        n = len(triples)
        if n == 0:
            print(f"  {pos:<4} {n:>4}       —        —         —        —     —")
            continue
        yt = np.array([t[0] for t in triples], dtype=float)
        yraw = np.array([t[1] for t in triples], dtype=float)
        yexp = np.array([t[2] for t in triples], dtype=float)
        rho_p = _spearman_corr(yt, yraw)
        rho_e = _spearman_corr(yt, yexp)
        mae_e = float(np.mean(np.abs(yt - yexp)))
        r2_e = r2_score(yt, yexp)
        p_at_k = _precision_at_k(yt, yexp, pk)

        def fmt_rho(x: float) -> str:
            return f"{x:8.4f}" if x == x else f"{'—':>8}"

        def fmt_pk(x: float) -> str:
            return f"{x:5.3f}" if x == x else "  —  "

        print(
            f"  {pos:<4} {n:>4}  {fmt_rho(rho_p)} {fmt_rho(rho_e)} "
            f"{mae_e:9.4f} {r2_e:8.4f}  {fmt_pk(p_at_k)}"
        )
    print()


def _print_block(name: str, yt: np.ndarray, yp: np.ndarray) -> None:
    if len(yt) == 0:
        print(f"  {name}: (no rows)")
        return
    mae = float(np.mean(np.abs(yt - yp)))
    rmse = float(np.sqrt(mean_squared_error(yt, yp)))
    r2 = r2_score(yt, yp)
    print(f"  {name}:")
    print(f"    MAE:  {mae:.4f}")
    print(f"    RMSE: {rmse:.4f}")
    print(f"    R2:   {r2:.4f}")
    print(f"    mean(actual)={float(np.mean(yt)):.3f}  mean(pred)={float(np.mean(yp)):.3f}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="MAE / R²: XGBoost predicted_pts and expected_pts vs actual_points.",
    )
    ap.add_argument("--gameweek", type=int, default=None, help="Target GW (omit = latest in dataset)")
    ap.add_argument("--season", type=str, default=None, help="e.g. 2025-26 (omit = auto)")
    ap.add_argument(
        "--played-only",
        action="store_true",
        help="Also print a third block: players with minutes > 0 in FPL live (ex-post who played).",
    )
    ap.add_argument(
        "--no-likely-block",
        action="store_true",
        help="Skip the 'likely to play only' block (default is to print it).",
    )
    ap.add_argument(
        "--precision-k",
        type=int,
        default=3,
        metavar="K",
        help="Precision@K within each position (top-K by expected_pts vs actual; default 3).",
    )
    ap.add_argument(
        "--no-position-strata",
        action="store_true",
        help="Skip per-position Spearman / MAE / R² / P@K table.",
    )
    args = ap.parse_args()

    from agents.stats_agent.stats_agent import (
        LIKELY_TO_PLAY_THRESHOLD,
        MODEL_PATH,
        run_stats_agent,
    )

    result = run_stats_agent(gameweek=args.gameweek, season=args.season)
    if result.get("error"):
        print("Agent error:", result["error"])
        sys.exit(1)

    gw = result.get("gameweek")
    season = result.get("season")
    rows = (result.get("ranked") or {}).get("ALL") or []

    minutes_by_el: dict[int, int] | None = None
    if args.played_only:
        minutes_by_el = fetch_fpl_live_minutes(int(gw))
        print(f"FPL live minutes map: {len(minutes_by_el)} players")

    print()
    print(f"XGBoost model file: {MODEL_PATH}")
    print(f"Season {season}  GW{gw}  actual_scores_source={result.get('actual_scores_source')}")
    print(f"likely_to_play threshold (matches app): {LIKELY_TO_PLAY_THRESHOLD}")
    print()

    pk = max(1, int(args.precision_k))

    def run_block(title: str, played: bool, likely: bool) -> None:
        mb = minutes_by_el if played else None
        yt, yraw, yexp = _collect_pairs(
            rows, mb, played, likely, LIKELY_TO_PLAY_THRESHOLD
        )
        yt = np.asarray(yt, dtype=float)
        yraw = np.asarray(yraw, dtype=float)
        yexp = np.asarray(yexp, dtype=float)
        print(title)
        print(f"  Rows: {len(yt)}")
        if len(yt) == 0:
            print("  (no rows)\n")
            return
        print("  Raw XGBoost (predicted_pts) vs actual:")
        _print_block("predicted_pts", yt, yraw)
        print("  Risk-adjusted (expected_pts = pred * start_prob), app xPts:")
        _print_block("expected_pts", yt, yexp)
        if not args.no_position_strata:
            _print_position_strata(
                rows, mb, played, likely, LIKELY_TO_PLAY_THRESHOLD, pk
            )
        else:
            print()

    run_block(
        "=== A) All FPL assets in model (~800) ===",
        played=False,
        likely=False,
    )

    if not args.no_likely_block:
        run_block(
            f"=== B) Likely to play only (start_prob >= {LIKELY_TO_PLAY_THRESHOLD}) -- matches app default ===",
            played=False,
            likely=True,
        )

    if args.played_only:
        run_block(
            "=== C) Played only (FPL live minutes > 0) -- who actually got minutes ===",
            played=True,
            likely=False,
        )
        run_block(
            "=== D) Likely to play AND played (minutes > 0) -- strictest ===",
            played=True,
            likely=True,
        )

    print(
        "Note: Training CV in models/xgb_history_v2_metadata.json is walk-forward on history, "
        "not identical to these live-GW snapshots.",
    )


if __name__ == "__main__":
    main()
