# Manager Agent (The Tactician) — Merged LangGraph Specification

> **Version:** 2.0 (Merged)
> **Date:** 2026-03-23
> **Status:** Draft — Pending Team Review
> **Merge Notes:** Combines decisions from both partners' v1 specs. Each node documents whose design was adopted and why.

---

## 1. Agent Purpose

The Manager Agent is the **tactician** of the FPL Optimizer system. It receives player-level Expected Points (xP) projections from the Statistician Agent and the user's current 15-man squad, then outputs the mathematically optimal Starting XI, bench order, captain/vice-captain picks, and chip-usage recommendations.

It does **not** fetch data, train models, recommend transfers, or call any external APIs. Its sole responsibility is: _given a fixed squad of 15 players and their projections, produce the highest-scoring legal lineup._

---

## 2. Scope Boundaries

### In Scope

- Selecting the best legal Starting XI from the user's 15-player squad.
- Enforcing all FPL formation and position rules.
- Ordering the 4 bench players by projected value (auto-sub priority), GK always last.
- Selecting a Captain (2× points) and Vice-Captain (backup 2×).
- Recommending chip activation when conditions are met (Triple Captain, Bench Boost), using **dynamic thresholds** derived from historical xP data.

### Out of Scope (Handled by Other Agents)

| Responsibility | Owner |
|---|---|
| Fetching live/historical data, training ML models, generating xP projections | Statistician Agent |
| Transfer recommendations, budget management, VORP calculations | Sporting Director Agent |
| Routing user intent, orchestrating multi-agent workflows | Orchestrator Agent (deferred) |

### Explicitly Excluded (Avoid Over-Engineering)

- Live weather or injury scraping.
- Multi-gameweek planning — this agent optimizes for the **upcoming single gameweek**.
- Opponent formation analysis or tactical simulations.
- `minutes_risk` adjustments — **decided against** in the merge. The Stats Agent's raw `xP` is the single source of truth for player value. Adding a second risk-discount layer inside the Manager would be double-counting uncertainty that the Stats Agent's model already captures.
- Differential/risk-tolerance profiles — keep v1 as pure expected-value maximization.

---

## 3. Merge Decisions Log

| Node | Source | Rationale |
|---|---|---|
| `validate_squad` | Original spec (mine) | Straightforward gate — both specs were nearly identical here |
| `compute_adjusted_xp` | **Removed entirely** | We agreed not to use `minutes_risk`. All downstream logic uses raw `xP` from the Stats Agent. This removes a node and simplifies the graph. |
| `select_optimal_xi` | **Partner's spec** | Cleaner loop structure with the `is_formation_valid?` conditional re-entry, greedy top-N per slot, and `-inf` scoring for impossible formations. Uses 7 legal formations (partner's list). |
| `order_bench` | **Partner's spec** | GK always placed in bench slot 4 (last). FPL auto-sub rules can only sub a bench GK for the starting GK, which almost never happens — placing them last avoids wasting high-value bench slots on a near-zero-probability event. |
| `select_captains` | **Either (functionally identical)** | Both specs select captain = highest xP, vice-captain = second highest from the Starting XI. |
| `advise_chips` | **My spec, with dynamic thresholds** | Replaced fixed thresholds with a median-based dynamic threshold computed from historical top-xP data. Added edge case handling for when the threshold is never reached. |
| `compile_summary` / `format_output` | Combined | Partner's `format_output` structure (JSON payload with `log` array and `error` field) plus my `compile_summary` human-readable output. |

---

## 4. LangGraph State Definition

