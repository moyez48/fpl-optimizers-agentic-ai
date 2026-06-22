import { buildOptimalPitchcraftSquad } from './optimalXI.js'
import { mergePlayerProjectionFields } from './gameweekDisplay.js'

export function transferKey(t) {
  const sellId = t.sell?.element ?? t.sell?.id
  const buyId = t.buy?.element ?? t.buy?.id
  return `${sellId}->${buyId}`
}

export function replacePlayerInSquad(squad, outId, inId) {
  const mapIds = (ids) => (ids || []).map((id) => (id === outId ? inId : id))
  return {
    starting: {
      GKP: mapIds(squad.starting?.GKP),
      DEF: mapIds(squad.starting?.DEF),
      MID: mapIds(squad.starting?.MID),
      FWD: mapIds(squad.starting?.FWD),
    },
    bench: mapIds(squad.bench),
    captain: squad.captain === outId ? inId : squad.captain,
    vice: squad.vice === outId ? inId : squad.vice,
  }
}

/**
 * Apply staged sell→buy rows to the sandbox squad and player pool, then
 * re-run optimal XI formation on the resulting 15.
 */
export function applySelectedTransfers({
  players,
  selectedTransfers,
  resolveBuyPlayer,
}) {
  let pool = players.map((p) => ({ ...p }))

  for (const t of selectedTransfers) {
    const sellId = t.sell?.element ?? t.sell?.id
    const buyId = t.buy?.element ?? t.buy?.id
    if (sellId == null || buyId == null) continue

    const buyRaw = resolveBuyPlayer(buyId, t.buy)
    if (buyRaw) {
      const enriched = mergePlayerProjectionFields({
        ...buyRaw,
        expected_pts: buyRaw.expected_pts ?? t.buy?.expected_pts,
        ep_next: buyRaw.ep_next ?? t.buy?.ep_next,
      })
      const targetId = Number(buyId)
      const existing = pool.find((p) => Number(p.id) === targetId)
      if (existing) {
        pool = pool.map((p) =>
          Number(p.id) === targetId ? mergePlayerProjectionFields({ ...p, ...enriched }) : p,
        )
      } else {
        pool.push(enriched)
      }
    }
    const sellTargetId = Number(sellId)
    pool = pool.filter((p) => Number(p.id) !== sellTargetId)
  }

  const squad = buildOptimalPitchcraftSquad(pool)

  return { squad, players: pool }
}

export function computeTransferHitCost(selectedCount, availableFreeTransfers, activeChip) {
  if (activeChip === 'wildcard' || activeChip === 'freehit') return 0
  return Math.max(0, selectedCount - availableFreeTransfers) * 4
}
