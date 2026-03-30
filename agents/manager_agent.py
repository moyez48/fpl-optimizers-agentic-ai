"""
manager_agent.py
================
LangGraph-powered Manager Agent for the FPL Optimizer (v2.0).

Responsibilities:
  - Validate the 15-player squad and required fields
  - Enumerate all 7 valid FPL formations, select the one maximising xP
  - Order the 4 bench players (outfield by xP desc, GK always last)
  - Assign Captain (highest xP) and Vice-Captain (second highest)
  - Recommend Triple Captain or Bench Boost using dynamic, history-based thresholds
  - Output a structured payload ready for the app layer

Graph structure:
  validate_squad
        │
  select_optimal_xi
        │
  order_bench
        │
  select_captains
        │
  [chips_evaluable?]
        ├── YES ── advise_chips
        │               │
        └── NO ─────────┤
                        v
                  format_output
                        │
                       END

Reference: agents/MANAGER_AGENT.md
"""

from __future__ import annotations

from typing import TypedDict, Optional

from langgraph.graph import StateGraph, END


# ── Constants ─────────────────────────────────────────────────────────────────

VALID_FORMATIONS = [
    (3, 4, 3),
    (3, 5, 2),
    (4, 3, 3),
    (4, 4, 2),
    (4, 5, 1),
    (5, 3, 2),
    (5, 4, 1),
]

POSITIONS = ["GK", "DEF", "MID", "FWD"]

# Dynamic threshold parameters
TC_TOP_N  = 5    # median of the 5 best captain xP values this season
BB_TOP_N  = 3    # median of the 3 best bench-total xP values this season

# Minimum floors — chip never fires below these even if threshold is low
TC_FLOOR  = 7.0   # captain xP floor for Triple Captain
BB_FLOOR  = 14.0  # bench total xP floor for Bench Boost

REQUIRED_PLAYER_FIELDS = {"id", "name", "position", "team", "xP"}
MIN_POSITION_COUNTS    = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}


# ═══════════════════════════════════════════════════════════════════════════════
# STATE DEFINITION
# Every node reads from and writes to this shared dict.
# ═══════════════════════════════════════════════════════════════════════════════

class ManagerState(TypedDict):
    # ── Inputs ────────────────────────────────────────────────────────────────
    squad:                  list        # 15 player dicts from Sporting Director
    gameweek:               int         # Current GW number
    chips_available:        list        # Unplayed chips e.g. ["triple_captain"]
    bank:                   float       # Remaining budget in £m (informational only)
    historical_captain_xp:  list        # Top captain xP per past GW (for TC threshold)
    historical_bench_xp:    list        # Total bench xP per past GW (for BB threshold)

    # ── Intermediate ──────────────────────────────────────────────────────────
    formation_scores:     dict          # {formation_str: total_xP}

    # ── Outputs ───────────────────────────────────────────────────────────────
    formation:            Optional[str]   # e.g. "4-3-3"
    starting_xi:          Optional[list]  # 11 enriched player dicts
    bench:                Optional[list]  # 4 bench players, ordered
    captain:              Optional[str]   # Captain name
    vice_captain:         Optional[str]   # Vice-Captain name
    captain_id:           Optional[int]
    vice_captain_id:      Optional[int]
    chip_recommendation:  Optional[dict]  # Chip rec dict or None
    projected_points:     Optional[float] # Sum of starting XI xP
    summary:              Optional[str]   # Human-readable decision summary

    # ── Control ───────────────────────────────────────────────────────────────
    error: Optional[str]
    log:   list


# ═══════════════════════════════════════════════════════════════════════════════
# PURE HELPERS
# Stateless functions used by the nodes.
# ═══════════════════════════════════════════════════════════════════════════════

def generate_valid_formations() -> list[tuple[int, int, int]]:
    """Return all legal FPL (def, mid, fwd) formation tuples."""
    return list(VALID_FORMATIONS)