```python
from typing import TypedDict, Optional
from langgraph.graph import StateGraph

class ManagerState(TypedDict):
    # ── INPUTS (populated before the graph runs) ──────────────────
    squad: list[dict]
    # List of 15 player dicts. Each dict contains:
    #   - id: int               (FPL element ID)
    #   - name: str
    #   - position: str         ("GK", "DEF", "MID", "FWD")
    #   - team: str             (Club short name)
    #   - price: float          (Price in £m)
    #   - xP: float             (Expected points from Stats Agent — single source of truth)
    #   - xP_5gw: float         (5-GW cumulative xP, passed through for Sporting Director)

    chips_available: list[str]
    # Chips the user still has. Possible values:
    #   "triple_captain", "bench_boost", "free_hit", "wildcard"

    gameweek: int
    # The upcoming gameweek number (1-38).

    bank: float
    # Remaining budget in £m (informational only — Manager does not make transfers).

    historical_captain_xp: list[float]
    # Historical record of the top-xP player's score per gameweek (for dynamic
    # Triple Captain threshold). Populated by the Statistician or Orchestrator.
    # Example: [7.2, 9.1, 6.5, 11.0, 8.3, ...] — one value per past GW.

    historical_bench_xp: list[float]
    # Historical record of the sum of bench xP per gameweek (for dynamic
    # Bench Boost threshold). Populated similarly.
    # Example: [12.4, 15.1, 9.8, 20.3, ...] — one value per past GW.

    # ── INTERMEDIATE ──────────────────────────────────────────────
    formation_scores: dict
    # {formation_str: total_xP} — all 7 formations scored. Populated by select_optimal_xi.

    # ── OUTPUTS ───────────────────────────────────────────────────
    formation: str
    # e.g. "4-3-3"

    starting_xi: list[dict]
    # 11 enriched player dicts.

    bench: list[dict]
    # 4 bench players, ordered (outfield by xP desc, GK always slot 4).

    captain: str
    # Captain player name.

    vice_captain: str
    # Vice-Captain player name.

    captain_id: int
    vice_captain_id: int

    chip_recommendation: Optional[dict]
    # {"chip": str, "confidence": float, "reasoning": str} or None.

    projected_points: float
    # Sum of starting XI xP.

    summary: str
    # Human-readable summary of the full decision.

    # ── CONTROL ───────────────────────────────────────────────────
    error: Optional[str]
    log: list[str]
```

### Why No `minutes_risk` or `adjusted_xP` in State?

We removed these fields from the pipeline. The Stats Agent's `xP` projection already accounts for the probability a player starts (it's a prediction of actual points, not a prediction assuming guaranteed 90 minutes). Applying a second discount inside the Manager would double-penalize rotation-prone players. All nodes now operate on raw `xP` as the single ranking metric.

---

## 5. LangGraph Nodes

### Node 1: `validate_squad`

> _Source: Original spec (mine)_

**Purpose:** Sanity-check the incoming squad before optimization begins.

**Validation rules:**
1. Squad must contain exactly 15 players.
2. Each player must carry `id`, `name`, `position`, `team`, `xP`.
3. Position values must be one of `GK`, `DEF`, `MID`, `FWD`.
4. Position distribution: exactly 2 GK, at least 5 DEF, at least 5 MID, at least 3 FWD (standard FPL squad composition).

**On failure:** Sets `error` with a descriptive message, appends to `log`, and routes to END.

**Writes to State:** `log` (validation entry). Nothing else — acts as a gate.

---

### Node 2: `select_optimal_xi`

> _Source: Partner's spec (Node 3)_
> _Note: This is Node 2 in the merged graph because we removed `compute_adjusted_xp`._

**Purpose:** Enumerate all 7 legal FPL formations and greedily select the combination that maximises total `xP`.

**Valid formations (def-mid-fwd):**

| Formation | GK | DEF | MID | FWD |
|---|---|---|---|---|
| 3-4-3 | 1 | 3 | 4 | 3 |
| 3-5-2 | 1 | 3 | 5 | 2 |
| 4-3-3 | 1 | 4 | 3 | 3 |
| 4-4-2 | 1 | 4 | 4 | 2 |
| 4-5-1 | 1 | 4 | 5 | 1 |
| 5-3-2 | 1 | 5 | 3 | 2 |
| 5-4-1 | 1 | 5 | 4 | 1 |

**Selection logic per formation:**
1. Group the 15-player squad by position, sorted by `xP` descending.
2. For each formation, take the top-N players per position slot (always 1 GK).
3. If any position has fewer eligible players than the slot requires, score that formation as `-inf` and skip it.
4. Track the total `xP` across all 11 slots.
5. The formation with the highest total wins.

