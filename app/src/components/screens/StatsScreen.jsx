import React, { useState, useMemo, useRef, useEffect } from 'react'

/** Red “not available” mark: circle with diagonal (prohibition / N/A). */
function ForbiddenMark({ className = '' }) {
  return (
    <svg
      className={`shrink-0 ${className}`}
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <circle cx="12" cy="12" r="9.5" stroke="currentColor" strokeWidth="2" />
      <path d="M7.5 7.5l9 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

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

const ACTUAL_SOURCE_LABEL = {
  fpl_event_live: 'Official FPL API (this gameweek)',
  csv_sanitised: 'Dataset CSV',
  fpl_event_live_csv_gapfill: 'FPL API + CSV where needed',
  none: 'Not available',
}

export default function StatsScreen({
  agentData = null,
  agentError = null,
  agentWarning = null,
  userInput = null,
  statsGwLoading = false,
  onGameweekChange,
  /** Max GW present in the model CSV; future GWs disabled. From API and/or inferred after a failed request. */
  selectableGwMax = null,
}) {
  const [sortBy, setSortBy] = useState('xPts')
  const [gwMenuOpen, setGwMenuOpen] = useState(false)
  const [onlyLikelyToPlay, setOnlyLikelyToPlay] = useState(true)
  const gwPickerRef = useRef(null)

  const rankedPool = agentData?.rankedPlayers

  const displayPlayers = useMemo(() => {
    if (!rankedPool?.length) return []
    if (!onlyLikelyToPlay) return rankedPool
    return rankedPool.filter((p) => {
      if (p.likelyToPlay === true) return true
      if (p.likelyToPlay === false) return false
      return (p.startProb ?? 0) >= 0.12
    })
  }, [rankedPool, onlyLikelyToPlay])

  const globalDisplayTop11XPts = useMemo(() => {
    if (!displayPlayers.length) return 0
    const top11 = [...displayPlayers].sort((a, b) => b.xPts - a.xPts).slice(0, 11)
    return parseFloat(top11.reduce((s, p) => s + p.xPts, 0).toFixed(1))
  }, [displayPlayers])

  const displaySquadXPtsMemo = useMemo(() => {
    const sp = agentData?.squadPlayers
    if (!sp?.length) return null
    const pool = onlyLikelyToPlay
      ? sp.filter((p) => {
          if (p.likelyToPlay === true) return true
          if (p.likelyToPlay === false) return false
          return (p.startProb ?? 0) >= 0.12
        })
      : sp
    if (!pool.length) return 0
    const top11 = [...pool].sort((a, b) => b.xPts - a.xPts).slice(0, 11)
    return parseFloat(top11.reduce((s, p) => s + p.xPts, 0).toFixed(1))
  }, [agentData?.squadPlayers, onlyLikelyToPlay])

  const byPosition = useMemo(
    () => ({
      GK:  displayPlayers.filter(p => p.position === 'GK' || p.position === 'GKP'),
      DEF: displayPlayers.filter(p => p.position === 'DEF'),
      MID: displayPlayers.filter(p => p.position === 'MID'),
      FWD: displayPlayers.filter(p => p.position === 'FWD'),
    }),
    [displayPlayers],
  )

  const positionSections = useMemo(() => {
    const totalInBuckets = POSITIONS.reduce(
      (n, pos) => n + (byPosition[pos]?.length ?? 0),
      0,
    )
    if (totalInBuckets === 0 && displayPlayers.length > 0) {
      return [{ pos: 'ALL', players: [...displayPlayers].sort((a, b) => b.xPts - a.xPts) }]
    }
    return POSITIONS.map(pos => ({ pos, players: byPosition[pos] || [] }))
  }, [byPosition, displayPlayers])

  useEffect(() => {
    if (!gwMenuOpen) return
    const onDocDown = (e) => {
      if (gwPickerRef.current && !gwPickerRef.current.contains(e.target)) {
        setGwMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', onDocDown)
    return () => document.removeEventListener('mousedown', onDocDown)
  }, [gwMenuOpen])

  useEffect(() => {
    if (statsGwLoading) setGwMenuOpen(false)
  }, [statsGwLoading])

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

  const { rankedPlayers } = agentData

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
  const squadTotalXPts = displaySquadXPtsMemo ?? globalDisplayTop11XPts

  const gwHasActualScores = agentData.gwHasActualScores === true
  const dsMin = agentData.datasetMinGw
  /** Upper bound for selectable GWs: dataset max from API, else cap state, else current GW (conservative). */
  const gwCap = selectableGwMax ?? agentData.datasetMaxGw ?? agentData.gameweek ?? null
  const dsMaxLabel = agentData.datasetMaxGw ?? gwCap
  const actualSrcKey = agentData.actualScoresSource
  const actualSrcLabel =
    actualSrcKey && ACTUAL_SOURCE_LABEL[actualSrcKey] ? ACTUAL_SOURCE_LABEL[actualSrcKey] : null

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
        <label className="mt-2 flex items-center gap-2 cursor-pointer select-none">
          <input
            type="checkbox"
            className="rounded border-white/20 bg-background text-primary focus:ring-primary/40"
            checked={onlyLikelyToPlay}
            onChange={() => setOnlyLikelyToPlay((v) => !v)}
          />
          <span className="text-[10px] text-fpl_text/45">
            Likely to play only (start probability ≥ 12% — from minutes, form & FPL injury flags)
          </span>
        </label>
        {onlyLikelyToPlay && (
          <p className="text-[10px] text-fpl_text/35">
            Showing {displayPlayers.length} of {rankedPlayers.length} players · xPts = pred × start%
          </p>
        )}
      </div>

      {agentWarning && (
        <div className="bg-amber/10 border border-amber/25 rounded-xl px-3 py-2">
          <p className="text-[11px] text-amber font-semibold">{agentWarning}</p>
        </div>
      )}

      {agentError && agentData && (
        <div className="bg-danger/10 border border-danger/25 rounded-xl px-3 py-2">
          <p className="text-[11px] text-danger font-semibold">{agentError}</p>
          <p className="text-[10px] text-fpl_text/45 mt-1">Showing the last loaded gameweek above.</p>
        </div>
      )}

      {/* Gameweek selector — custom list so future GWs can be blurred + show prohibition on click */}
      <div className="bg-card rounded-xl p-3 border border-white/5 flex flex-col gap-2">
        <label htmlFor="stats-gw-picker-trigger" className="text-[10px] text-fpl_text/40 uppercase tracking-widest">
          View gameweek
        </label>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative flex-1 min-w-[8rem]" ref={gwPickerRef}>
            <button
              id="stats-gw-picker-trigger"
              type="button"
              disabled={statsGwLoading || typeof onGameweekChange !== 'function'}
              onClick={() => {
                if (statsGwLoading || !onGameweekChange) return
                setGwMenuOpen((o) => !o)
              }}
              aria-expanded={gwMenuOpen}
              aria-haspopup="listbox"
              className="w-full flex items-center justify-between gap-2 bg-background border border-white/10 rounded-lg px-3 py-2 text-sm font-semibold text-fpl_text
                disabled:opacity-50 disabled:cursor-not-allowed
                enabled:hover:border-primary/30 transition-colors
                focus:outline-none focus:ring-1 focus:ring-primary/40"
            >
              <span>GW{agentData.gameweek ?? 1}</span>
              <span className="text-[10px] text-fpl_text/45">{gwMenuOpen ? '▲' : '▼'}</span>
            </button>
            {gwMenuOpen && (
              <ul
                role="listbox"
                aria-labelledby="stats-gw-picker-trigger"
                className="absolute left-0 right-0 top-full z-50 mt-1 max-h-56 overflow-y-auto rounded-lg border border-white/10 bg-surface py-1 shadow-xl"
              >
                {Array.from({ length: 38 }, (_, i) => i + 1).map((gw) => {
                  const locked = gwCap != null && gw > gwCap
                  const selected = (agentData.gameweek ?? 1) === gw
                  return (
                    <li key={gw} role="presentation">
                      <button
                        type="button"
                        role="option"
                        aria-selected={selected}
                        disabled={locked}
                        onClick={() => {
                          onGameweekChange(gw)
                          setGwMenuOpen(false)
                        }}
                        className={`w-full flex items-center justify-between gap-2 px-3 py-2 text-left text-sm transition-colors
                          ${locked
                            ? 'cursor-not-allowed text-fpl_text/35 opacity-50 blur-[0.5px]'
                            : `cursor-pointer hover:bg-white/[0.06] ${selected ? 'text-primary font-bold bg-primary/10' : 'text-fpl_text'}`}`}
                      >
                        <span className={locked ? 'select-none' : ''}>
                          GW{gw}
                          {locked ? ' — N/A' : ''}
                        </span>
                        {locked ? (
                          <ForbiddenMark className="h-3.5 w-3.5 shrink-0 text-danger/70" />
                        ) : selected ? (
                          <span className="text-[10px] text-primary">●</span>
                        ) : (
                          <span className="w-4" />
                        )}
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
          {statsGwLoading && (
            <span className="text-[10px] font-semibold text-primary animate-pulse">Loading…</span>
          )}
        </div>
        {dsMin != null && dsMaxLabel != null && (
          <p className="text-[10px] text-fpl_text/40">
            Model features cover GW{dsMin}–GW{dsMaxLabel} in your CSV. Later gameweeks are disabled until that week exists in your data.
          </p>
        )}
        <p className="text-[10px] text-fpl_text/35">
          xPts = model prediction × start probability.
        </p>
        {actualSrcLabel && (
          <p className="text-[10px] text-fpl_text/35">
            Actual points column: <span className="text-fpl_text/55">{actualSrcLabel}</span>
          </p>
        )}
      </div>

      {/* Summary — squad xPts (injury / availability for your squad is on the Manager tab) */}
      <div className="bg-card rounded-xl p-3 border border-white/5">
        <p className="text-[10px] text-fpl_text/40 uppercase tracking-widest">Squad xPts</p>
        <p className="text-2xl font-black text-fpl_text">{squadTotalXPts}</p>
        <p className="text-[10px] text-fpl_text/40">top 11 by predicted pts</p>
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

      {onlyLikelyToPlay && displayPlayers.length === 0 && rankedPlayers.length > 0 && (
        <div className="bg-amber/10 border border-amber/20 rounded-xl p-3 text-center text-[11px] text-amber">
          No players meet the start-probability threshold. Turn off &quot;Likely to play only&quot; above to see the full list.
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
    </div>
  )
}
