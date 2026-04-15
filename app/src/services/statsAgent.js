/**
 * statsAgent.js
 * =============
 * Frontend client for the FastAPI Stats Agent backend.
 *
 * fetchStats()   — POST /api/stats → raw agent response
 * adaptToStatsOutput() — transform agent response to StatsScreen shape
 */

/**
 * Call the Stats Agent API.
 * @param {Object} opts
 * @param {number|null} opts.gameweek  - Target GW (null = auto-detect latest)
 * @param {string}      opts.season    - e.g. "2024-25"
 * @returns {Promise<Object>}          - Raw agent response
 */
/**
 * FastAPI may return `detail` as a string, validation array, or object.
 */
export function extractStatsApiDetail(body) {
  if (!body || typeof body !== 'object') return null
  const d = body.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d)) {
    return d.map((x) => (x && typeof x === 'object' ? x.msg ?? JSON.stringify(x) : String(x))).join('; ')
  }
  if (d && typeof d === 'object') {
    return d.message ?? d.msg ?? JSON.stringify(d)
  }
  return body.message ?? body.error ?? null
}

/**
 * When the model has no rows for GW33 but the CSV ends at GW31, the backend
 * returns a long `run_model: no feature rows...` string — normalize for UI.
 */
export function friendlyStatsLoadError(raw) {
  const s = String(raw ?? '')
  const range = s.match(/GW1\s*[–-]\s*GW(\d+)/i)
  const noRows = s.match(/no feature rows for\s+[^\s]+\s+GW(\d+)/i)
  if (range && noRows) {
    const hi = range[1]
    const asked = noRows[1]
    return `Gameweek ${asked} is not in your processed dataset yet (your CSV runs through GW${hi}). Update the data pipeline or choose GW1–GW${hi}.`
  }
  return s.replace(/^run_model:\s*/i, '').trim() || s
}

/** After a failed load, use this so the GW dropdown can disable future weeks. Works on raw API text and friendlyStatsLoadError output. */
export function parseDatasetGwMaxFromStatsError(message) {
  if (!message) return null
  const s = String(message)
  const patterns = [/GW1\s*[–-]\s*GW(\d+)/i, /through GW(\d+)/i, /choose GW1\s*[–-]\s*GW(\d+)/i]
  for (const re of patterns) {
    const m = s.match(re)
    if (m) return parseInt(m[1], 10)
  }
  return null
}

export async function fetchStats({ gameweek = null, season = null } = {}) {
  const res = await fetch('/api/stats', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ gameweek, season }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const raw = extractStatsApiDetail(body) ?? `Stats API returned ${res.status}`
    throw new Error(friendlyStatsLoadError(raw))
  }
  return res.json()
}

/** Align with backend single-GW bounds; drop season totals if they slip through. */
const ACTUAL_PTS_SANITY_MIN = -25
const ACTUAL_PTS_SANITY_MAX = 30

/** Prefer backend `actual_points`, then legacy `total_points`. */
function pickActualPoints(p) {
  const raw = p.actual_points ?? p.total_points
  if (raw === null || raw === undefined) return null
  const n = Number(raw)
  if (!Number.isFinite(n)) return null
  const r = Math.round(n)
  if (r < ACTUAL_PTS_SANITY_MIN || r > ACTUAL_PTS_SANITY_MAX) return null
  return r
}

/** Stable £m / xPts numbers for UI (avoids NaN breaking .toFixed). */
function finiteFixed(raw, digits = 1) {
  const n = Number(raw)
  if (!Number.isFinite(n)) return 0
  return parseFloat(n.toFixed(digits))
}

/** Display bucket: GK/GKP → GK, AM → MID, etc. */
function normalizePositionCode(pos) {
  const u = String(pos ?? '').trim().toUpperCase()
  if (u === 'GKP') return 'GK'
  if (u === 'AM') return 'MID'
  if (['GK', 'DEF', 'MID', 'FWD'].includes(u)) return u
  return u || '—'
}

/** Only real FPL outfield lines; unknown codes are not lumped into MID. */
function bucketPosition(pos) {
  const b = normalizePositionCode(pos)
  if (b === 'GK' || b === 'DEF' || b === 'MID' || b === 'FWD') return b
  return null
}

