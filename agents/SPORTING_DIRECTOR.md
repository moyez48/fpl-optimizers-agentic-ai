# Agent Specification: The Sporting Director

## 1. Agent Identity & Core Objective

**Role:** The Sporting Director — the squad's financial and strategic advisor.

**Objective:** Given the Stats Agent's ranked player output and the manager's current squad, identify the best available transfers (single and multi), assess squad health per player, and flag wildcard or hold conditions — all within strict FPL budget constraints including selling price locks.

---

## 2. Input State

### From the Stats Agent

| Variable | Type | Description |
|---|---|---|
| `ranked` | dict | Position-keyed ranked player lists: `ALL`, `GK`, `DEF`, `MID`, `FWD` |
| `bootstrap` | dict | FPL bootstrap-static JSON (team names, player status, availability) |
| `gameweek` | int | Current gameweek — transfers are planned for `gameweek + 1` |
| `form_stats` | list[dict] | Per-player form records from Stats Agent (source of `avg_minutes_last5`, `ewm_points`, `std_pts_last5`, `blank_rate_last5`) |

### From the user / app

| Variable | Type | Description |
|---|---|---|
| `squad` | list[PlayerProfile] | 15-player squad — see schema below |
| `bank` | float | Money in the bank (ITB), £m |
| `free_transfers` | int | Free transfers available this gameweek (0–2) |

### PlayerProfile schema

| Field | Type | Description |
|---|---|---|
| `name` | str | Player name |
| `position` | str | `GK` / `DEF` / `MID` / `FWD` |
| `team` | str | Club name |
| `element` | int | FPL player ID — used to look up `bootstrap` availability data |
| `cost` | float | Current market price, £m |
| `purchase_price` | float | Price paid when player was bought, £m |
| `sell_price` | float | Actual sell price after price lock rule (see Section 4). Computed by `SquadValidator.compute_sell_price()` before any budget check. |
| `expected_pts` | float | Model prediction scaled by `start_prob` |
| `start_prob` | float | Start probability 0.0–1.0 |
| `avg_pts_last5` | float | Last-5 GW average |
| `is_available` | bool | False = injured/suspended |
| `status` | str | FPL availability code: `a`/`d`/`i`/`s`/`u`. Sourced from `bootstrap["elements"]` by `element` ID. |
| `chance_of_playing` | int | 0–100 injury probability. Sourced from `bootstrap["elements"]` by `element` ID. |
| `avg_minutes_last5` | float | Average minutes played in last 5 GWs. Sourced from `form_stats`. |
| `ewm_points` | float | Exponentially weighted recent form score. Sourced from `form_stats`. |

### Config parameters (optional, with defaults)

| Parameter | Default | Description |
|---|---|---|
| `sd_top_n` | 10 | Max single-transfer recommendations to return. Multi-transfer pairs are returned separately. |
| `sd_window` | 5 | Fixture window in gameweeks |
| `max_transfers` | 2 | Max sequential transfers to evaluate (cap: 3) |
| `vorp_replacement_pct` | 20 | Percentile of `expected_pts` within each position cluster used as the replacement level. A player at this percentile has `vorp_score = 0`. Calibrate to your league size and roster depth. **Note:** placeholder; calibrate empirically during Weeks 5–6. |
| `t1_candidates` | 3 | Number of top T1 transfers to explore when building T1+T2 pairs |

---

## 3. Tools

