import React, { useState, useMemo } from 'react'

const XPTS_COLOR = (v) => v >= 6 ? 'text-primary' : v >= 3 ? 'text-amber' : 'text-danger'

const DIFF_COLOR = (d) => {
  if (d == null) return 'text-fpl_text/30'
  if (Math.abs(d) <= 1) return 'text-primary'
  if (Math.abs(d) <= 3) return 'text-amber'
  return 'text-danger'
}

const POS_STYLE = {
  GK:  'bg-amber/20 text-amber',
  DEF: 'bg-blue-500/20 text-blue-300',
  MID: 'bg-primary/20 text-primary',
  FWD: 'bg-danger/20 text-danger',
  ALL: 'bg-white/10 text-fpl_text',
}

const POSITION_LIMITS = { GK: 2, DEF: 4, MID: 4, FWD: 3, ALL: 50 }
const POSITIONS = ['FWD', 'MID', 'DEF', 'GK']

const COLS = '1.2rem 1fr 3.2rem 3.2rem 2.5rem'

function PlayerRow({ player, idx, gwHasResults, sortBy }) {
  const showActual = gwHasResults && player.actualPts != null
  const diff = showActual
    ? (player.actualPts - player.adjustedXPts).toFixed(1)
    : null

  return (
    <div
      className={`grid gap-1.5 px-4 py-2.5 border-b border-white/5 last:border-0
        ${player.injured ? 'bg-amber/5' : idx % 2 === 0 ? 'bg-transparent' : 'bg-white/[0.02]'}`}
      style={{ gridTemplateColumns: COLS }}
    >
      <span className="text-[10px] text-fpl_text/30 self-center">{idx + 1}</span>

      <div className="min-w-0 self-center">
        <div className="flex items-center gap-1.5">
          <span className={`text-[9px] font-bold px-1 py-0.5 rounded shrink-0 ${POS_STYLE[player.position] || 'bg-white/10 text-fpl_text/60'}`}>
            {player.position}
          </span>
          <p className="text-xs font-semibold text-fpl_text truncate">{player.name}</p>
          {player.injured && <span className="text-[9px]">⚠️</span>}
        </div>
        <p className="text-[10px] text-fpl_text/40 ml-6">{player.team} · £{player.price}m</p>
      </div>

      {/* xPts */}
      <span className={`text-sm font-black self-center text-right ${sortBy === 'xPts' ? XPTS_COLOR(Number(player.adjustedXPts) || 0) : 'text-fpl_text/50'}`}>
        {Number.isFinite(Number(player.adjustedXPts)) ? Number(player.adjustedXPts).toFixed(1) : '—'}
      </span>

      {/* Actual — real integers once GW is scored; "—" only before data exists */}
      <span className={`text-sm self-center text-right ${showActual ? (sortBy === 'actual' ? 'font-black text-fpl_text' : 'font-bold text-fpl_text/80') : 'text-fpl_text/20'}`}>
        {gwHasResults ? (player.actualPts != null ? player.actualPts : '—') : '—'}
      </span>

      {/* +/- diff */}
      <span className={`text-[10px] font-semibold self-center text-right ${DIFF_COLOR(diff != null ? parseFloat(diff) : null)}`}>
        {diff != null ? (parseFloat(diff) >= 0 ? `+${diff}` : diff) : ''}
      </span>
    </div>
  )
}

