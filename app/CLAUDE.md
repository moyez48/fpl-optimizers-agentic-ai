# FPL Optimizer — Project Instructions

## Project Overview

This is an FPL (Fantasy Premier League) Optimizer web/mobile app built with a **3-agent Chain-of-Thought pipeline**. The app helps users optimize their FPL squad by analyzing player data, recommending an optimal XI, and suggesting transfers.

FPL rules context:
- 15-player squad: 2 GKP, 5 DEF, 5 MID, 3 FWD
- £100m budget, max 3 players per club
- Starting XI: 1 GKP + 10 outfield (valid formation: min 3 DEF, min 2 MID, min 1 FWD)
- Transfers: 1 free per GW; each extra costs -4 pts
- Chips: Triple Captain (3x captain pts), Bench Boost (all 15 score), Wildcard (unlimited transfers), Free Hit (temporary squad)

**Current phase**: Initial prototype using fake data only. Do not integrate real APIs until instructed.

---

## Tech Stack

- **Frontend**: React (web) + React Native (mobile)
- **Styling**: Tailwind CSS, mobile-first
- **State**: React Context or Zustand (keep it simple)
- **Backend**: Node.js (pseudo/mock — no real server needed in prototype)
- **Data**: Fake static JSON (50 players, invented names/stats)
- **Charts**: Recharts or Chart.js
- **Export**: CSV + JSON via client-side generation

---

## Architecture — 3-Agent Pipeline

Agents run **sequentially** (chain of thought). Each agent takes the previous agent's output as input.

```
User Input → Statistician Agent → Manager Agent → Transfer Agent → Dashboard
```

### Agent 1: Statistician
- **Input**: User's 15-player squad IDs, risk tolerance (0–100)
- **Logic**: Compute `adjustedXPts` per player using fixture difficulty, form, injury penalty
- **Output**: Ranked player list, injury alerts, squad total xPts

### Agent 2: Manager
- **Input**: Statistician output + available chips + bank
- **Logic**: Select valid XI (formation rules + 3-per-club limit), assign captain (highest xPts), evaluate chip usage
- **Output**: Starting XI, bench order, captain/VC, chip recommendation, total projected pts

### Agent 3: Transfer
- **Input**: Manager output + squad + bank + free transfers
- **Logic**: Identify weakest players, find affordable replacements, calculate net gain after hit penalties
- **Output**: Up to 2 ranked transfer recommendations, post-transfer squad value

### Orchestrator
- Chains all three agents
- Emits events for UI progress tracking (`agent:start`, `agent:complete`)
- Builds final summary object for dashboard

---

## Fake Data Schema

All prototype data lives in `src/data/players.js`. Use this schema — do not deviate:

```js
{
  id: Number,
  name: String,           // e.g. "Erling Haaland"
  position: "GKP" | "DEF" | "MID" | "FWD",
  team: String,           // e.g. "Man City"
  price: Number,          // £m, e.g. 14.0
  form: Number,           // 0–20, recent GW pts average
  xPts: Number,           // base projected pts, 0–15
  xG: Number,             // expected goals
  xA: Number,             // expected assists
  fixtureDifficulty: Number, // 1 (easy) – 5 (hard)
  nextFixture: String,    // e.g. "Wolves (H)"
  injured: Boolean,       // ~10% of players flagged true
  ownership: Number,      // % ownership, e.g. 72.4
  variance: Number        // spread/risk, 1.5–5.0
}
```

Pool size: **50 players** across all 20 Premier League clubs. Prices range £4.0m–£15.0m. At least 5 players must have `injured: true`.

---

## File Structure

```
/src
  /agents
    statisticianAgent.js
    managerAgent.js
    transferAgent.js
    optimizer.js          ← orchestrator
  /components
    /screens
      InputScreen.jsx
      LoadingScreen.jsx
      StatsScreen.jsx
      ManagerScreen.jsx
      Dashboard.jsx
    /ui
      PlayerCard.jsx
      AgentProgressBar.jsx
      SummaryCard.jsx
      PointsChart.jsx
  /data
    players.js            ← 50-player fake dataset
  /hooks
    useOptimizer.js       ← wraps orchestrator, manages loading state
  /utils
    export.js             ← CSV/JSON export helpers
    formations.js         ← formation validation logic
  App.jsx
  index.js
```