**Conditional edge — `is_formation_valid?`:**
After selecting the best formation, verify the XI contains exactly 11 unique players, exactly 1 GK, and the correct outfield counts. If no formation passes (all scored `-inf`), the agent sets `error = "Could not build a valid Starting XI"` and routes to END.

**Writes to State:** `formation_scores`, `formation`, `starting_xi`, `log`

---

### Node 3: `order_bench`

> _Source: Partner's spec (Node 4)_

**Purpose:** Determine the priority order of the 4 bench players for FPL's auto-substitution system.

**Ordering rules:**

| Bench Slot | Player Type | Ordering Logic |
|---|---|---|
| 1 | Outfield | Highest `xP` among remaining outfield players |
| 2 | Outfield | Second highest `xP` |
| 3 | Outfield | Third highest `xP` |
| 4 | GK | **Always last**, regardless of xP |

**Why GK always last?**
FPL's auto-sub rules can only bring on a bench GK to replace the starting GK, which almost never happens. Placing the GK in slot 4 ensures the three outfield bench slots are filled by the highest-value outfield options, maximizing the expected value of any auto-substitution.

**Writes to State:** `bench`, `log`

---

### Node 4: `select_captains`

> _Source: Both specs (functionally identical)_

**Purpose:** Assign Captain and Vice-Captain from the Starting XI.

**Selection logic:**
1. Sort `starting_xi` by `xP` descending.
2. Captain = rank 1 (highest xP).
3. Vice-Captain = rank 2 (second highest xP).

**Tiebreak:** If two players share the same `xP`, break ties by `player_id` ascending (deterministic, no randomness).

**Output fields set on player dicts:**

| Field | Value |
|---|---|
| `is_captain` | `true` for the captain, `false` otherwise |
| `is_vice_captain` | `true` for the VC, `false` otherwise |

**Writes to State:** `captain`, `vice_captain`, `captain_id`, `vice_captain_id`, updated `starting_xi` with captain flags, `log`

---

### Node 5: `advise_chips`

> _Source: My spec, with dynamic median-based thresholds_

**Purpose:** Evaluate whether activating Triple Captain or Bench Boost this gameweek would be beneficial, using **historically-derived dynamic thresholds** instead of hardcoded constants.

#### Dynamic Threshold Mechanism

