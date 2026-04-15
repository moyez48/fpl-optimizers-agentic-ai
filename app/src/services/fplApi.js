/**
 * FPL API Service
 *
 * All requests are routed through the Vite dev proxy (/fpl-api → fantasy.premierleague.com/api)
 * to bypass CORS restrictions in the browser.
 *
 * Key endpoints used:
 *   /bootstrap-static/          → all players, teams, positions, gameweek info
 *   /entry/{teamId}/            → manager info (name, team name, overall rank)
 *   /entry/{teamId}/event/{gw}/picks/ → manager's 15-player squad for a given GW
 */

const BASE = '/fpl-api'

// ─── Low-level fetch helper ──────────────────────────────────────────────────

async function apiFetch(path) {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    if (res.status === 404) throw new Error('Not found — check your Team ID and gameweek.')
    throw new Error(`FPL API error (${res.status}). Try again in a moment.`)
  }
  return res.json()
}

// ─── Raw API calls ───────────────────────────────────────────────────────────

export async function fetchBootstrap() {
  return apiFetch('/bootstrap-static/')
}

export async function fetchTeamInfo(teamId) {
  return apiFetch(`/entry/${teamId}/`)
}

export async function fetchTeamPicks(teamId, eventId) {
  return apiFetch(`/entry/${teamId}/event/${eventId}/picks/`)
}