| Tool | Description |
|---|---|
| `FixtureAnalyser.fetch_fixtures(from_gameweek, window)` | Fetches FPL fixture difficulty ratings from live API or local cache (`data/fixtures_cache.json`) |
| `FixtureAnalyser.enrich_players(players, from_gameweek, window)` | Returns a `fixture_data` dict mapping `team` → list of fixtures over the window. Consumed by `SquadHealthAnalyser` to populate `has_blank_gw` and `has_double_gw` per player. |
| `SquadValidator.compute_sell_price(player)` | Computes `sell_price` using the price lock rule (see Section 4). Called once per squad player before any budget check. |
| `SquadValidator.get_sellable_players(squad)` | Returns all 15 squad players with `sell_price` already populated on each. |
| `SquadValidator.get_buyable_players(squad, sell, pool)` | Filters pool to legally buyable players for a given sell target. Checks: (1) affordability — `bank + sell.sell_price >= buy.cost`; (2) squad composition — buying the candidate must not cause any club to have more than 3 players in the squad (accounting for the sell player being removed). Pass the simulated squad in multi-transfer evaluation so club counts reflect prior transfers. |
| `SquadValidator.can_afford(squad, sell, buy)` | Budget check using `sell.sell_price` (not `sell.cost`). Available funds = `bank + sell.sell_price` (where `bank` is the top-level state field). |
| `VORPCalculator.build_position_stats(pool, replacement_pct)` | For each position cluster (GK/DEF/MID/FWD), computes `mean_pts`, `std_pts`, `replacement_z`, and a per-player `vorp_score` lookup (keyed by `element`) for pool players. Returns a `position_stats` dict keyed by position. Squad players (sell candidates) are not in the pool; their `vorp_score` is computed on the fly using the same stats (see Node 5). Edge cases: if `std_pts == 0`, all Z-scores for that position are 0; if fewer than 2 pool players at a position, `vorp_score` defaults to 0. |
| `SquadHealthAnalyser.analyse(squad_players, fixture_data)` | Produces a per-dimension health breakdown for each squad player with explicit flags. |
| `MultiTransferEvaluator.evaluate(squad, pool, validator, t1_candidates, max_transfers)` | Explores the top `t1_candidates` T1 options. For each T1, simulates the post-T1 squad and evaluates T2. Returns the best T1+T2 pair. Budget is propagated across transfers. T1 sell player is excluded from T2 sell candidates. Flags `budget_unlock` on T2 if T1's proceeds made that target newly affordable. |

---

## 4. Budget Rules

### Selling price lock

FPL does not allow managers to profit fully from player price rises. When a player's price has risen since purchase, only 50% of the gain is recoverable (rounded down to the nearest £0.1m). If the price has fallen, the full loss is borne by the seller.

```
if current_price > purchase_price:
    sell_price = purchase_price + floor((current_price - purchase_price) * 10 / 2) / 10
else:
    sell_price = current_price
```

**Example:** Bought Salah at £12.5m, now worth £13.0m.
`floor((13.0 - 12.5) * 10 / 2) / 10 = floor(2.5) / 10 = 2 / 10 = 0.2` → sell price = £12.7m.

`sell_price` is computed once by `SquadValidator.compute_sell_price(player)` and stored on each `PlayerProfile` before any budget check. All downstream code uses `sell.sell_price`, not `sell.cost`.

### Bank propagation across transfers

When evaluating T2, the bank available is the bank after T1 has been applied:

```
post_T1_bank = original_bank + sell_price_T1 - buy_price_T1
```

T2 affordability is checked against `post_T1_bank`. The T1 sell player is removed from the T2 sell candidate list, and the T1 buy player is added to the simulated squad.

### Hit cost

```
hit_cost = max(0, transfers_used + 1 - free_transfers) × 4
```

T2 is only recommended if its `expected_gain` passes the gate (`expected_gain > hit_cost`) with `transfers_used=1`.

---

## 5. VORP — Value Over Replacement Player

VORP is a single-number measure of a player's value above the replacement level, specific to their position and league settings. Pool players (buy candidates) receive a pre-computed `vorp_score` stored in `position_stats`. Squad players (sell candidates) are not in the pool; their score is computed on the fly using the same position-level statistics. In both cases the score is a position-normalised Z-score anchored to 0 at the replacement level.

### Replacement level

The replacement level for each position is the player at the `vorp_replacement_pct` percentile of `expected_pts` within that position cluster. A player at exactly this percentile has `vorp_score = 0`. Higher is better; negative means below replacement. Calibrate to your league size and roster depth (see Section 2).

### Per-player VORP score

For each position cluster, computed once over the full available player pool by `VORPCalculator.build_position_stats(pool, replacement_pct)`:

```
mean_pts[pos]        = mean(expected_pts)   across all available players at pos
std_pts[pos]         = std(expected_pts)    across all available players at pos

z_score(player)      = (player.expected_pts - mean_pts[pos]) / std_pts[pos]

replacement_z[pos]   = z_score of the player at the vorp_replacement_pct percentile

vorp_score(player)   = z_score(player) - replacement_z[pos]
```

`vorp_score` is stored in a per-player lookup dict (keyed by `element`) inside `position_stats`. It is not written back to `PlayerProfile`.

### Transfer evaluation

Transfer candidates are evaluated in two steps:

**Step 1 — Gate (is this transfer worth its cost in points?)**

```
expected_gain = buy.expected_pts - sell.expected_pts
hit_cost      = max(0, transfers_used + 1 - free_transfers) × 4

Pass if expected_gain > hit_cost, else discard.
```

**Step 2 — Rank (among passing transfers, which is the biggest upgrade?)**