function deriveByPositionFromRanked(players) {
  return {
    GK:  players.filter(p => bucketPosition(p.position) === 'GK'),
    DEF: players.filter(p => bucketPosition(p.position) === 'DEF'),
    MID: players.filter(p => bucketPosition(p.position) === 'MID'),
    FWD: players.filter(p => bucketPosition(p.position) === 'FWD'),
  }
}


/**
 * Call the Sporting Director (transfers) API.
 * @param {Object} opts
 * @param {number[]} opts.playerIds    - 15 FPL element IDs (manager's squad)
 * @param {number}   opts.bank         - £m in bank
 * @param {number}   opts.freeTransfers
 * @param {number|null} opts.gameweek
 * @param {string}   opts.season
 * @returns {Promise<Object>}          - Raw transfers response
 */
/**
 * Run Manager Agent v2 (optimal XI, captain/VC, chips).
 */
export async function fetchManager({
  playerIds,
  bank = 0,
  gameweek = null,
  season = null,
  tripleCaptain = true,
  benchBoost = true,
} = {}) {
  const res = await fetch('/api/manager', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      player_ids: playerIds,
      bank,
      gameweek,
      season,
      triple_captain: tripleCaptain,
      bench_boost: benchBoost,
    }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Manager API returned ${res.status}`)
  }
  return res.json()
}

export async function fetchTransfers({ playerIds, bank = 0, freeTransfers = 1, gameweek = null, season = null } = {}) {
  const res = await fetch('/api/transfers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      player_ids: playerIds,
      bank,
      free_transfers: freeTransfers,
      gameweek,
      season,
    }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Transfers API returned ${res.status}`)
  }
  return res.json()
}

/**
 * Transform the raw transfers response into the shape ManagerScreen expects.
 */
export function adaptToTransferOutput(apiResponse) {
  const mapOne = (t, i) => {
    const isFree = t.transfer_cost_points === 0
    const netGain = parseFloat((t.net_expected_gain ?? 0).toFixed(1))
    const score = t.score ?? 0
    const priority = score >= 3 ? 'HIGH' : score >= 1.5 ? 'MEDIUM' : 'LOW'

    return {
      out: {
        id:       t.sell?.element ?? i,
        name:     t.sell?.name ?? '—',
        position: t.sell?.position ?? '—',
        price:    parseFloat((t.sell?.cost ?? 0).toFixed(1)),
        xPts:     parseFloat((t.sell?.expected_pts ?? 0).toFixed(1)),
      },
      in: {
        id:       t.buy?.element ?? i,
        name:     t.buy?.name ?? '—',
        position: t.buy?.position ?? '—',
        team:     t.buy?.team ?? '—',
        price:    parseFloat((t.buy?.cost ?? 0).toFixed(1)),
        xPts:     parseFloat((t.buy?.expected_pts ?? 0).toFixed(1)),
      },
      xPtsGain:        parseFloat((t.expected_gain ?? 0).toFixed(1)),
      hitCost:         t.transfer_cost_points ?? 0,
      netGain,
      isFreeTransfer:  isFree,
      priority,
      reasoning:       t.reasoning ?? '',
      // Alternative buy targets for the same sell player (#2 and #3 by tiebreaker)
      alternatives:    (t.alternatives ?? []).map((alt) => mapOne(alt, i)),
    }
  }

  const normalizeTransfers = (apiResponse.transfers || []).map((t, i) => mapOne(t, i))
  const groupedByOut = new Map()

  const mergeTransfer = (candidate) => {
    const outId = candidate?.out?.id
    if (outId == null) return

    const existing = groupedByOut.get(outId)
    if (!existing) {
      groupedByOut.set(outId, {
        ...candidate,
        alternatives: [...(candidate.alternatives || [])],
      })
      return
    }

    // Keep the stronger candidate as primary for this outgoing player.
    const existingScore = existing.netGain ?? Number.NEGATIVE_INFINITY
    const candidateScore = candidate.netGain ?? Number.NEGATIVE_INFINITY
    const keepCandidatePrimary = candidateScore > existingScore

    const primary = keepCandidatePrimary ? candidate : existing
    const secondary = keepCandidatePrimary ? existing : candidate
    const mergedAlternatives = [
      ...(primary.alternatives || []),
      secondary,
      ...(secondary.alternatives || []),
    ]

    // Dedupe alternatives by incoming player and remove the primary incoming pick.
    const seenIn = new Set([primary.in?.id])
    const dedupedAlternatives = []
    for (const alt of mergedAlternatives) {
      const inId = alt?.in?.id
      if (inId == null || seenIn.has(inId)) continue
      seenIn.add(inId)
      dedupedAlternatives.push({
        ...alt,
        alternatives: [],
      })
    }

    groupedByOut.set(outId, {
      ...primary,
      alternatives: dedupedAlternatives,
    })
  }

  for (const t of normalizeTransfers) {
    mergeTransfer(t)
  }

  const transfers = [...groupedByOut.values()].sort((a, b) => (b.netGain ?? 0) - (a.netGain ?? 0))

  return {
    transfers,
    holdFlag:     Boolean(apiResponse.hold_flag),
    wildcardFlag: Boolean(apiResponse.wildcard_flag),
    summary:      apiResponse.summary ?? '',
    gameweek:     apiResponse.gameweek,
    /** Next FPL round the Sporting Director targets (stats `gameweek` + 1). */
    planningGameweek: apiResponse.planning_gameweek ?? null,
  }
}