function PositionSection({ position, players, limit, gwHasResults, sortBy }) {
  const [expanded, setExpanded] = useState(false)

  const sorted = useMemo(() => {
    if (sortBy === 'actual' && gwHasResults) {
      return [...players].sort((a, b) => {
        const av = a.actualPts
        const bv = b.actualPts
        if (av == null && bv == null) return 0
        if (av == null) return 1
        if (bv == null) return -1
        return bv - av
      })
    }
    return players
  }, [players, sortBy, gwHasResults])

  const visible = expanded ? sorted : sorted.slice(0, limit)
  const hasMore = sorted.length > limit

  return (
    <div className="bg-card rounded-xl border border-white/5 overflow-hidden">
      <button
        onClick={() => hasMore && setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-2.5 border-b border-white/5 hover:bg-white/[0.02] transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${POS_STYLE[position]}`}>
            {position}
          </span>
          <span className="text-xs font-semibold text-fpl_text">
            {position === 'ALL' ? 'All players (by xPts)'
              : position === 'GK' ? 'Goalkeepers'
                : position === 'DEF' ? 'Defenders'
                  : position === 'MID' ? 'Midfielders'
                    : 'Forwards'}
          </span>
          <span className="text-[10px] text-fpl_text/30">
            ({sorted.length})
          </span>
        </div>
        {hasMore && (
          <span className="text-[10px] text-primary/70">
            {expanded ? '▲ Show top' : `▼ All ${sorted.length}`}
          </span>
        )}
      </button>

      {/* Column headers */}
      <div
        className="grid gap-1.5 px-4 py-1.5 border-b border-white/5 bg-white/[0.01]"
        style={{ gridTemplateColumns: COLS }}
      >
        <span className="text-[9px] text-fpl_text/25">#</span>
        <span className="text-[9px] text-fpl_text/25">Player</span>
        <span className={`text-[9px] text-right ${sortBy === 'xPts' ? 'text-primary/60 font-bold' : 'text-fpl_text/25'}`}>xPts</span>
        <span className={`text-[9px] text-right ${sortBy === 'actual' ? 'text-fpl_text/80 font-bold' : 'text-fpl_text/25'}`}>Actual</span>
        <span className="text-[9px] text-fpl_text/25 text-right">+/-</span>
      </div>

      {visible.map((p, i) => (
        <PlayerRow key={p.id} player={p} idx={i} gwHasResults={gwHasResults} sortBy={sortBy} />
      ))}
    </div>
  )
}

export default function StatsScreen({ agentData = null, agentError = null, userInput = null }) {
  const [sortBy, setSortBy] = useState('xPts')

  // Show error state if agent failed and no data
  if (agentError && !agentData) {
    return (
      <div className="flex flex-col gap-4 pb-6">
        <div>
          <p className="text-xs text-fpl_text/40 uppercase tracking-widest">Agent 1 Output</p>
          <p className="text-lg font-black text-fpl_text">Statistician Report</p>
        </div>
        <div className="bg-danger/10 border border-danger/30 rounded-2xl p-6 text-center flex flex-col gap-3">
          <p className="text-danger font-bold text-sm">Agent Error</p>
          <p className="text-xs text-danger/70 font-mono break-words">{agentError}</p>
          <p className="text-[11px] text-fpl_text/40 mt-1">
            Make sure the backend is running:<br />
            <span className="font-mono text-fpl_text/60">python -m uvicorn backend.main:app --port 8006</span>
          </p>
        </div>
      </div>
    )
  }

  if (!agentData) return null

  const { rankedPlayers, injuryAlerts, globalTop11XPts, squadXPts } = agentData

  if (!rankedPlayers?.length) {
    return (
      <div className="flex flex-col gap-4 pb-6">
        <div>
          <p className="text-xs text-fpl_text/40 uppercase tracking-widest">Agent 1 Output</p>
          <p className="text-lg font-black text-fpl_text">Statistician Report</p>
        </div>
        <div className="bg-amber/10 border border-amber/20 rounded-2xl p-6 text-center">
          <p className="text-amber font-bold text-sm">No player rows in stats payload</p>
          <p className="text-[11px] text-fpl_text/50 mt-2">
            Restart the FastAPI server (cache clears on schema change), confirm Vite proxies to the same port (<span className="font-mono">VITE_API_PROXY</span> in <span className="font-mono">app/.env.local</span>), then run the optimizer again.
          </p>
        </div>
      </div>
    )
  }
  const squadTotalXPts = squadXPts ?? globalTop11XPts

  const bucketCount = agentData.byPosition
    ? Object.values(agentData.byPosition).reduce((n, arr) => n + (arr?.length ?? 0), 0)
    : 0
  const byPosition =
    bucketCount > 0 && agentData.byPosition
      ? agentData.byPosition
      : {
          GK:  rankedPlayers.filter(p => p.position === 'GK' || p.position === 'GKP'),
          DEF: rankedPlayers.filter(p => p.position === 'DEF'),
          MID: rankedPlayers.filter(p => p.position === 'MID'),
          FWD: rankedPlayers.filter(p => p.position === 'FWD'),
        }

  const totalInBuckets = POSITIONS.reduce(
    (n, pos) => n + (byPosition[pos]?.length ?? 0),
    0,
  )
  // Stale API cache or missing identity fields → every row position is "—" and all buckets empty.
  // Still show xPts in one list so the screen is never blank while predictions exist.
  const positionSections =
    totalInBuckets === 0 && rankedPlayers.length > 0
      ? [{ pos: 'ALL', players: [...rankedPlayers].sort((a, b) => b.xPts - a.xPts) }]
      : POSITIONS.map(pos => ({ pos, players: byPosition[pos] || [] }))

  const gwHasActualScores = agentData.gwHasActualScores === true

  const squadIds = new Set(userInput?.isLiveData ? (userInput?.squadIds ?? []) : [])
  const squadInjuries = injuryAlerts.filter(p => squadIds.has(p.id))

  return (
    <div className="flex flex-col gap-4 pb-6">
      {/* Header */}
      <div>
        <p className="text-xs text-fpl_text/40 uppercase tracking-widest">Agent 1 Output</p>
        <p className="text-lg font-black text-fpl_text">Statistician Report</p>
        <p className="text-[10px] text-primary/70 mt-0.5">
          {userInput?.isLiveData ? '● Live FPL import' : '● Demo squad'} · xPts model GW{agentData.gameweek}
          {agentData.planningGameweek != null && agentData.planningGameweek !== agentData.gameweek
            ? ` · transfer plan GW${agentData.planningGameweek}`
            : ''}{' '}
          · XGBoost
        </p>
      </div>

      {/* Summary pills */}
      <div className="grid grid-cols-2 gap-2">
        <div className="bg-card rounded-xl p-3 border border-white/5">
          <p className="text-[10px] text-fpl_text/40 uppercase tracking-widest">Squad xPts</p>
          <p className="text-2xl font-black text-fpl_text">{squadTotalXPts}</p>
          <p className="text-[10px] text-fpl_text/40">top 11 by predicted pts</p>
        </div>
        <div className="bg-danger/10 border border-danger/20 rounded-xl p-3">
          <p className="text-[10px] text-danger/70 uppercase tracking-widest">Injury Alerts</p>
          <p className="text-2xl font-black text-danger">{injuryAlerts?.length ?? 0}</p>
          <p className="text-[10px] text-danger/60">
            {injuryAlerts?.length ? (squadInjuries.length ? `${squadInjuries.length} in your squad` : 'See alerts below') : 'All clear'}
          </p>
        </div>
      </div>

      {!gwHasActualScores && (
        <p className="text-[10px] text-fpl_text/40 text-center px-2">
          Actual points show here once this gameweek is in your data (after you run the data refresh).
        </p>
      )}

      {/* Sort toggle */}
      {gwHasActualScores && (
        <div className="flex items-center justify-center gap-1 bg-card rounded-xl p-1 border border-white/5">
          <button
            onClick={() => setSortBy('xPts')}
            className={`flex-1 py-2 rounded-lg text-xs font-semibold transition-all
              ${sortBy === 'xPts' ? 'bg-primary text-background' : 'text-fpl_text/40 hover:text-fpl_text'}`}
          >
            Sort by Predicted xPts
          </button>
          <button
            onClick={() => setSortBy('actual')}
            className={`flex-1 py-2 rounded-lg text-xs font-semibold transition-all
              ${sortBy === 'actual' ? 'bg-primary text-background' : 'text-fpl_text/40 hover:text-fpl_text'}`}
          >
            Sort by Actual Pts
          </button>
        </div>
      )}

      {/* Position sections (or single "All players" if buckets are empty but xPts exist) */}
      {positionSections.map(({ pos, players }) => (
        <PositionSection
          key={pos}
          position={pos}
          players={players}
          limit={POSITION_LIMITS[pos] ?? 50}
          gwHasResults={gwHasActualScores}
          sortBy={sortBy}
        />
      ))}

      {/* Injury alert banner */}
      {injuryAlerts?.length > 0 && (
        <div className="bg-amber/10 border border-amber/20 rounded-xl p-4">
          <p className="text-amber font-bold text-xs mb-2">⚠️ FPL Injury & Availability Alerts</p>
          <div className="flex flex-col gap-1.5">
            {injuryAlerts.map(p => (
              <div key={p.id} className="flex items-start gap-2">
                <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded shrink-0 mt-0.5
                  ${p.statusCode === 'i' ? 'bg-danger/30 text-danger' :
                    p.statusCode === 's' ? 'bg-danger/30 text-danger' :
                    'bg-amber/30 text-amber'}`}>
                  {p.statusLabel}
                </span>
                <div className="min-w-0">
                  <p className="text-xs text-amber/90 font-semibold flex items-center flex-wrap gap-1">
                    {p.name}
                    <span className="text-amber/50 font-normal"> · {p.position} · {p.team}</span>
                    {p.startProb != null && (
                      <span className="text-amber/50 font-normal"> · {(p.startProb * 100).toFixed(0)}% chance</span>
                    )}
                    {squadIds.has(p.id) && (
                      <span className="text-[9px] font-bold bg-danger/30 text-danger px-1.5 py-0.5 rounded ml-1">YOUR SQUAD</span>
                    )}
                  </p>
                  {p.news && <p className="text-[10px] text-amber/50 truncate">{p.news}</p>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