def compute_dynamic_threshold(historical_values: list[float], top_n: int) -> float | None:
    """
    Returns the median of the top `top_n` values from `historical_values`.
    Returns None if there are fewer than `top_n` data points — threshold is
    unavailable (insufficient history, e.g. early season).
    """
    if len(historical_values) < top_n:
        return None
    sorted_desc = sorted(historical_values, reverse=True)
    top_slice   = sorted_desc[:top_n]
    mid         = len(top_slice) // 2
    if len(top_slice) % 2 == 0:
        return (top_slice[mid - 1] + top_slice[mid]) / 2
    return top_slice[mid]


def _players_by_position(squad: list[dict]) -> dict[str, list[dict]]:
    """Group squad players by position, sorted by xP descending."""
    groups: dict[str, list[dict]] = {pos: [] for pos in POSITIONS}
    for player in squad:
        pos = player["position"]
        if pos in groups:
            groups[pos].append(player)
    for pos in groups:
        groups[pos].sort(key=lambda p: p["xP"], reverse=True)
    return groups


def _score_formation(
    groups: dict[str, list[dict]],
    formation: tuple[int, int, int],
) -> tuple[float, list[dict]]:
    """
    For a given formation (n_def, n_mid, n_fwd), greedily pick the top-xP
    players per slot and return (total_xP, xi_list).
    Returns (-inf, []) if there are not enough players to fill a slot.
    """
    n_def, n_mid, n_fwd = formation
    slots = {"GK": 1, "DEF": n_def, "MID": n_mid, "FWD": n_fwd}
    xi: list[dict] = []
    total = 0.0
    for pos, count in slots.items():
        available = groups[pos]
        if len(available) < count:
            return float("-inf"), []
        chosen = available[:count]
        xi.extend(chosen)
        total += sum(p["xP"] for p in chosen)
    return total, xi


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 1 — validate_squad
# Sanity-check the incoming squad before optimisation begins.
# ═══════════════════════════════════════════════════════════════════════════════

def validate_squad(state: ManagerState) -> ManagerState:
    log = state.get("log", [])
    try:
        squad = state.get("squad", [])

        if len(squad) != 15:
            return {
                **state,
                "error": f"validate_squad: squad must have exactly 15 players, got {len(squad)}",
                "log": log,
            }

        for i, player in enumerate(squad):
            missing = REQUIRED_PLAYER_FIELDS - set(player.keys())
            if missing:
                return {
                    **state,
                    "error": (
                        f"validate_squad: player at index {i} "
                        f"({player.get('name', '?')}) is missing required fields: {missing}"
                    ),
                    "log": log,
                }
            if player["position"] not in POSITIONS:
                return {
                    **state,
                    "error": (
                        f"validate_squad: player {player['name']} has invalid position "
                        f"'{player['position']}' — must be one of {POSITIONS}"
                    ),
                    "log": log,
                }

        pos_counts = {pos: 0 for pos in POSITIONS}
        for player in squad:
            pos_counts[player["position"]] += 1

        for pos, minimum in MIN_POSITION_COUNTS.items():
            if pos_counts[pos] < minimum:
                return {
                    **state,
                    "error": (
                        f"validate_squad: need at least {minimum} {pos} players, "
                        f"got {pos_counts[pos]}"
                    ),
                    "log": log,
                }

        log.append(
            f"validate_squad: 15 players validated "
            f"({pos_counts['GK']} GK, {pos_counts['DEF']} DEF, "
            f"{pos_counts['MID']} MID, {pos_counts['FWD']} FWD)"
        )

    except Exception as e:
        return {**state, "error": f"validate_squad: {e}", "log": log}

    return {**state, "log": log}


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 2 — select_optimal_xi
# Enumerate all 7 legal FPL formations, greedily pick the best XI by xP.
# ═══════════════════════════════════════════════════════════════════════════════

