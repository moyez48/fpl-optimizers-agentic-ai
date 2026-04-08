export const POSITION_LIMITS = {
  GKP: { min: 2, max: 2 },
  DEF: { min: 5, max: 5 },
  MID: { min: 5, max: 5 },
  FWD: { min: 3, max: 3 },
}

export const XI_LIMITS = {
  GKP: { min: 1, max: 1 },
  DEF: { min: 3, max: 5 },
  MID: { min: 2, max: 5 },
  FWD: { min: 1, max: 3 },
}

export function countByPosition(players) {
  return players.reduce((acc, p) => {
    acc[p.position] = (acc[p.position] || 0) + 1
    return acc
  }, {})
}

export function countByTeam(players) {
  return players.reduce((acc, p) => {
    acc[p.team] = (acc[p.team] || 0) + 1
    return acc
  }, {})
}

export function isSquadValid(players) {
  if (players.length !== 15) return false
  const counts = countByPosition(players)
  if ((counts.GKP || 0) !== 2) return false
  if ((counts.DEF || 0) !== 5) return false
  if ((counts.MID || 0) !== 5) return false
  if ((counts.FWD || 0) !== 3) return false
  const teamCounts = countByTeam(players)
  return Object.values(teamCounts).every(c => c <= 3)
}

export function squadErrors(players) {
  const errors = []
  const counts = countByPosition(players)
  if (players.length < 15) errors.push(`Select ${15 - players.length} more player(s)`)
  if ((counts.GKP || 0) < 2) errors.push(`Need ${2 - (counts.GKP || 0)} more GKP`)
  if ((counts.DEF || 0) < 5) errors.push(`Need ${5 - (counts.DEF || 0)} more DEF`)
  if ((counts.MID || 0) < 5) errors.push(`Need ${5 - (counts.MID || 0)} more MID`)
  if ((counts.FWD || 0) < 3) errors.push(`Need ${3 - (counts.FWD || 0)} more FWD`)
  const teamCounts = countByTeam(players)
  Object.entries(teamCounts).forEach(([team, count]) => {
    if (count > 3) errors.push(`Too many players from ${team} (max 3)`)
  })
  return errors
}

export function totalPrice(players) {
  return players.reduce((sum, p) => sum + p.price, 0)
}

/**
 * Select the optimal starting XI from a 15-player squad using a greedy xPts approach.
 * Enforces FPL formation rules: 1 GKP, min 3 DEF / 2 MID / 1 FWD, max 5 DEF / 5 MID / 3 FWD.
 *
 * @param {Array} squadPlayers  — array of player objects with .position and .adjustedXPts
 * @returns {{ xi, bench, captain, viceCaptain, formation }}
 */
export function selectOptimalXI(squadPlayers) {
  const normalize = pos => (pos === 'GKP' ? 'GK' : pos)

  const sorted = [...squadPlayers].sort((a, b) => b.adjustedXPts - a.adjustedXPts)
  const gkps   = sorted.filter(p => normalize(p.position) === 'GK')
  const defs   = sorted.filter(p => p.position === 'DEF')
  const mids   = sorted.filter(p => p.position === 'MID')
  const fwds   = sorted.filter(p => p.position === 'FWD')

  // Mandatory minimums
  const starters = new Set()
  const addN = (players, n) => players.slice(0, n).forEach(p => starters.add(p.id))
  addN(gkps, 1)
  addN(defs, 3)
  addN(mids, 2)
  addN(fwds, 1)

  // Fill 4 flex outfield spots from remaining (sorted by xPts), respecting maxes
  const counts = { GK: 1, DEF: 3, MID: 2, FWD: 1 }
  const maxes  = { GK: 1, DEF: 5, MID: 5, FWD: 3 }

  const remaining = sorted.filter(p => !starters.has(p.id) && normalize(p.position) !== 'GK')
  for (const p of remaining) {
    if (starters.size >= 11) break
    const pos = p.position
    if ((counts[pos] ?? 0) < (maxes[pos] ?? 0)) {
      starters.add(p.id)
      counts[pos] = (counts[pos] ?? 0) + 1
    }
  }

  const xi    = squadPlayers.filter(p => starters.has(p.id))
  const bench = squadPlayers.filter(p => !starters.has(p.id))

  const outfield = xi.filter(p => normalize(p.position) !== 'GK').sort((a, b) => b.adjustedXPts - a.adjustedXPts)
  const captain     = outfield[0] ?? null
  const viceCaptain = outfield[1] ?? null
  const formation = `${counts.DEF}-${counts.MID}-${counts.FWD}`

  return { xi, bench, captain, viceCaptain, formation }
}
