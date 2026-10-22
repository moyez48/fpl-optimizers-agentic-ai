"""
predict_gw8.py
==============
GW8 predictions + recommended XI from the retrained model.

Mirrors the Stats Agent path (agents/stats_agent/stats_agent.py):
load processed CSV → build the feature matrix from raw stats
(scripts/fpl_matrix.build_feature_matrix — the same
add_base_rolling_features + MasterFPLFeatureEngineer + alias/interaction
block the agent and training use) → load models/xgb_history_v2.pkl +
feature list from models/xgb_history_v2_metadata.json → predict on the
2026-27 GW8 planning-GW rows → fillna(0), exactly as run_model does.

Availability comes from the LIVE bootstrap-static at run time:
players flagged out (status i/s/u/n or 0% chance next round) are excluded
from the XI pool; doubtful players may be picked but are flagged, with
the next-best fully-available alternative named for each.

XI selection is exact: for every legal formation (DEF 3-5, MID 2-5,
FWD 1-3), a small integer program (scipy.optimize.milp) maximises total
predicted points subject to ≤3 players per team. The best formation wins.

Outputs (to ~/workspace/fpl-work/):
  gw8_predictions_ranked.csv  — every predicted player, ranked
  gw8_recommended_xi.md       — the XI, captain/vice, totals, flags

Run from repo root:
    python scripts/predict_gw8.py
"""

from __future__ import annotations

import json
import os
import pickle
import sys

import numpy as np
import pandas as pd
import requests
from scipy.optimize import Bounds, LinearConstraint, milp

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from fpl_matrix import build_feature_matrix  # noqa: E402

SEASON = "2026-27"
TARGET_GW = 8
OUT_DIR = os.path.expanduser("~/workspace/fpl-work")
BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"

OUT_STATUSES = {"i", "s", "u", "n"}


