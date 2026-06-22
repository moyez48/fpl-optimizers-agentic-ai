import { VALID_FORMATIONS } from './optimalXI.js'

export function isInStarting(squad, playerId) {
  if (!squad?.starting) return false
  return Object.values(squad.starting).some((ids) => ids.includes(playerId))
}

export function isValidStartingFormation(starting) {
  const nDef = (starting.DEF || []).length
  const nMid = (starting.MID || []).length
  const nFwd = (starting.FWD || []).length
  const nGk = (starting.GKP || []).length
  if (nGk !== 1) return false
  return VALID_FORMATIONS.some(([d, m, f]) => d === nDef && m === nMid && f === nFwd)
}

export function setCaptain(squad, playerId) {
  if (!isInStarting(squad, playerId)) return squad
  const vice = squad.vice === playerId ? null : squad.vice
  return { ...squad, captain: playerId, vice }
}

export function setViceCaptain(squad, playerId) {
  if (!isInStarting(squad, playerId)) return squad
  const captain = squad.captain === playerId ? null : squad.captain
  return { ...squad, captain, vice: playerId }
}

function swapStarterWithBench(squad, starterId, benchId, benchPlayerPos) {
  const pos = benchPlayerPos
  const row = [...(squad.starting[pos] || [])]
  const starterIdx = row.indexOf(starterId)
  if (starterIdx < 0) return null

  const bench = [...(squad.bench || [])]
  const benchIdx = bench.indexOf(benchId)
  if (benchIdx < 0) return null

  row[starterIdx] = benchId
  bench[benchIdx] = starterId

  const starting = { ...squad.starting, [pos]: row }
  if (!isValidStartingFormation(starting)) return null

  let { captain, vice } = squad
  if (captain === starterId) captain = null
  if (vice === starterId) vice = null

  return { ...squad, starting, bench, captain, vice }
}

function swapStartersSameRow(squad, idA, idB, position) {
  const row = [...(squad.starting[position] || [])]
  const iA = row.indexOf(idA)
  const iB = row.indexOf(idB)
  if (iA < 0 || iB < 0) return null
  ;[row[iA], row[iB]] = [row[iB], row[iA]]
  return { ...squad, starting: { ...squad.starting, [position]: row } }
}

function swapBenchOrder(squad, idA, idB) {
  const bench = [...(squad.bench || [])]
  const iA = bench.indexOf(idA)
  const iB = bench.indexOf(idB)
  if (iA < 0 || iB < 0) return null
  ;[bench[iA], bench[iB]] = [bench[iB], bench[iA]]
  return { ...squad, bench }
}

/** Swap two squad players (starter↔bench, same-row, or bench order). */
export function swapPlayers(squad, idA, idB, playersById) {
  if (idA === idB) return squad

  const pA = playersById.get(idA)
  const pB = playersById.get(idB)
  if (!pA || !pB) return squad

  const aStarter = isInStarting(squad, idA)
  const bStarter = isInStarting(squad, idB)

  if (aStarter && bStarter) {
    if (pA.position !== pB.position) return squad
    return swapStartersSameRow(squad, idA, idB, pA.position) || squad
  }

  if (!aStarter && !bStarter) {
    return swapBenchOrder(squad, idA, idB) || squad
  }

  const starterId = aStarter ? idA : idB
  const benchId = aStarter ? idB : idA
  const benchPlayer = playersById.get(benchId)
  const starterPlayer = playersById.get(starterId)
  if (!benchPlayer || !starterPlayer) return squad
  if (benchPlayer.position !== starterPlayer.position) return squad

  return swapStarterWithBench(squad, starterId, benchId, benchPlayer.position) || squad
}