```
sell_vorp_score = (sell.expected_pts - mean_pts[sell.position]) / std_pts[sell.position] - replacement_z[sell.position]
buy_vorp_score  = position_stats[buy.position]["vorp_scores"][buy.element]

vorp_gain = buy_vorp_score - sell_vorp_score
```

Transfers that pass the gate are ranked by `vorp_gain` descending. Where `vorp_gain` is equal, the tiebreaker is `cost_delta` ascending — prefer the cheaper upgrade to preserve more bank. The top `sd_top_n` are returned as `single_transfer_options`.

---

## 6. Squad Health

Squad health is a per-dimension breakdown per player — no composite score. Each dimension surfaces its raw signals. Explicit flags handle the most critical alerts. The Manager Agent consumes this output to inform XI selection and transfer decisions.

### Health record schema (per player)

```
name:           str
availability:
    status:                str    — "a" / "d" / "i" / "s" / "u" (from bootstrap via element ID)
    chance_of_playing:     int    — 0–100 (from bootstrap via element ID)
    is_available:          bool
    yellow_cards:          int    — season yellow card total (from bootstrap via element ID)
rotation_risk:
    start_prob:            float  — 0.0–1.0
    avg_minutes_last5:     float  — average minutes played in last 5 GWs (from form_stats)
    blank_rate_last5:      float  — proportion of last 5 GWs where minutes played = 0
form:
    avg_pts_last5:         float
    ewm_points:            float  — exponentially weighted recent form (from form_stats)
volatility:
    std_pts_last5:         float  — standard deviation of points over last 5 GWs
fixture:
    has_blank_gw:           bool  — blank gameweek in the fixture window
    has_double_gw:          bool  — double gameweek in the fixture window
flags:          list[str]  — explicit alerts (see below)
```

### Flags

| Flag | Trigger condition |
|---|---|
| `injured` | `status` is `i`, `s`, or `u` |
| `doubtful` | `status` is `d` |
| `suspension_risk` | `yellow_cards >= 10` (second PL yellow card threshold; resets after GW32) |
| `rotation_risk` | `start_prob < 0.6` OR `avg_minutes_last5 < 45`. **Note:** threshold is a placeholder; calibrate during Weeks 5–6. |
| `form_declining` | `avg_pts_last5 - ewm_points > 1.5` — recent games pulling the weighted average below the 5-GW average. **Note:** threshold is a placeholder; calibrate during Weeks 5–6. |
| `blank_gw_{N}` | Player's team has no fixture in GW N within the window |
| `double_gw_{N}` | Player's team has two fixtures in GW N within the window |
| `high_volatility` | `std_pts_last5 > 3.5` — points swing significantly week-to-week. **Note:** threshold is a placeholder; calibrate during Weeks 5–6. |

---

## 7. LangGraph Workflow

```
START
  │
  ▼
Node 1: build_player_pool
  │
  ▼
Node 2: compute_sell_prices
  │
  ▼
Node 3: fetch_enrich_fixtures
  │
  ▼
Node 4: analyse_squad_health
  │
  ▼
Node 5: score_single_transfers
  │
  ▼
Node 6: evaluate_multi_transfer
  │
  ▼
Node 7: detect_wildcard_hold
  │
  ▼
Node 8: format_output
  │
  ▼
END
```

Every node has a **conditional error exit**: if an exception is raised, `state["error"]` is set and execution routes to END immediately. If `state["error"]` is already set on entry, the node passes through to END immediately.

### Node 1 — `build_player_pool`

Build a flat list of PlayerProfiles from `state["ranked"]` using the position-specific lists (GK, DEF, MID, FWD). Filter out players where `is_available=False`. Deduplicate by `element` (FPL player ID), not name.

### Node 2 — `compute_sell_prices`

For each of the 15 squad players, call `SquadValidator.compute_sell_price(player)` and store the result as `player.sell_price`. This must run before any budget check in any subsequent node.

### Node 3 — `fetch_enrich_fixtures`

Call `FixtureAnalyser.fetch_fixtures(from_gameweek=gameweek+1, window=sd_window)`. If successful, call `FixtureAnalyser.enrich_players()` to produce a `fixture_data` dict (team → fixture list) passed to `SquadHealthAnalyser` in Node 4. If the fetch fails (API and cache both unavailable), log a WARNING and pass `fixture_data=None` — blank/double GW flags will be absent from squad health. Failure is **non-fatal**.

### Node 4 — `analyse_squad_health`