def main() -> None:
    os.chdir(REPO_ROOT)

    # ── Live bootstrap (availability, prices, display names) ─────────────
    bs = requests.get(BOOTSTRAP_URL, timeout=45).json()
    teams = {int(t["id"]): t["name"] for t in bs["teams"]}
    pos_map = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
    el = pd.DataFrame(bs["elements"])
    el_info = pd.DataFrame({
        "element": el["id"].astype(int),
        "player": el["first_name"] + " " + el["second_name"],
        "web_name": el["web_name"],
        "team_live": el["team"].map(teams),
        "price": el["now_cost"] / 10.0,
        "status": el["status"],
        "chance_next": el["chance_of_playing_next_round"],
        "chance_this": el["chance_of_playing_this_round"],
        "news": el["news"].fillna(""),
        "ep_next_live": pd.to_numeric(el["ep_next"], errors="coerce"),
    })

    # ── Feature matrix + predictions ──────────────────────────────────────
    raw = pd.read_csv(os.path.join(REPO_ROOT, "data", "processed_fpl_data.csv"),
                      low_memory=False)
    matrix, _ = build_feature_matrix(raw)

    with open(os.path.join(REPO_ROOT, "models", "xgb_history_v2_metadata.json")) as f:
        features = json.load(f)["training"]["features"]
    with open(os.path.join(REPO_ROOT, "models", "xgb_history_v2.pkl"), "rb") as f:
        model = pickle.load(f)

    pred_df = matrix[(matrix["season"] == SEASON) & (matrix["GW"] == TARGET_GW)].copy()
    assert len(pred_df) > 500, f"Only {len(pred_df)} GW{TARGET_GW} rows — ingest missing?"
    pred_df["predicted_pts"] = model.predict(pred_df[features].fillna(0))
    pred_df["element"] = pd.to_numeric(pred_df["element"], errors="coerce").astype(int)

    # The CSV carries its own (stale) status/news snapshot columns — drop
    # them so the LIVE bootstrap values win the merge.
    pred_df = pred_df.drop(columns=[c for c in ("status", "news")
                                    if c in pred_df.columns])
    out = pred_df.merge(el_info, on="element", how="left")
    out = out.sort_values("predicted_pts", ascending=False).reset_index(drop=True)
    out.insert(0, "rank", range(1, len(out) + 1))

    ranked_cols = ["rank", "player", "web_name", "team_live", "position",
                   "price", "predicted_pts", "ep_next_live", "status",
                   "chance_next", "news", "element", "name"]
    ranked = out[ranked_cols].rename(columns={"team_live": "team", "name": "dataset_name"})
    ranked["predicted_pts"] = ranked["predicted_pts"].round(3)
    ranked_path = os.path.join(OUT_DIR, "gw8_predictions_ranked.csv")
    ranked.to_csv(ranked_path, index=False)
    print(f"Wrote {ranked_path} ({len(ranked)} players)")

    # ── XI selection ──────────────────────────────────────────────────────
    pool = out.copy()
    pool["chance_next"] = pd.to_numeric(pool["chance_next"], errors="coerce")
    pool["unavailable"] = (
        pool["status"].isin(OUT_STATUSES) | (pool["chance_next"] == 0)
    )
    pool["doubtful"] = (
        ~pool["unavailable"]
        & ((pool["status"] == "d") | (pool["chance_next"].notna() & (pool["chance_next"] < 100)))
    )
    elig = pool[~pool["unavailable"]].reset_index(drop=True)
    print(f"XI pool: {len(elig)} available/eligible of {len(pool)} predicted "
          f"({int(pool['unavailable'].sum())} flagged out)")

    team_ids = elig["team_live"].astype("category")
    T = team_ids.cat.categories
    A_team = np.zeros((len(T), len(elig)))
    for j, t in enumerate(team_ids):
        A_team[list(T).index(t), j] = 1.0
    pos_arr = elig["position"].values
    c = -elig["predicted_pts"].values  # minimise negative = maximise points

    formations = [
        (d, m, f) for d in range(3, 6) for m in range(2, 6) for f in range(1, 4)
        if d + m + f == 10
    ]
    best = None
    for (d, m, f) in formations:
        A_pos = np.zeros((3, len(elig)))
        for j, p in enumerate(pos_arr):
            if p == "DEF":
                A_pos[0, j] = 1
            elif p == "MID":
                A_pos[1, j] = 1
            elif p == "FWD":
                A_pos[2, j] = 1
        A_gk = (pos_arr == "GK").astype(float).reshape(1, -1)
        A = np.vstack([A_gk, A_pos, A_team])
        lb = np.concatenate([[1, d, m, f], np.zeros(len(T))])
        ub = np.concatenate([[1, d, m, f], np.full(len(T), 3.0)])
        res = milp(c, integrality=np.ones(len(elig)),
                   bounds=Bounds(0, 1),
                   constraints=LinearConstraint(A, lb, ub))
        if res.success and (best is None or -res.fun > best[0]):
            best = (-res.fun, (d, m, f), np.where(res.x > 0.5)[0])

    assert best is not None, "No feasible XI found"
    total_pred, (d, m, f), idx = best
    xi = elig.iloc[idx].copy()
    xi = xi.assign(_ord=xi["position"].map({"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}))
    xi = xi.sort_values(["_ord", "predicted_pts"], ascending=[True, False])
    total_cost = float(xi["price"].sum())

    # Captain = top predicted; vice = next. Flag if captain doubtful.
    xi_sorted = xi.sort_values("predicted_pts", ascending=False)
    captain = xi_sorted.iloc[0]
    vice = xi_sorted.iloc[1]

    def alternative(row) -> str:
        """Next-best fully-available, not-doubtful player at same position."""
        cand = elig[
            (elig["position"] == row["position"])
            & (~elig["unavailable"]) & (~elig["doubtful"])
            & (~elig["element"].isin(xi["element"]))
        ].sort_values("predicted_pts", ascending=False)
        if cand.empty:
            return "—"
        a = cand.iloc[0]
        return (f"{a['player']} ({a['team_live']}, £{a['price']:.1f}m, "
                f"{a['predicted_pts']:.2f} pts)")

    lines = []
    lines.append(f"# GW8 recommended XI — 2026-27 (model: retrained xgb_history_v2)")
    lines.append("")
    lines.append(f"Formation: **{d}-{m}-{f}**  |  XI predicted points: "
                 f"**{total_pred:.2f}** ({total_pred + captain['predicted_pts']:.2f} "
                 f"with captain doubled)  |  XI cost: **£{total_cost:.1f}m**")
    lines.append("")
    lines.append("| Pos | Player | Team | Price | Pred pts | Flag |")
    lines.append("|-----|--------|------|-------|----------|------|")
    for _, r in xi.iterrows():
        tag = ""
        if r["element"] == captain["element"]:
            tag = " **(C)**"
        elif r["element"] == vice["element"]:
            tag = " **(VC)**"
        flag = ""
        if r["doubtful"]:
            flag = (f"⚠️ doubtful — status {r['status']}, "
                    f"chance next round {r['chance_next'] if pd.notna(r['chance_next']) else '—'}%"
                    + (f" ({r['news']})" if r["news"] else ""))
        lines.append(f"| {r['position']} | {r['player']}{tag} | {r['team_live']} | "
                     f"£{r['price']:.1f}m | {r['predicted_pts']:.2f} | {flag} |")
    lines.append("")
    lines.append(f"**Captain:** {captain['player']} ({captain['team_live']}) — "
                 f"{captain['predicted_pts']:.2f} predicted pts"
                 + (" ⚠️ DOUBTFUL, see below" if captain["doubtful"] else ""))
    lines.append(f"**Vice-captain:** {vice['player']} ({vice['team_live']}) — "
                 f"{vice['predicted_pts']:.2f} predicted pts"
                 + (" ⚠️ doubtful" if vice["doubtful"] else ""))
    doubtful_xi = xi[xi["doubtful"]]
    if len(doubtful_xi):
        lines.append("")
        lines.append("**Doubtful picks and next-best alternatives:**")
        for _, r in doubtful_xi.iterrows():
            lines.append(f"- {r['player']} ({r['position']}, {r['team_live']}, "
                         f"{r['predicted_pts']:.2f} pts) → alternative: {alternative(r)}")
    report = "\n".join(lines) + "\n"
    xi_path = os.path.join(OUT_DIR, "gw8_recommended_xi.md")
    with open(xi_path, "w") as fh:
        fh.write(report)
    print(f"Wrote {xi_path}")
    print(report)


if __name__ == "__main__":
    main()
