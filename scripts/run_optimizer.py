#!/usr/bin/env python3
"""
Run the full optimizer pipeline locally (no HTTP): FPL squad → Stats Agent → Manager + Sporting Director.

Usage (from repo root):
  python scripts/run_optimizer.py 5858754

Requires network access to fantasy.premierleague.com. If /api/manager returns 404 in the browser,
restart uvicorn so it loads the current backend/main.py (see OpenAPI at http://127.0.0.1:8006/openapi.json).
"""

from __future__ import annotations

import argparse
import json
import sys
from urllib.request import urlopen

REPO_ROOT = __file__.rsplit("scripts", 1)[0].rstrip("/\\")
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from backend.main import (  # noqa: E402
    _get_or_run_agent,
    _merge_player_form,
    _form_by_name,
    _by_element,
    _squad_for_manager_agent,
)
from agents.manager_agent import run_manager_agent  # noqa: E402
from agents.sporting_director import run_sporting_director  # noqa: E402
from agents.sporting_director.schemas import Squad, PlayerProfile  # noqa: E402


def _fetch_json(url: str) -> dict:
    with urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode())


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    p = argparse.ArgumentParser(description="Run FPL optimizer for a team ID")
    p.add_argument("team_id", type=int, help="FPL entry / team ID (from your team URL)")
    args = p.parse_args()

    base = "https://fantasy.premierleague.com/api"
    bootstrap = _fetch_json(f"{base}/bootstrap-static/")
    events = bootstrap.get("events") or []
    current = next((e for e in events if e.get("is_current")), None) or next(
        (e for e in events if e.get("is_next")), None
    )
    if not current:
        print("Could not determine current gameweek from bootstrap.", file=sys.stderr)
        return 1
    gw = int(current["id"])

    entry = _fetch_json(f"{base}/entry/{args.team_id}/")
    picks_data = _fetch_json(f"{base}/entry/{args.team_id}/event/{gw}/picks/")

    raw_ids = [p["element"] for p in picks_data.get("picks", [])]
    valid_ids = {e["id"] for e in bootstrap.get("elements", []) if e.get("status") != "u"}
    squad_ids = [i for i in raw_ids if i in valid_ids]

    if len(squad_ids) != 15:
        print(
            f"Expected 15 playable squad members; got {len(squad_ids)} "
            f"(raw picks {len(raw_ids)}). Check for unavailable players in picks.",
            file=sys.stderr,
        )
        if len(squad_ids) < 11:
            return 1

    bank_raw = (picks_data.get("entry_history") or {}).get("bank")
    bank = float(bank_raw) / 10.0 if bank_raw is not None else 0.0

    print(f"Team: {entry.get('name')} — {entry.get('player_first_name')} {entry.get('player_last_name')}")
    print(f"GW {gw} | Bank £{bank:.1f}m | {len(squad_ids)} player IDs")

    result = _get_or_run_agent(season=None, gameweek=None)
    if result.get("error"):
        print("Stats agent error:", result["error"], file=sys.stderr)
        return 1

    target_gw = result["gameweek"]
    all_ranked = result.get("ranked", {}).get("ALL", [])
    predictions = result.get("predictions", [])
    form_stats = result.get("form_stats", [])
    ranked_by = _by_element(all_ranked)
    pred_by = _by_element(predictions)
    form_by = _form_by_name(form_stats)

    squad_players: list[PlayerProfile] = []
    for pid in squad_ids:
        row = ranked_by.get(pid) or pred_by.get(pid)
        if row is None:
            print(f"  [!] No GW{target_gw} data for element {pid}", file=sys.stderr)
            continue
        merged = _merge_player_form(row, form_by)
        squad_players.append(PlayerProfile.from_ranked_player(merged))

    if len(squad_players) < 15:
        print("Not enough players resolved for manager agent.", file=sys.stderr)
        return 1

    squad = Squad(players=squad_players, bank=bank, free_transfers=1, gameweek=target_gw)

    mgr_squad = _squad_for_manager_agent(result, squad_ids)
    if len(mgr_squad) != 15:
        print("Manager squad mapping failed (need 15).", file=sys.stderr)
        return 1

    mgr = run_manager_agent(
        {
            "squad": mgr_squad,
            "gameweek": target_gw,
            "chips_available": ["triple_captain", "bench_boost"],
            "bank": bank,
            "historical_captain_xp": [],
            "historical_bench_xp": [],
        }
    )
    print("\n--- Manager ---")
    print("formation:", mgr.get("formation"), "projected:", mgr.get("projected_points"))
    print("captain:", mgr.get("captain"), "vice:", mgr.get("vice_captain"))
    if mgr.get("error"):
        print("Manager error:", mgr["error"], file=sys.stderr)

    sd = run_sporting_director(result, squad)
    print("\n--- Sporting Director ---")
    print("hold:", sd.hold_flag, "wildcard:", sd.wildcard_flag)
    print("summary:", (sd.summary or "")[:400])
    print("transfers suggested:", len(sd.recommended_transfers))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