Call `SquadHealthAnalyser.analyse(squad_players, fixture_data)`. The analyser:
1. Looks up `status`, `chance_of_playing`, and `yellow_cards` from `bootstrap["elements"]` by each player's `element` ID.
2. Looks up `avg_minutes_last5`, `ewm_points`, `std_pts_last5`, and `blank_rate_last5` from `form_stats`: attempt lookup by `element` first, fall back to `name`, log a WARNING and use `0.0` as default if neither matches.
3. Produces one health record per player with all dimensions and flags populated.

Attach the result to state as `squad_health`.

### Node 5 — `score_single_transfers`

1. Call `VORPCalculator.build_position_stats(pool, vorp_replacement_pct)` once to pre-compute position-level statistics.
2. Call `SquadValidator.get_sellable_players(squad)` to get the list of squad players (with `sell_price` already populated from Node 2).
3. For each sellable squad player:
   a. Compute `sell_vorp_score = (sell.expected_pts - mean_pts[sell.position]) / std_pts[sell.position] - replacement_z[sell.position]`.
   b. Filter the pool to affordable same-position candidates via `SquadValidator.get_buyable_players()` — checks affordability and club composition (max 3 per club).
   c. For each valid buy candidate:
      i. Look up `buy_vorp_score = position_stats[buy.position]["vorp_scores"][buy.element]`.
      ii. Compute `expected_gain = buy.expected_pts - sell.expected_pts` and `hit_cost = max(0, 1 - free_transfers) × 4`.
      iii. Discard if `expected_gain <= hit_cost`.
      iv. Compute `vorp_gain = buy_vorp_score - sell_vorp_score`. Record the transfer.
4. Sort all recorded transfers by `vorp_gain` descending, with `cost_delta` ascending as a tiebreaker.
5. Store top `sd_top_n` as `single_transfer_options`.

### Node 6 — `evaluate_multi_transfer`

Only runs if `max_transfers >= 2` and `single_transfer_options` is non-empty.

1. Take the top `t1_candidates` options from `single_transfer_options` as T1 candidates.
2. For each T1 candidate:
   a. Simulate the squad after T1: apply `post_T1_bank = bank + sell_price_T1 - buy_price_T1`, remove T1 sell player, add T1 buy player.
   b. Re-run Node 5 logic on the simulated squad with `hit_cost = max(0, 2 - free_transfers) × 4` (i.e. `transfers_used=1`).
   c. Find the best T2 (highest `vorp_gain`) from the simulated squad.
   d. Only include T2 if its `expected_gain > hit_cost`.
   e. Set `budget_unlock_flag=True` on T2 if T2's buy target was unaffordable against the original bank but became affordable after T1.
3. Select the best overall T1+T2 pair (highest combined `vorp_gain_T1 + vorp_gain_T2`).
4. Store as `multi_transfer_option` (a single best pair, not a list).

### Node 7 — `detect_wildcard_hold`

**Wildcard trigger:** 5 or more squad players have 2 or more flags (any combination). The 2-flag threshold prevents a single signal (e.g. `doubtful`) from inflating the count. 5 problems cannot be fixed within available free transfers without incurring excessive hits — a wildcard is the appropriate response. **Note:** the 5-player and 2-flag thresholds are placeholders; calibrate empirically during Weeks 5–6.

**Hold trigger:** `single_transfer_options` is empty — no transfer passed the gate. Recommend banking the free transfer.

### Node 8 — `format_output`

Assemble final output. Serialise into `recommended_transfers`: single-transfer options from `single_transfer_options` each become one entry with `transfer_number=1`; the best multi-transfer pair from `multi_transfer_option` becomes two consecutive entries with `transfer_number=1` and `transfer_number=2`. Write `squad_health`, `recommended_transfers`, `wildcard_flag`, `hold_flag`, `sd_summary`, and `sd_log` to state. Log completion.

---

## 8. Output Contract