export async function fetchTeamHistory(teamId) {
  return apiFetch(`/entry/${teamId}/history/`)
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Returns the current or next active gameweek object from the events array.
 */
export function getCurrentEvent(events) {
  const current = events.find(e => e.is_current)
  const next = events.find(e => e.is_next)
  return current || next || events[events.length - 1]
}

/**
 * Converts FPL element_type id → our position string.
 * FPL: 1=GKP, 2=DEF, 3=MID, 4=FWD
 */
const FPL_POSITION_MAP = { 1: 'GKP', 2: 'DEF', 3: 'MID', 4: 'FWD' }

/**
 * Map a single FPL player element to our app's player schema.
 */
function transformElement(element, posMap, teamMap) {
  const pos = posMap[element.element_type] || 'MID'
  const teamInfo = teamMap[element.team] || {}

  // FPL status codes: 'a'=available, 'd'=doubtful, 'i'=injured, 's'=suspended, 'u'=unavailable
  const injured = element.status === 'i' || element.status === 's'

  // Seed variance from player's cost/form to make it deterministic but varied
  const variance = 1.5 + (element.now_cost % 7) * 0.5

  return {
    id: element.id,
    name: `${element.first_name} ${element.second_name}`,
    position: pos,
    team: teamInfo.name || 'Unknown',
    teamShort: teamInfo.shortName || '???',
    price: element.now_cost / 10,
    form: parseFloat(element.form) || 0,
    // ep_next is the FPL model's expected points for the next GW
    xPts: parseFloat(element.ep_next) || 0,
    xG: parseFloat(element.expected_goals_per_90) || 0,
    xA: parseFloat(element.expected_assists_per_90) || 0,
    // Fixture difficulty requires a separate /fixtures/ call; default to 3 (medium)
    fixtureDifficulty: 3,
    nextFixture: 'TBC',
    injured,
    ownership: parseFloat(element.selected_by_percent) || 0,
    variance,
    // Extra real data fields (bonus, not in fake schema)
    totalPoints: element.total_points,
    minutes: element.minutes,
    goalsScored: element.goals_scored,
    assists: element.assists,
    cleanSheets: element.clean_sheets,
    statusCode: element.status,
    news: element.news || '',
  }
}

/**
 * Transforms the full bootstrap-static response into our player array.
 * Filters out players who have left their clubs (status 'u' with 0 minutes).
 */
export function transformPlayers(bootstrap) {
  const { elements, element_types, teams } = bootstrap

  // Build lookup maps
  const posMap = Object.fromEntries(
    element_types.map(et => [et.id, FPL_POSITION_MAP[et.id] || 'MID'])
  )
  const teamMap = Object.fromEntries(
    teams.map(t => [t.id, { name: t.name, shortName: t.short_name }])
  )

  return elements
    .filter(p => p.status !== 'u') // exclude departed players
    .map(p => transformElement(p, posMap, teamMap))
}

// ─── History helpers ──────────────────────────────────────────────────────────

/**
 * Compute how many free transfers the manager has available for the upcoming GW.
 * Rules:
 *  - Start at 1 FT from GW1.
 *  - Each GW: if transfers <= FTs available → FTs = min(FTs - transfers + 1, 5)
 *                            else (hit taken) → FTs = 1
 *  - Wildcard / Free Hit resets FTs to 1 for the following GW.
 */
function computeFreeTransfers(historyData) {
  const { current = [], chips = [] } = historyData
  const chipsByGw = Object.fromEntries(chips.map(c => [c.event, c.name]))

  let fts = 1
  for (const gw of current) {
    const chip = chipsByGw[gw.event]
    const transfers = gw.event_transfers || 0

    if (chip === 'wildcard' || chip === 'freehit') {
      fts = 1
    } else if (transfers <= fts) {
      fts = Math.min(fts - transfers + 1, 5)
    } else {
      fts = 1 // hit taken — still earn 1 FT for next GW
    }
  }
  return fts
}

/**
 * Determine which chips are still available.
 * - Triple Captain (3xc), Bench Boost (bboost), Free Hit (freehit): once per season.
 * - Wildcard: once per half-season (GWs 1-19 first half, GWs 20-38 second half).
 */
function computeAvailableChips(historyData, currentGw) {
  const { chips = [] } = historyData
  const usedChipNames = new Set(chips.map(c => c.name))

  const firstHalfBoundary = 19
  const inSecondHalf = currentGw > firstHalfBoundary
  const wildcardUsedFirstHalf  = chips.some(c => c.name === 'wildcard' && c.event <= firstHalfBoundary)
  const wildcardUsedSecondHalf = chips.some(c => c.name === 'wildcard' && c.event >  firstHalfBoundary)
  const wildcardAvailable = inSecondHalf ? !wildcardUsedSecondHalf : !wildcardUsedFirstHalf

  return {
    tripleCaptain: !usedChipNames.has('3xc'),
    benchBoost:    !usedChipNames.has('bboost'),
    wildcard:      wildcardAvailable,
    freeHit:       !usedChipNames.has('freehit'),
  }
}

// ─── Main import function ─────────────────────────────────────────────────────

/**
 * Full team import flow:
 *  1. Fetch bootstrap-static (all players + current GW)
 *  2. Fetch team info + season history in parallel
 *  3. Fetch picks for current GW
 *  4. Derive bank, free transfers, and chip availability from real data
 *  5. Return transformed player pool + squad IDs + metadata
 *
 * @param {number|string} teamId  - FPL manager team ID (visible in FPL URL)
 * @returns {Promise<{
 *   players: Array,
 *   squadIds: number[],
 *   teamInfo: object,
 *   gameweek: number,
 *   bank: number,
 *   freeTransfers: number,
 *   chips: { tripleCaptain: boolean, benchBoost: boolean, wildcard: boolean, freeHit: boolean },
 * }>}
 */
export async function importFPLTeam(teamId) {
  const id = parseInt(teamId, 10)
  if (!id || id <= 0) throw new Error('Enter a valid Team ID (positive integer).')

  // Step 1: Bootstrap + team info + history in parallel
  const [bootstrap, teamInfo, historyData] = await Promise.all([
    fetchBootstrap(),
    fetchTeamInfo(id),
    fetchTeamHistory(id),
  ])

  // Step 2: Determine current GW
  const currentEvent = getCurrentEvent(bootstrap.events)
  const gameweek = currentEvent.id

  // Step 3: Picks for that GW
  const picksData = await fetchTeamPicks(id, gameweek)

  // Step 4: Transform full player pool
  const players = transformPlayers(bootstrap)
  const playerMap = new Map(players.map(p => [p.id, p]))

  // Step 5: Extract squad player IDs in pick order
  const rawSquadIds = picksData.picks.map(p => p.element)
  const squadIds = rawSquadIds.filter(elemId => playerMap.has(elemId))

  // Step 6: Derive bank, free transfers, and chip availability
  const bank = (picksData.entry_history?.bank ?? 0) / 10
  const freeTransfers = computeFreeTransfers(historyData)
  const chips = computeAvailableChips(historyData, gameweek)

  return {
    players,
    squadIds,
    teamInfo: {
      id: teamInfo.id,
      teamName: teamInfo.name,
      managerName: `${teamInfo.player_first_name} ${teamInfo.player_last_name}`,
      overallPoints: teamInfo.summary_overall_points,
      overallRank: teamInfo.summary_overall_rank,
    },
    gameweek,
    bank,
    freeTransfers,
    chips,
  }
}