---

## Key Implementation Rules

### Agent Logic
- `adjustedXPts` formula: `baseXPts * injuryFactor * fixtureFactor * formFactor + riskBonus`
  - `injuryFactor`: injured = 0.9, healthy = 1.0
  - `fixtureFactor`: `(6 - fixtureDifficulty) / 5`
  - `formFactor`: `0.7 + 0.3 * (form / 20)`
  - `riskBonus`: `variance * (riskTolerance / 100)`
- Transfer net gain = `inPlayer.adjustedXPts - outPlayer.adjustedXPts - hitCost`
- Only recommend a hit transfer if `netGain > 0`
- Triple Captain trigger: captain `adjustedXPts > 12` AND `fixtureDifficulty ≤ 2`
- Bench Boost trigger: sum of bench 4 `adjustedXPts > 20`

### Formation Rules (enforced in Manager Agent)
- Exactly 1 GKP in XI
- DEF: min 3, max 5
- MID: min 2, max 5
- FWD: min 1, max 3
- Total outfield: 10
- Max 3 players from any single club (across all 15, not just XI)

### UI/UX Rules
- **Mobile-first**: design for 375px width, scale up
- Player cards: color-coded by xPts (green ≥ 10, amber 6–9.9, red < 6)
- Injured players: amber `⚠️` badge, never selected as captain
- FDR badge: 🟢 1–2, 🟡 3, 🔴 4–5
- Agent pipeline shows sequential progress bars; each step must visually complete before the next starts
- Risk tolerance: rendered as a slider (0 = conservative, 100 = aggressive)
- Loading screen shows a live "thinking" message reflecting the current agent's reasoning step

### Exports
- CSV: one row per player in final XI + bench, columns match player schema + `role` (captain/vc/starter/bench)
- JSON: full output object from orchestrator `buildSummary()`

---

## Input Screen Fields

| Field | Type | Default | Validation |
|---|---|---|---|
| Squad (15 players) | Multi-select from pool | Empty | Exactly 15, position counts valid |
| Gameweek | Number (1–38) | 25 | Required |
| Bank | Number (£m) | 0.0 | 0.0–10.0 |
| Free Transfers | Number | 1 | 0–2 |
| Triple Captain | Boolean | true | — |
| Bench Boost | Boolean | true | — |
| Wildcard | Boolean | false | — |
| Free Hit | Boolean | false | — |
| Risk Tolerance | Slider 0–100 | 50 | — |

"Run Optimizer" button is **disabled** until all 15 squad slots are filled with a valid position distribution.

---

## Design Tokens

```
Colors:
  primary:    #00FF87  (FPL green)
  secondary:  #04F5FF  (FPL cyan)
  background: #1A1A2E  (dark navy)
  surface:    #16213E
  card:       #0F3460
  text:       #EAEAEA
  amber:      #FFB703  (injury/medium)
  red:        #E63946  (high FDR / danger)

Typography:
  font-family: 'Inter', sans-serif
  heading: 700 weight
  body: 400 weight

Spacing: 4px base unit (Tailwind defaults)
Border radius: rounded-xl (12px) on cards
```

---

## Demo Flow (Reference)

The prototype must demonstrate this complete flow end-to-end with fake data:

1. User fills Input Screen with the sample squad below
2. Clicks "Run Optimizer" → Loading screen with 3 sequential agent bars
3. Statistician ranks squad → Rice flagged injured, shown in Stats tab
4. Manager selects 4-4-2 XI, recommends Triple Captain Haaland (FDR 2)
5. Transfer Agent recommends Rice → Mbeumo (free transfer, +5.5 net pts)
6. Dashboard shows: current xPts 101.3 → optimized 121.8 → **+20.5 pts gain**

**Sample input squad IDs**: 7 (Raya), 8 (Sels), 5 (A-Arnold), 6 (Porro), 11 (Gvardiol), 15 (van Dijk), + Mykolenko, Salah, Palmer, Mbeumo, Rice, Pereira, Haaland, Isak, Delap

---

## Out of Scope (Prototype)

Do not build these until explicitly instructed:
- Real FPL API calls (`fantasy.premierleague.com`)
- User authentication / saved squads
- Database / persistence layer
- ML model for xPts prediction
- Multi-gameweek horizon planning
- Push notifications
- Deployment / CI pipeline