/**
 * Map Manager Agent v2 API response → UI shape (aligned with PitchPlayerCard / formations).
 */
export function adaptToManagerOutput(api) {
  if (!api || api.detail) return null

  const toPitchPlayer = (p) => ({
    id: p.id,
    name: p.name,
    position: p.position === 'GK' ? 'GKP' : p.position,
    team: p.team || '—',
    adjustedXPts: typeof p.xP === 'number' ? p.xP : parseFloat(p.xP) || 0,
    injured: false,
    benchOrder: p.bench_order,
  })

  const xi = (api.starting_xi || []).map(toPitchPlayer)
  const bench = [...(api.bench || [])]
    .sort((a, b) => (a.bench_order ?? 0) - (b.bench_order ?? 0))
    .map(toPitchPlayer)

  return {
    formation: api.formation,
    projectedPoints: api.projected_points,
    captain: api.captain,
    captainId: api.captain_id,
    viceCaptain: api.vice_captain,
    viceCaptainId: api.vice_captain_id,
    xi,
    bench,
    chipRecommendation: api.chip_recommendation,
    summary: api.summary ?? '',
    gameweek: api.gameweek,
    log: api.log || [],
  }
}

/**
 * Transform the raw agent response into the shape StatsScreen expects.
 *
 * Returns:
 *   rankedPlayers   - ALL players sorted by expected_pts
 *   byPosition      - { GK: [...], DEF: [...], MID: [...], FWD: [...] }
 *   injuryAlerts, squadPlayers, squadXPts, globalTop11XPts, captainShortlist, gameweek
 */
