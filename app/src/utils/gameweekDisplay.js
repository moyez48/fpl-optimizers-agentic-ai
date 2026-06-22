/**
 * Gameweek display modes for the accountability pitch UI.
 *
 * - foresight: no GW context — show prediction only
 * - future: selected GW is after the live FPL round — prediction only
 * - accountability: past or active GW — show actual pts alongside xP
 */

export function pitchDisplayMode(selectedGw, currentActiveGw) {
  if (selectedGw == null || currentActiveGw == null) return 'foresight'
  if (Number(selectedGw) > Number(currentActiveGw)) return 'future'
  return 'accountability'
}

export function shouldPollLiveScores(selectedGw, currentActiveGw) {
  if (selectedGw == null || currentActiveGw == null) return false
  return Number(selectedGw) === Number(currentActiveGw)
}

export function playerActualPts(player) {
  const raw = player?.gw_points ?? player?.gw_pts
  if (raw == null || raw === '') return null
  return Number(raw)
}

/**
 * Canonical xPts for Pitch + sidebar. Pitch reads ``xp`` / ``xPts`` only;
 * global pool may also supply model / FPL keys from transfers or bootstrap.
 */
export function resolvePlayerXpts(raw) {
  if (!raw) return 0
  const candidates = [
    raw.xPts,
    raw.xp,
    raw.predicted_points,
    raw.expected_pts,
    raw.ep_next,
    raw.ep_this,
  ]
  for (const val of candidates) {
    if (val == null || val === '') continue
    const n = Number(val)
    if (Number.isFinite(n)) return n
  }
  return 0
}

export function mergePlayerProjectionFields(raw) {
  const xPts = resolvePlayerXpts(raw)
  const gwPts = raw?.gw_pts ?? raw?.gw_points ?? null
  return {
    ...raw,
    xp: xPts,
    xPts,
    gw_pts: gwPts,
    gw_points: gwPts,
  }
}

export function playerProjectedXp(player) {
  return resolvePlayerXpts(player)
}