def select_optimal_xi(state: ManagerState) -> ManagerState:
    log = state.get("log", [])
    if state.get("error"):
        return state

    try:
        squad  = state["squad"]
        groups = _players_by_position(squad)

        best_score      = float("-inf")
        best_xi:   list[dict] = []
        best_formation  = ""
        formation_scores: dict[str, float] = {}

        for formation in VALID_FORMATIONS:
            score, xi     = _score_formation(groups, formation)
            formation_str = f"{formation[0]}-{formation[1]}-{formation[2]}"
            formation_scores[formation_str] = round(score, 3) if score != float("-inf") else None
            if score > best_score:
                best_score     = score
                best_xi        = xi
                best_formation = formation_str

        if not best_xi:
            return {
                **state,
                "error": "select_optimal_xi: could not build a valid Starting XI "
                         "from the provided squad — check position counts",
                "log": log,
            }

        xi_ids = {p["id"] for p in best_xi}
        bench  = [p for p in squad if p["id"] not in xi_ids]

        log.append(
            f"select_optimal_xi: best formation {best_formation} "
            f"({round(best_score, 2)} xP) out of {len(VALID_FORMATIONS)} evaluated"
        )

    except Exception as e:
        return {**state, "error": f"select_optimal_xi: {e}", "log": log}

    return {
        **state,
        "formation":        best_formation,
        "starting_xi":      best_xi,
        "bench":            bench,
        "formation_scores": formation_scores,
        "log":              log,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 3 — order_bench
# Assign bench priority slots (1–4): outfield by xP desc, GK always last.
# ═══════════════════════════════════════════════════════════════════════════════

def order_bench(state: ManagerState) -> ManagerState:
    log = state.get("log", [])
    if state.get("error"):
        return state

    try:
        bench = [dict(p) for p in state["bench"]]

        gk_bench       = [p for p in bench if p["position"] == "GK"]
        outfield_bench = [p for p in bench if p["position"] != "GK"]
        outfield_bench.sort(key=lambda p: p["xP"], reverse=True)

        ordered = outfield_bench + gk_bench
        for i, player in enumerate(ordered, start=1):
            player["bench_order"] = i

        log.append(
            "order_bench: bench ordered by xP desc, GK placed in slot 4 — "
            + ", ".join(
                f"{p['name']} ({p['position']}, slot {p['bench_order']})"
                for p in ordered
            )
        )

    except Exception as e:
        return {**state, "error": f"order_bench: {e}", "log": log}

    return {**state, "bench": ordered, "log": log}


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 4 — select_captains
# Captain = highest xP in Starting XI; Vice-Captain = second highest.
# Tiebreak: lower player id wins (deterministic).
# ═══════════════════════════════════════════════════════════════════════════════

def select_captains(state: ManagerState) -> ManagerState:
    log = state.get("log", [])
    if state.get("error"):
        return state

    try:
        starting_xi = [dict(p) for p in state["starting_xi"]]
        sorted_xi   = sorted(starting_xi, key=lambda p: (-p["xP"], p["id"]))

        captain      = sorted_xi[0]
        vice_captain = sorted_xi[1]

        for player in starting_xi:
            player["is_captain"]      = player["id"] == captain["id"]
            player["is_vice_captain"] = player["id"] == vice_captain["id"]

        log.append(
            f"select_captains: captain={captain['name']} ({captain['xP']:.2f} xP), "
            f"vc={vice_captain['name']} ({vice_captain['xP']:.2f} xP)"
        )

    except Exception as e:
        return {**state, "error": f"select_captains: {e}", "log": log}

    return {
        **state,
        "starting_xi":      starting_xi,
        "captain":          captain["name"],
        "vice_captain":     vice_captain["name"],
        "captain_id":       captain["id"],
        "vice_captain_id":  vice_captain["id"],
        "log":              log,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 5 — advise_chips  (only reached when TC or BB is available)
#
# Both chips are evaluated independently. Each produces a confidence score:
#   confidence = min(current_value / (effective_threshold × 1.3), 1.0)
#
# The chip with the higher confidence is recommended. If tied, TC wins because
# it is a guaranteed 3× on a known player — more predictable than bench points.
# If neither chip meets its effective threshold, no chip is recommended.
#
# Dynamic threshold = median of top-N historical xP values.
# Effective threshold = max(dynamic_threshold, floor).
# ═══════════════════════════════════════════════════════════════════════════════

def advise_chips(state: ManagerState) -> ManagerState:
    log = state.get("log", [])
    if state.get("error"):
        return state

    try:
        chips_available     = state.get("chips_available", [])
        historical_cap_xp   = state.get("historical_captain_xp", [])
        historical_bench_xp = state.get("historical_bench_xp", [])

        starting_xi  = state["starting_xi"]
        bench        = state["bench"]

        captain      = next((p for p in starting_xi if p.get("is_captain")), None)
        captain_xp   = captain["xP"] if captain else 0.0
        bench_total  = sum(p["xP"] for p in bench)

        # Evaluate each chip independently — store (confidence, rec_dict) or None
        tc_result = None
        bb_result = None

        # ── Triple Captain ─────────────────────────────────────────────────────
        if "triple_captain" in chips_available:
            tc_dyn = compute_dynamic_threshold(historical_cap_xp, TC_TOP_N)
            if tc_dyn is None:
                log.append(
                    f"advise_chips: Insufficient historical data "
                    f"({len(historical_cap_xp)} of {TC_TOP_N} GWs needed) "
                    f"— Triple Captain threshold unavailable. Skipping TC evaluation."
                )
            else:
                tc_threshold = max(tc_dyn, TC_FLOOR)
                log.append(
                    f"advise_chips: TC threshold={tc_threshold:.1f} "
                    f"(dynamic={tc_dyn:.1f}, floor={TC_FLOOR}), captain xP={captain_xp:.1f}"
                )
                if captain_xp >= tc_threshold:
                    conf = round(min(captain_xp / (tc_threshold * 1.3), 1.0), 2)
                    tc_result = (conf, {
                        "chip":       "triple_captain",
                        "confidence": conf,
                        "reasoning":  (
                            f"Captain projects {captain_xp:.1f} xP vs TC threshold "
                            f"{tc_threshold:.1f} (dynamic={tc_dyn:.1f}, floor={TC_FLOOR}). "
                            f"Confidence {conf:.0%}."
                        ),
                    })
                    log.append(f"advise_chips: TC qualifies (conf={conf}).")
                else:
                    log.append(
                        f"advise_chips: TC does not qualify — captain xP {captain_xp:.1f} "
                        f"< threshold {tc_threshold:.1f}."
                    )

        # ── Bench Boost ────────────────────────────────────────────────────────
        if "bench_boost" in chips_available:
            bb_dyn = compute_dynamic_threshold(historical_bench_xp, BB_TOP_N)
            if bb_dyn is None:
                log.append(
                    f"advise_chips: Insufficient historical data "
                    f"({len(historical_bench_xp)} of {BB_TOP_N} GWs needed) "
                    f"— Bench Boost threshold unavailable. Skipping BB evaluation."
                )
            else:
                bb_threshold = max(bb_dyn, BB_FLOOR)
                log.append(
                    f"advise_chips: BB threshold={bb_threshold:.1f} "
                    f"(dynamic={bb_dyn:.1f}, floor={BB_FLOOR}), bench total xP={bench_total:.1f}"
                )
                if bench_total >= bb_threshold:
                    conf = round(min(bench_total / (bb_threshold * 1.3), 1.0), 2)
                    bb_result = (conf, {
                        "chip":       "bench_boost",
                        "confidence": conf,
                        "reasoning":  (
                            f"Bench projects {bench_total:.1f} total xP vs BB threshold "
                            f"{bb_threshold:.1f} (dynamic={bb_dyn:.1f}, floor={BB_FLOOR}). "
                            f"Confidence {conf:.0%}."
                        ),
                    })
                    log.append(f"advise_chips: BB qualifies (conf={conf}).")
                else:
                    log.append(
                        f"advise_chips: BB does not qualify — bench total {bench_total:.1f} "
                        f"< threshold {bb_threshold:.1f}."
                    )

        # ── Compare and pick winner ────────────────────────────────────────────
        chip_rec = None

        if tc_result and bb_result:
            tc_conf, tc_rec = tc_result
            bb_conf, bb_rec = bb_result
            if tc_conf >= bb_conf:
                chip_rec = tc_rec
                log.append(
                    f"advise_chips: Both chips qualify — TC conf={tc_conf} >= BB conf={bb_conf}. "
                    f"Recommending triple_captain."
                )
            else:
                chip_rec = bb_rec
                log.append(
                    f"advise_chips: Both chips qualify — BB conf={bb_conf} > TC conf={tc_conf}. "
                    f"Recommending bench_boost."
                )
        elif tc_result:
            chip_rec = tc_result[1]
            log.append("advise_chips: Only TC qualifies — recommending triple_captain.")
        elif bb_result:
            chip_rec = bb_result[1]
            log.append("advise_chips: Only BB qualifies — recommending bench_boost.")
        else:
            log.append("advise_chips: No chip threshold met — chip_recommendation=None.")

    except Exception as e:
        return {**state, "error": f"advise_chips: {e}", "log": log}

    return {**state, "chip_recommendation": chip_rec, "log": log}


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 6 — format_output
# Assemble the final payload and human-readable summary.
# ═══════════════════════════════════════════════════════════════════════════════

def format_output(state: ManagerState) -> ManagerState:
    log = state.get("log", [])
    if state.get("error"):
        return state

    try:
        def _fmt_xi(player: dict) -> dict:
            return {
                "id":              player["id"],
                "name":            player["name"],
                "position":        player["position"],
                "team":            player.get("team", ""),
                "xP":              round(float(player["xP"]), 2),
                "is_captain":      player.get("is_captain", False),
                "is_vice_captain": player.get("is_vice_captain", False),
            }

        def _fmt_bench(player: dict) -> dict:
            return {
                "id":          player["id"],
                "name":        player["name"],
                "position":    player["position"],
                "bench_order": player["bench_order"],
                "xP":          round(float(player["xP"]), 2),
            }

        starting_xi      = [_fmt_xi(p) for p in state["starting_xi"]]
        bench            = [_fmt_bench(p) for p in state["bench"]]
        projected_points = round(sum(p["xP"] for p in starting_xi), 1)

        cap_xp = next((p["xP"] for p in starting_xi if p["is_captain"]), 0.0)
        vc_xp  = next((p["xP"] for p in starting_xi if p["is_vice_captain"]), 0.0)

        chip_str = "None"
        chip_rec = state.get("chip_recommendation")
        if chip_rec:
            chip_str = f"{chip_rec['chip']} (conf {chip_rec['confidence']:.2f})"

        summary = (
            f"GW{state['gameweek']} | Formation: {state['formation']} | "
            f"Captain: {state['captain']} ({cap_xp:.1f} xP) | "
            f"VC: {state['vice_captain']} ({vc_xp:.1f} xP) | "
            f"Chip: {chip_str} | "
            f"Projected: {projected_points} pts"
        )

        log.append(
            f"format_output: Manager Agent complete for GW{state['gameweek']} "
            f"— formation={state['formation']}, "
            f"projected={projected_points} xP, "
            f"captain={state['captain']}"
        )

    except Exception as e:
        return {**state, "error": f"format_output: {e}", "log": log}

    return {
        **state,
        "starting_xi":      starting_xi,
        "bench":            bench,
        "projected_points": projected_points,
        "summary":          summary,
        "log":              log,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# GRAPH ASSEMBLY
# ═══════════════════════════════════════════════════════════════════════════════

def should_evaluate_chips(state: ManagerState) -> str:
    """
    Route to advise_chips only if the user has Triple Captain or Bench Boost.
    Free Hit and Wildcard are transfer chips — the Manager ignores them.
    """
    relevant = {"triple_captain", "bench_boost"}
    if relevant.intersection(set(state.get("chips_available", []))):
        return "advise_chips"
    return "format_output"


def build_manager_agent():
    """
    Construct and compile the Manager Agent graph.

    Nodes (execution order):
        validate_squad    → validate 15-player squad
        select_optimal_xi → formation enumeration + best XI selection (by xP)
        order_bench       → bench priority (outfield xP desc, GK last)
        select_captains   → captain = highest xP, vc = second highest
        advise_chips      → dynamic threshold chip evaluation (skipped if no TC/BB)
        format_output     → final payload + summary assembly
    """
    workflow = StateGraph(ManagerState)

    # ── Register nodes ────────────────────────────────────────────────────────
    workflow.add_node("validate_squad",    validate_squad)
    workflow.add_node("select_optimal_xi", select_optimal_xi)
    workflow.add_node("order_bench",       order_bench)
    workflow.add_node("select_captains",   select_captains)
    workflow.add_node("advise_chips",      advise_chips)
    workflow.add_node("format_output",     format_output)

    # ── Entry point ───────────────────────────────────────────────────────────
    workflow.set_entry_point("validate_squad")

    # ── Edges ─────────────────────────────────────────────────────────────────
    workflow.add_conditional_edges(
        "validate_squad",
        lambda state: "select_optimal_xi" if state.get("error") is None else END,
    )

    workflow.add_conditional_edges(
        "select_optimal_xi",
        lambda state: "order_bench" if state.get("error") is None else END,
    )

    workflow.add_edge("order_bench", "select_captains")

    workflow.add_conditional_edges(
        "select_captains",
        should_evaluate_chips,
    )

    workflow.add_edge("advise_chips",  "format_output")
    workflow.add_edge("format_output", END)

    return workflow.compile()


# Compiled agent — import this in other modules
manager_agent = build_manager_agent()


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def run_manager_agent(input_data: dict) -> dict:
    """
    Run the Manager Agent for a given gameweek.

    Args:
        input_data: dict with keys:
            squad                  — list of 15 player dicts (id, name, position,
                                     team, price, xP, xP_5gw)
            gameweek               — int, current GW number
            chips_available        — list[str], unplayed chips
            bank                   — float, remaining budget in £m
            historical_captain_xp  — list[float], past top-captain xP per GW
            historical_bench_xp    — list[float], past bench-total xP per GW

    Returns:
        Final ManagerState dict with starting_xi, bench, captain, vice_captain,
        captain_id, vice_captain_id, chip_recommendation, projected_points, summary.

    Example:
        from agents.manager_agent import run_manager_agent
        result = run_manager_agent(input_data)
        print(result["formation"])            # "4-3-3"
        print(result["captain"])              # "M.Salah"
        print(result["projected_points"])     # 61.3
        print(result["chip_recommendation"])  # dict or None
    """
    initial_state: ManagerState = {
        "squad":                 input_data["squad"],
        "gameweek":              input_data["gameweek"],
        "chips_available":       input_data.get("chips_available", []),
        "bank":                  input_data.get("bank", 0.0),
        "historical_captain_xp": input_data.get("historical_captain_xp", []),
        "historical_bench_xp":   input_data.get("historical_bench_xp", []),
        "formation_scores":      {},
        "formation":             None,
        "starting_xi":           None,
        "bench":                 None,
        "captain":               None,
        "vice_captain":          None,
        "captain_id":            None,
        "vice_captain_id":       None,
        "chip_recommendation":   None,
        "projected_points":      None,
        "summary":               None,
        "error":                 None,
        "log":                   [],
    }
    return manager_agent.invoke(initial_state)


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Minimal test squad — 2 GK, 5 DEF, 5 MID, 3 FWD
    TEST_SQUAD = [
        {"id": 1,  "name": "Raya",             "position": "GK",  "team": "ARS", "price": 5.5,  "xP": 5.2,  "xP_5gw": 24.1},
        {"id": 2,  "name": "Flekken",          "position": "GK",  "team": "BRE", "price": 4.5,  "xP": 3.1,  "xP_5gw": 14.2},
        {"id": 3,  "name": "Alexander-Arnold", "position": "DEF", "team": "LIV", "price": 7.2,  "xP": 6.4,  "xP_5gw": 29.3},
        {"id": 4,  "name": "Pedro Porro",      "position": "DEF", "team": "TOT", "price": 5.8,  "xP": 5.1,  "xP_5gw": 22.4},
        {"id": 5,  "name": "Mykolenko",        "position": "DEF", "team": "EVE", "price": 4.5,  "xP": 2.8,  "xP_5gw": 12.3},
        {"id": 6,  "name": "Dunk",             "position": "DEF", "team": "BRI", "price": 4.6,  "xP": 3.2,  "xP_5gw": 14.8},
        {"id": 7,  "name": "Saliba",           "position": "DEF", "team": "ARS", "price": 5.9,  "xP": 5.6,  "xP_5gw": 25.9},
        {"id": 8,  "name": "Salah",            "position": "MID", "team": "LIV", "price": 13.2, "xP": 9.1,  "xP_5gw": 41.2},
        {"id": 9,  "name": "Saka",             "position": "MID", "team": "ARS", "price": 10.0, "xP": 7.3,  "xP_5gw": 33.1},
        {"id": 10, "name": "Palmer",           "position": "MID", "team": "CHE", "price": 11.2, "xP": 7.8,  "xP_5gw": 35.4},
        {"id": 11, "name": "Andreas",          "position": "MID", "team": "FUL", "price": 5.5,  "xP": 4.1,  "xP_5gw": 18.7},
        {"id": 12, "name": "Mbeumo",           "position": "MID", "team": "BRE", "price": 8.0,  "xP": 6.2,  "xP_5gw": 28.1},
        {"id": 13, "name": "Haaland",          "position": "FWD", "team": "MCI", "price": 14.5, "xP": 8.6,  "xP_5gw": 38.9},
        {"id": 14, "name": "Watkins",          "position": "FWD", "team": "AVL", "price": 9.1,  "xP": 6.1,  "xP_5gw": 27.3},
        {"id": 15, "name": "Wood",             "position": "FWD", "team": "NEW", "price": 6.5,  "xP": 5.0,  "xP_5gw": 22.4},
    ]

    result = run_manager_agent({
        "squad":                TEST_SQUAD,
        "gameweek":             35,
        "chips_available":      ["triple_captain", "bench_boost"],
        "bank":                 0.5,
        "historical_captain_xp": [7.2, 9.1, 6.5, 11.0, 8.3, 7.8, 10.2, 6.9],
        "historical_bench_xp":   [12.4, 15.1, 9.8, 20.3, 11.7, 14.0, 18.5, 10.2],
    })

    if result["error"]:
        print(f"\nERROR: {result['error']}")
    else:
        print(f"\n{'='*60}")
        print(f"Manager Agent — GW{result['gameweek']} Results")
        print(f"{'='*60}")

        print("\nExecution log:")
        for entry in result["log"]:
            print(f"  * {entry}")

        print(f"\nFormation: {result['formation']}")
        print(f"Projected points: {result['projected_points']}")

        print(f"\nStarting XI:")
        for p in result["starting_xi"]:
            flags = ""
            if p["is_captain"]:      flags += " [C]"
            if p["is_vice_captain"]: flags += " [V]"
            print(f"  {p['position']:<4}  {p['name']:<25}  xP={p['xP']:.2f}{flags}")

        print(f"\nBench:")
        for p in result["bench"]:
            print(f"  {p['bench_order']}. {p['name']:<25}  {p['position']:<4}  xP={p['xP']:.2f}")

        print(f"\nCaptain:      {result['captain']} (id={result['captain_id']})")
        print(f"Vice-Captain: {result['vice_captain']} (id={result['vice_captain_id']})")

        if result["chip_recommendation"]:
            rec = result["chip_recommendation"]
            print(f"\nChip recommendation: {rec['chip'].upper()} "
                  f"(confidence={rec['confidence']:.0%})")
            print(f"  {rec['reasoning']}")
        else:
            print("\nChip recommendation: None")

        print(f"\nSummary: {result['summary']}")
1