Instead of fixed thresholds (which can't adapt to different seasons, model calibrations, or squad quality), we compute thresholds from historical data.

**How it works:**

1. **Collect historical data.** The state carries two lists:
   - `historical_captain_xp`: the top-xP player's projection for each past gameweek this season.
   - `historical_bench_xp`: the total bench xP for each past gameweek this season.

2. **Compute the threshold.** For each chip, take the **top N values** from the relevant historical list and calculate the **median** of those top values. This median represents "what a genuinely strong gameweek looks like for this metric."

   ```python
   def compute_dynamic_threshold(historical_values: list[float], top_n: int) -> float | None:
       """
       Returns the median of the top N historical values.
       Returns None if there are fewer than `top_n` data points
       (threshold is unreachable / insufficient data).
       """
       if len(historical_values) < top_n:
           return None
       sorted_desc = sorted(historical_values, reverse=True)
       top_slice = sorted_desc[:top_n]
       median_index = len(top_slice) // 2
       if len(top_slice) % 2 == 0:
           return (top_slice[median_index - 1] + top_slice[median_index]) / 2
       return top_slice[median_index]
   ```

3. **`top_n` parameter.** This controls how selective the threshold is:
   - **Triple Captain:** `top_n = 5` — The median of the 5 best captain projections this season. This means the captain's current xP must be "top-5 worthy" to trigger the chip.
   - **Bench Boost:** `top_n = 3` — The median of the 3 best bench totals this season. Bench Boost opportunities are rarer, so a smaller sample sets a higher bar.
   - These values are configurable constants, not magic numbers. They can be tuned during the validation phase (Weeks 13–15).

#### Chip Evaluation Rules

**Triple Captain:**
- **Gate:** `"triple_captain"` must be in `chips_available`.
- **Trigger:** Captain's `xP` ≥ `tc_threshold` (dynamic, from above).
- **Confidence:** `min(captain_xP / (tc_threshold × 1.3), 1.0)` — scales to 1.0 at 30% above threshold.

**Bench Boost:**
- **Gate:** `"bench_boost"` must be in `chips_available`.
- **Trigger:** Sum of bench `xP` ≥ `bb_threshold` (dynamic, from above).
- **Confidence:** `min(bench_total_xP / (bb_threshold × 1.3), 1.0)`.

**Priority:** If both qualify, Triple Captain is preferred (a guaranteed doubling of the captain's points is more reliable than speculative bench contributions).

**If neither qualifies:** `chip_recommendation = None`.

#### Edge Case: Threshold Never Reached

If `compute_dynamic_threshold` returns `None` (fewer data points than `top_n`), the chip is **never recommended** for that category. This occurs early in the season (e.g., GW1–4 when there's insufficient history). The agent logs this explicitly:

```
"advise_chips: Insufficient historical data (3 of 5 GWs needed) — Triple Captain threshold unavailable. Skipping TC evaluation."
```

This is the correct behavior: the agent should not guess a threshold from a tiny sample. As gameweeks accumulate, the threshold becomes available naturally.

#### Fallback: Minimum Floor

Even with dynamic thresholds, we enforce a **minimum floor** so the agent never recommends a chip on a mediocre week just because the season's history has been uniformly poor:
- Triple Captain floor: captain xP ≥ **7.0** (regardless of dynamic threshold).
- Bench Boost floor: bench total xP ≥ **14.0** (regardless of dynamic threshold).

The effective threshold is: `max(dynamic_threshold, floor)`.

**Writes to State:** `chip_recommendation`, `log`

---

### Node 6: `format_output`

> _Source: Combined from both specs_

**Purpose:** Assemble the final output payload and a human-readable summary.

**Logic:**
1. Calculate `projected_points` = sum of `xP` across all 11 Starting XI players.
2. Build the structured JSON payload (see Output Payload section).
3. Generate a `summary` string including: formation, Starting XI by position, captain/VC with xP, bench order, chip recommendation (if any), and projected points.
4. Write the final `log` entry.

**Writes to State:** `projected_points`, `summary`, `log`

---

## 6. Graph Architecture and Conditional Edges

```
START
  │
  ▼
validate_squad ────── (invalid?) ────► END (error)
  │
  (valid)
  ▼
select_optimal_xi ◄────────────────┐
  │                                │
  [is_formation_valid?]            │
  ├── NO (try next formation) ─────┘
  └── YES
  │
  ▼
order_bench
  │
  ▼
select_captains
  │
  ▼
  ┌──────────────────────────────────┐
  │ CONDITIONAL: chips_evaluable?    │
  └──────────────────────────────────┘
     │                      │
  (yes)                  (no)
     ▼                      │
advise_chips                │
     │                      │
     └──────────┬───────────┘
                ▼
        format_output
                │
                ▼
               END
```

### Conditional Edge Definitions

```python
def should_evaluate_chips(state: ManagerState) -> str:
    """
    Route to chip advisor only if the user has Triple Captain
    or Bench Boost available. Free Hit and Wildcard are transfer
    chips handled by the Sporting Director — the Manager ignores them.
    """
    relevant_chips = {"triple_captain", "bench_boost"}
    if relevant_chips.intersection(set(state["chips_available"])):
        return "advise_chips"
    return "format_output"
```

**Why this edge exists:** If the user has no relevant chips (or only Free Hit/Wildcard), running the chip advisor is unnecessary. The conditional edge keeps the graph efficient and avoids producing confusing "no chip recommended" output when no chips were possible in the first place.

---

## 7. LangGraph Graph Construction

```python
from langgraph.graph import StateGraph, END

workflow = StateGraph(ManagerState)

# ── Add Nodes ─────────────────────────────────────
workflow.add_node("validate_squad", validate_squad)
workflow.add_node("select_optimal_xi", select_optimal_xi)
workflow.add_node("order_bench", order_bench)
workflow.add_node("select_captains", select_captains)
workflow.add_node("advise_chips", advise_chips)
workflow.add_node("format_output", format_output)

# ── Add Edges ─────────────────────────────────────
workflow.set_entry_point("validate_squad")

workflow.add_conditional_edges(
    "validate_squad",
    lambda state: "select_optimal_xi" if state.get("error") is None else END
)

# select_optimal_xi handles the formation loop internally.
# It either succeeds (sets starting_xi) or sets error and routes to END.
workflow.add_conditional_edges(
    "select_optimal_xi",
    lambda state: "order_bench" if state.get("error") is None else END
)

workflow.add_edge("order_bench", "select_captains")

workflow.add_conditional_edges(
    "select_captains",
    should_evaluate_chips
)

workflow.add_edge("advise_chips", "format_output")
workflow.add_edge("format_output", END)

# ── Compile ───────────────────────────────────────
manager_agent = workflow.compile()
```

---

## 8. Input / Output Contract

### Input

```json
{
  "gameweek": 35,
  "chips_available": ["triple_captain", "bench_boost"],
  "bank": 0.5,
  "squad": [
    {
      "id": 123,
      "name": "M.Salah",
      "position": "MID",
      "team": "LIV",
      "price": 13.2,
      "xP": 8.1,
      "xP_5gw": 34.6
    }
    // ... 14 more players
  ],
  "historical_captain_xp": [7.2, 9.1, 6.5, 11.0, 8.3, 7.8, 10.2, 6.9],
  "historical_bench_xp": [12.4, 15.1, 9.8, 20.3, 11.7, 14.0, 18.5, 10.2]
}
```

### Output

```json
{
  "gameweek": 35,
  "formation": "4-3-3",
  "starting_xi": [
    {
      "id": 123,
      "name": "M.Salah",
      "position": "MID",
      "team": "LIV",
      "xP": 8.1,
      "is_captain": true,
      "is_vice_captain": false
    }
    // ... 10 more players
  ],
  "bench": [
    {"id": 456, "name": "Bench Player", "position": "DEF", "bench_order": 1, "xP": 3.2},
    {"id": 457, "name": "Bench Mid", "position": "MID", "bench_order": 2, "xP": 2.9},
    {"id": 458, "name": "Bench Fwd", "position": "FWD", "bench_order": 3, "xP": 2.1},
    {"id": 459, "name": "Bench GK", "position": "GK", "bench_order": 4, "xP": 3.5}
  ],
  "captain": "M.Salah",
  "vice_captain": "Haaland",
  "captain_id": 123,
  "vice_captain_id": 301,
  "chip_recommendation": {
    "chip": "triple_captain",
    "confidence": 0.84,
    "reasoning": "Captain projects 8.1 xP — above the dynamic threshold of 7.8 (median of top 5 historical captain projections). Floor of 7.0 also met."
  },
  "projected_points": 61.3,
  "summary": "GW35 | Formation: 4-3-3 | Captain: M.Salah (8.1 xP) | VC: Haaland (7.9 xP) | Chip: Triple Captain (conf 0.84) | Projected: 61.3 pts",
  "error": null,
  "log": [
    "validate_squad: 15 players validated (2 GK, 5 DEF, 5 MID, 3 FWD)",
    "select_optimal_xi: best formation 4-3-3 (61.3 xP) out of 7 evaluated",
    "order_bench: bench ordered by xP desc, GK placed in slot 4",
    "select_captains: captain=M.Salah (8.1), vc=Haaland (7.9)",
    "advise_chips: TC threshold=7.8 (median top-5), captain xP 8.1 qualifies. BB threshold=15.1 (median top-3), bench total 11.7 does not qualify. Recommending triple_captain.",
    "format_output: Manager Agent complete for GW35"
  ]
}
```

---

## 9. Testing Strategy

| Test Case | Input Condition | Expected Behavior |
|---|---|---|
| **Happy path** | 15 players, no chips | Returns valid XI, bench order, captains, no chip rec |
| **Formation edge case** | Only 3 DEF in squad | Only 3-back formations viable; 4-back and 5-back score `-inf` |
| **All formations impossible** | Corrupted position data | `error` set, graph routes to END |
| **Captain tiebreak** | Two players share top xP | Lower `player_id` wins captain (deterministic) |
| **GK bench placement** | Bench GK has highest xP of all bench | GK still placed in slot 4 regardless |
| **TC triggers** | Captain xP exceeds dynamic threshold + floor | `chip_recommendation.chip = "triple_captain"` |
| **BB triggers** | Bench total xP exceeds dynamic threshold + floor | `chip_recommendation.chip = "bench_boost"` |
| **Both chips trigger** | TC and BB both qualify | TC preferred (higher certainty) |
| **Threshold unreachable (early season)** | `historical_captain_xp` has only 3 entries, `top_n = 5` | TC threshold = `None`, chip not evaluated, log explains why |
| **Threshold never exceeded** | Dynamic threshold = 10.5, captain xP = 9.0 | `chip_recommendation = None`, no chip played |
| **No relevant chips** | `chips_available = ["free_hit"]` | `advise_chips` node is skipped entirely via conditional edge |
| **Weak season history** | All past captain xPs are low (e.g., 4.0–5.0) | Dynamic threshold is low, but **floor** (7.0) prevents TC on a mediocre week |
| **All same xP** | All 15 players have xP = 5.0 | Deterministic tiebreak by `player_id` — no randomness |

---

## 10. Known Limitations

1. **Greedy formation scoring** — Picks top-N players per slot per formation. Does not explore non-greedy combinations (e.g., benching a weaker DEF to start a stronger MID in a different formation). Rarely suboptimal in practice.
2. **No fixture-level awareness** — The Manager applies no fixture multiplier. Fixture context is already baked into the Stats Agent's `xP`.
3. **Dynamic thresholds require history** — Early-season (GW1–4) the chip advisor is effectively disabled. This is intentional but means the agent cannot recommend chips in early gameweeks.
4. **No near-miss surfacing** — If two formations score within 0.5 xP of each other, the agent picks one silently without alerting the user.
5. **No `minutes_risk` override** — We intentionally removed `minutes_risk` from the Manager's scope. If the Stats Agent's `xP` underweights rotation risk, the Manager has no mechanism to compensate.

---

## 11. Future Enhancements (Post-v1, Parked)

- **Ownership-weighted captaincy:** Factor in player ownership % for differential captain picks.
- **Double Gameweek awareness:** Prioritize players with two fixtures in a single GW.
- **Risk profiles:** Let the user choose "safe" vs. "aggressive" lineups.
- **Auto-sub simulation:** Model the probability a starter doesn't play and the expected value of the auto-sub chain.
- **Adaptive `top_n`:** Dynamically adjust the `top_n` parameter for chip thresholds based on the gameweek number (smaller early, larger late).
- **Near-miss alerts:** Surface formations within 1.0 xP of the winner so the user can make an informed override.

---

## 12. Glossary

| Term | Definition |
|---|---|
| **xP** | Expected Points — the ML-predicted score for a player in the upcoming gameweek. **The single ranking metric used by this agent.** |
| **GK / DEF / MID / FWD** | Goalkeeper / Defender / Midfielder / Forward |
| **Starting XI** | The 11 players who earn full points |
| **Bench** | The 4 remaining squad players, ordered for auto-substitution (GK always slot 4) |
| **Triple Captain** | Chip that triples (instead of doubles) the captain's points for one GW |
| **Bench Boost** | Chip that adds bench players' points to the GW total |
| **Free Hit / Wildcard** | Transfer-related chips — handled by the Sporting Director, not the Manager |
| **Dynamic Threshold** | A chip-trigger threshold calculated as the median of the top-N historical xP values for that metric |
| **Floor** | A minimum xP value below which a chip is never recommended, regardless of the dynamic threshold |
| **`top_n`** | The number of top historical values used to compute the dynamic threshold median |
| **LangGraph State** | The shared data object that all nodes read from and write to |
| **Node** | A single processing step (function) in the LangGraph workflow |
| **Conditional Edge** | A routing decision that determines which node runs next based on state |