```json
{
  "gameweek": "int — gameweek transfers are planned for (current + 1)",
  "free_transfers_available": "int — free transfers at time of evaluation",
  "bank": "float — current bank balance in £m",

  "squad_health": [
    {
      "name": "string",
      "availability": {
        "status": "string — a/d/i/s/u",
        "chance_of_playing": "int 0–100",
        "is_available": "bool",
        "yellow_cards": "int — season yellow card total"
      },
      "rotation_risk": {
        "start_prob": "float 0–1",
        "avg_minutes_last5": "float",
        "blank_rate_last5": "float 0–1"
      },
      "form": {
        "avg_pts_last5": "float",
        "ewm_points": "float"
      },
      "volatility": {
        "std_pts_last5": "float"
      },
      "fixture": {
        "has_blank_gw": "bool",
        "has_double_gw": "bool"
      },
      "flags": ["string — e.g. blank_gw_32, form_declining, rotation_risk, injured, suspension_risk, high_volatility"]
    }
  ],

  "recommended_transfers": [
    {
      "transfer_number": "int — 1 (single) or 1/2 (multi-transfer pair)",
      "sell": "PlayerProfile",
      "buy": "PlayerProfile",
      "sell_price": "float — actual sell price after price lock rule",
      "cost_delta": "float — buy.cost - sell.sell_price",
      "remaining_bank": "float — bank after this transfer executes",
      "sell_vorp_score": "float — position-normalised Z-score of the sell player above replacement",
      "buy_vorp_score": "float — position-normalised Z-score of the buy player above replacement",
      "vorp_gain": "float — buy_vorp_score minus sell_vorp_score — primary ranking signal",
      "expected_gain": "float — buy.expected_pts minus sell.expected_pts",
      "transfer_cost_points": "int — 0 if free, 4 per hit",
      "budget_unlock_flag": "bool — true if a preceding transfer freed budget for this one",
      "reasoning": "string — structured reasoning stub for Manager Agent"
    }
  ],

  "wildcard_flag": "bool",
  "hold_flag": "bool",
  "sd_summary": "string — structured one-paragraph briefing stub",
  "sd_log": ["string — execution log entries"],
  "error": "string | null"
}
```

---

## 9. Shared LangGraph State Contract

All three agents operate on a single shared state object — `FPLOptimizerState`.

```python
class FPLOptimizerState(TypedDict):

    # ── Shared inputs (injected before graph runs) ────────────────────────────
    gameweek:        int          # Target GW
    season:          str          # e.g. "2025-26"
    squad:           list         # 15-player squad (with purchase_price per player)
    bank:            float        # £m in the bank
    free_transfers:  int          # Free transfers available (0–2)

    # ── Stats Agent outputs ───────────────────────────────────────────────────
    # Written by: Stats Agent | Read by: Sporting Director, Manager Agent
    bootstrap:         dict       # FPL bootstrap-static JSON
    ranked:            dict       # Position-keyed ranked player lists
    form_stats:        list       # Per-player last-5 GW form records
    predictions:       list       # Raw model predictions per player
    start_probs:       dict       # { player_name: float } start probabilities
    captain_shortlist: list       # Top 5 captain candidates (start_prob >= 0.70)

    # ── Sporting Director outputs ─────────────────────────────────────────────
    # Written by: Sporting Director | Read by: Manager Agent, App
    squad_health:             list   # Per-player health breakdown (see Section 6)
    recommended_transfers:    list   # Serialised transfer recommendations (see Section 8)
    wildcard_flag:            bool   # True if squad health triggers a wildcard recommendation
    hold_flag:                bool   # True if no transfer passed the gate — bank the free transfer
    sd_summary:               str    # One-line briefing stub for Manager Agent
    sd_log:                   list   # Sporting Director execution log

    # ── Manager Agent outputs ─────────────────────────────────────────────────
    # Written by: Manager Agent | Read by: App / Frontend
    starting_xi:          list        # 11 selected PlayerProfiles
    bench:                list        # 4 bench PlayerProfiles (ordered)
    captain:              dict        # PlayerProfile of selected captain
    vice_captain:         dict        # PlayerProfile of selected vice-captain
    chip_recommendation:  str | None  # "triple_captain" | "bench_boost" | "wildcard" | "free_hit" | null
    projected_pts:        float       # Total projected points for the GW
    manager_summary:      str         # Final briefing for the frontend

    # ── Control ───────────────────────────────────────────────────────────────
    error:  str | None    # Set by any node on failure; causes all downstream nodes to skip
    log:    list[str]     # Appended to by every node; full execution trace
```

**Key rules:**
- Each agent appends to `log`, never overwrites it
- Any node that sets `error` routes to END — all downstream nodes skip on entry
- `squad`, `bank`, and `free_transfers` are injected by the app; no agent writes to them
- The Manager Agent reads `squad_health` and `recommended_transfers` from the Sporting Director

---

## 10. What Is Out of Scope

- Real-time lineup confirmation (not known until ~1hr before kick-off)
- Chip strategy (Free Hit, Bench Boost, Triple Captain) — covered by Manager Agent
- Multi-gameweek horizon planning beyond the `sd_window` fixture window
- Price trend prediction (player price rise/fall forecasting)
- User authentication or saved squad persistence

---

*Sporting Director Agent Specification — FPL Optimizer Agentic AI — 2025-26*
