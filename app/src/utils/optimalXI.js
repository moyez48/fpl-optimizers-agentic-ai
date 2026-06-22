/** All legal FPL outfield formations (DEF-MID-FWD). */
export const VALID_FORMATIONS = [
  [3, 4, 3],
  [3, 5, 2],
  [4, 4, 2],
  [4, 3, 3],
  [4, 5, 1],
  [5, 3, 2],
  [5, 4, 1],
]

/**
 * Optimal XI / captaincy always ranks on model xPts — never actual gw_pts.
 * Actual scores are display-only (accountability UI) and must not leak into
 * Manager or Transfer agent decisions.
 */
export function playerOptimalScore(player) {
  return Number(player.xp ?? player.xPts ?? 0)
}

function groupByPosition(players) {
  const groups = { GKP: [], DEF: [], MID: [], FWD: [] }
  for (const p of players) {
    const pos = p.position === 'GK' ? 'GKP' : p.position
    if (groups[pos]) {
      groups[pos].push({
        ...p,
        position: pos,
        _score: playerOptimalScore(p),
      })
    }
  }
  for (const pos of Object.keys(groups)) {
    groups[pos].sort((a, b) => b._score - a._score)
  }
  return groups
}

function scoreFormation(groups, [nDef, nMid, nFwd]) {
  const slots = { GKP: 1, DEF: nDef, MID: nMid, FWD: nFwd }
  const xi = []
  let total = 0
  for (const [pos, count] of Object.entries(slots)) {
    const available = groups[pos] || []
    if (available.length < count) return { total: -Infinity, xi: [], counts: null }
    const chosen = available.slice(0, count)
    xi.push(...chosen)
    total += chosen.reduce((s, p) => s + p._score, 0)
  }
  return {
    total,
    xi,
    counts: { DEF: nDef, MID: nMid, FWD: nFwd },
    formation: `${nDef}-${nMid}-${nFwd}`,
  }
}

/**
 * Build the mathematically best valid FPL XI from 15 squad players.
 * Always uses xPts — past gameweeks still show the model's predicted lineup;
 * actual GW points are surfaced separately in the UI.
 *
 * @returns {{ starting, bench, captain, vice, formation, sortMode }}
 */
export function buildOptimalPitchcraftSquad(players) {
  const pool = (players || []).filter((p) => p?.id != null)
  if (pool.length === 0) {
    return {
      starting: { GKP: [], DEF: [], MID: [], FWD: [] },
      bench: [],
      captain: null,
      vice: null,
      formation: null,
      sortMode: 'foresight',
    }
  }

  const groups = groupByPosition(pool)

  let best = { total: -Infinity, xi: [], counts: null, formation: null }
  for (const fmt of VALID_FORMATIONS) {
    const result = scoreFormation(groups, fmt)
    if (result.total > best.total) best = result
  }

  if (!best.xi.length) {
    return {
      starting: { GKP: [], DEF: [], MID: [], FWD: [] },
      bench: [],
      captain: null,
      vice: null,
      formation: null,
      sortMode: 'foresight',
    }
  }

  const starterIds = new Set(best.xi.map((p) => p.id))
  const bench = pool
    .filter((p) => !starterIds.has(p.id))
    .map((p) => ({ ...p, _score: playerOptimalScore(p) }))
    .sort((a, b) => b._score - a._score)
    .map((p) => p.id)

  const starting = {
    GKP: best.xi.filter((p) => p.position === 'GKP').map((p) => p.id),
    DEF: best.xi.filter((p) => p.position === 'DEF').map((p) => p.id),
    MID: best.xi.filter((p) => p.position === 'MID').map((p) => p.id),
    FWD: best.xi.filter((p) => p.position === 'FWD').map((p) => p.id),
  }

  const outfield = best.xi
    .filter((p) => p.position !== 'GKP')
    .sort((a, b) => b._score - a._score)

  return {
    starting,
    bench,
    captain: outfield[0]?.id ?? null,
    vice: outfield[1]?.id ?? null,
    formation: best.formation,
    sortMode: 'foresight',
  }
}
