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