export function adaptToStatsOutput(apiResponse, squadIds = null) {
  const formMap = {}
  for (const f of apiResponse.form_stats || []) {
    formMap[f.name] = f
  }

  // Build injury lookup FIRST so mapPlayer can use it
  const STATUS_LABEL = { d: 'Doubtful', i: 'Injured', s: 'Suspended', u: 'Unavailable' }
  let injuryAlerts = (apiResponse.injury_alerts || []).map(p => ({
    id:          p.element,
    name:        p.name,
    team:        p.team,
    position:    p.position,
    injured:     true,
    statusCode:  p.status,
    statusLabel: STATUS_LABEL[p.status] || p.status,
    news:        p.news,
    startProb:   p.chance_of_playing_next_round != null ? p.chance_of_playing_next_round / 100 : null,
  }))
  if (squadIds?.length) {
    const squadSet = new Set(squadIds)
    injuryAlerts = injuryAlerts.filter((a) => squadSet.has(a.id))
  } else {
    injuryAlerts = []
  }
  const injuredElementIds = new Set(injuryAlerts.map(p => p.id))

  function mapPlayer(p, form) {
    const gws = Math.max(form.form_gws?.length || 5, 1)
    const xPtsCore = finiteFixed(p.expected_pts ?? p.predicted_pts ?? 0, 1)
    return {
      id:            p.element ?? p.name,
      name:          p.name ?? '—',
      position:      normalizePositionCode(p.position),
      team:          p.team || '—',
      xPts:          xPtsCore,
      adjustedXPts:  xPtsCore,
      predictedPts:  finiteFixed(p.predicted_pts ?? 0, 1),
      actualPts:     pickActualPoints(p),
      startProb:     finiteFixed(p.start_prob ?? 0.25, 2),
      form:          finiteFixed(form.avg_pts_last5 ?? 0, 1),
      formTrend:     finiteFixed(form.form_trend ?? 0, 2),
      xG:            finiteFixed((form.goals_last5 ?? 0) / gws, 2),
      xA:            finiteFixed((form.assists_last5 ?? 0) / gws, 2),
      avgMinutes:    finiteFixed(form.avg_minutes_last5 ?? 0, 0),
      price:         finiteFixed(
        p.value_m ??
          (p.value != null
            ? (Number(p.value) >= 25 ? Number(p.value) / 10 : Number(p.value))
            : 0),
        1
      ),
      fdr:           finiteFixed(p.fdr ?? 3, 1),
      fixtureDifficulty: finiteFixed(p.fdr ?? 3, 1),
      nextFixture:   '—',
      ownership:     0,
      variance:      finiteFixed((p.predicted_pts ?? 0) * 0.3, 1),
      injured:       p.element != null && injuredElementIds.has(p.element),
      rank:          p.rank ?? 0,
      likelyToPlay:
        p.likely_to_play != null ? Boolean(p.likely_to_play) : (p.start_prob ?? 0) >= 0.12,
    }
  }

  const mapList = (list) => (list || []).map(p => mapPlayer(p, formMap[p.name] || {}))

  const rankedPlayers = mapList(apiResponse.ranked?.ALL)

  let byPosition = {
    GK:  mapList(apiResponse.ranked?.GK),
    DEF: mapList(apiResponse.ranked?.DEF),
    MID: mapList(apiResponse.ranked?.MID),
    FWD: mapList(apiResponse.ranked?.FWD),
  }

  const bucketTotal =
    byPosition.GK.length +
    byPosition.DEF.length +
    byPosition.MID.length +
    byPosition.FWD.length

  // Backend sometimes omits per-position keys or returns empty slices while
  // ranked.ALL is populated — StatsScreen used to prefer empty byPosition and
  // showed no players. Rebuild from ALL when buckets are empty.
  if (bucketTotal === 0 && rankedPlayers.length > 0) {
    byPosition = deriveByPositionFromRanked(rankedPlayers)
  }

  // Squad-specific stats (only for live FPL import with real element IDs)
  let squadPlayers = null
  let squadXPts = null
  if (squadIds?.length) {
    const byElement = new Map(rankedPlayers.map(p => [p.id, p]))
    squadPlayers = squadIds.map(id => byElement.get(id)).filter(Boolean)
    if (squadPlayers.length > 0) {
      const top11 = [...squadPlayers].sort((a, b) => b.xPts - a.xPts).slice(0, 11)
      squadXPts = parseFloat(top11.reduce((s, p) => s + p.xPts, 0).toFixed(1))
    }
  }

  const top11 = rankedPlayers.slice(0, 11)
  const globalTop11XPts = parseFloat(top11.reduce((s, p) => s + p.xPts, 0).toFixed(1))

  const captainShortlist = (apiResponse.captain_shortlist || []).map(p => ({
    name:         p.name,
    team:         p.team || '—',
    position:     p.position || '—',
    expectedPts:  parseFloat((p.expected_pts ?? 0).toFixed(1)),
    startProb:    parseFloat((p.start_prob ?? 0).toFixed(2)),
  }))

  const gwHasActualScores = Boolean(apiResponse.gw_has_actual_scores)

  return {
    rankedPlayers,
    byPosition,
    injuryAlerts,
    squadPlayers,
    squadXPts,
    globalTop11XPts,
    captainShortlist,
    gameweek:             apiResponse.gameweek,
    gwHasActualScores,
    datasetMinGw:         apiResponse.dataset_gw_min ?? null,
    datasetMaxGw:         apiResponse.dataset_gw_max ?? null,
    actualScoresSource:   apiResponse.actual_scores_source ?? null,
    gwFallbackWarning:    apiResponse.gw_fallback_warning ?? null,
  }
}
