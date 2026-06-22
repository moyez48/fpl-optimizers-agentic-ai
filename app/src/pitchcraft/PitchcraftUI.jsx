import React from 'react'
import { pitchcraftApiUrl } from '../lib/pitchcraftApi.js'
import { transferKey } from '../utils/transferApply.js'
import {
  pitchDisplayMode,
  playerActualPts,
  playerProjectedXp,
} from '../utils/gameweekDisplay.js'

/** Shirt colours — keyed by full club name fragments */
export const TEAMS = {
  Arsenal: { short: 'ARS', primary: '#EF0107' },
  Liverpool: { short: 'LIV', primary: '#C8102E' },
  Chelsea: { short: 'CHE', primary: '#034694' },
  'Man City': { short: 'MCI', primary: '#6CABDD' },
  'Man Utd': { short: 'MUN', primary: '#DA291C' },
  Spurs: { short: 'TOT', primary: '#132257' },
  Newcastle: { short: 'NEW', primary: '#241F20' },
  'Aston Villa': { short: 'AVL', primary: '#670E36' },
  Brighton: { short: 'BHA', primary: '#0057B8' },
  Brentford: { short: 'BRE', primary: '#E30613' },
  Fulham: { short: 'FUL', primary: '#000000' },
  West: { short: 'WHU', primary: '#7A263A' },
  'West Ham': { short: 'WHU', primary: '#7A263A' },
  Everton: { short: 'EVE', primary: '#003399' },
  'Crystal Palace': { short: 'CRY', primary: '#1B458F' },
  Bournemouth: { short: 'BOU', primary: '#DA291C' },
  Wolves: { short: 'WOL', primary: '#FDB913' },
  Southampton: { short: 'SOU', primary: '#D71920' },
  Leicester: { short: 'LEI', primary: '#003090' },
  Ipswich: { short: 'IPS', primary: '#003399' },
  'Nottm Forest': { short: 'NFO', primary: '#DD0000' },
  Unknown: { short: '???', primary: '#555555' },
}

function teamStyle(teamName) {
  if (!teamName) return TEAMS.Unknown
  const hit = Object.keys(TEAMS).find((k) => teamName.includes(k))
  return TEAMS[hit] || { short: teamName.slice(0, 3).toUpperCase(), primary: '#4a5568' }
}

const POSITION_ROWS = ['FWD', 'MID', 'DEF', 'GKP']
const KIT_SIZE = 220

export function fplKitUrl(teamCode, isGoalkeeper, ext = 'webp', size = KIT_SIZE) {
  if (teamCode == null) return null
  const file = isGoalkeeper
    ? `shirt_${teamCode}_1-${size}.${ext}`
    : `shirt_${teamCode}-${size}.${ext}`
  return `https://fantasy.premierleague.com/dist/img/shirts/standard/${file}`
}

export function PlayerKitImg({
  teamCode,
  elementType,
  position,
  className = '',
  fallbackColor,
}) {
  const isGk =
    Number(elementType) === 1 ||
    position === 'GKP' ||
    position === 'GK'
  const [kitExt, setKitExt] = React.useState('webp')
  const kitUrl = fplKitUrl(teamCode, isGk, kitExt)
  const [kitFailed, setKitFailed] = React.useState(false)

  React.useEffect(() => {
    setKitFailed(false)
    setKitExt('webp')
  }, [teamCode, isGk])

  const handleKitError = () => {
    if (kitExt === 'webp') setKitExt('png')
    else setKitFailed(true)
  }

  if (!teamCode || kitFailed) {
    return (
      <span
        className={`pkit-fallback ${className}`.trim()}
        style={fallbackColor ? { background: fallbackColor } : undefined}
        aria-hidden
      />
    )
  }

  return (
    <img
      className={className}
      src={kitUrl}
      alt=""
      loading="lazy"
      onError={handleKitError}
    />
  )
}

export function EditActionMenu({ onCaptain, onVice, onSwap, onCancel, showCaptainActions }) {
  return (
    <div
      className="edit-popover"
      role="menu"
      onClick={(e) => e.stopPropagation()}
    >
      {showCaptainActions && (
        <>
          <button type="button" className="edit-popover-btn" onClick={onCaptain}>
            ⭐ Captain
          </button>
          <button type="button" className="edit-popover-btn" onClick={onVice}>
            🔼 Vice
          </button>
        </>
      )}
      <button type="button" className="edit-popover-btn" onClick={onSwap}>
        🔄 Swap
      </button>
      <button type="button" className="edit-popover-btn" onClick={onCancel}>
        ✕ Cancel
      </button>
    </div>
  )
}

export function PlayerChip({
  player,
  isCaptain,
  isVice,
  onClick,
  theme,
  isEditMode,
  isSelected,
  isSwapSource,
  showEditMenu,
  onSetCaptain,
  onSetVice,
  onStartSwap,
  onCancelEdit,
  selectedGw,
  currentActiveGw,
}) {
  const team = teamStyle(player.team)
  const gwXp = playerProjectedXp(player)
  const actualPts = playerActualPts(player)
  const displayMode = pitchDisplayMode(selectedGw, currentActiveGw)
  const displayName = player.web_name || player.name || 'Unknown'
  const showKit = player.team_code != null
  const highlighted = isSelected || isSwapSource
  const teamCode = player.teamShort || team.short

  return (
    <div className={`pchip-slot${highlighted ? ' pchip-slot-active' : ''}`}>
      <button
        className={`pchip pchip-${theme}${isEditMode ? ' pchip-edit' : ''}${highlighted ? ' pchip-selected' : ''}`}
        onClick={onClick}
        type="button"
      >
      <div
        className={`pchip-shirt pchip-shirt-kit${showKit ? '' : ' pchip-shirt-fallback'}`}
        style={!showKit ? { '--team': team.primary } : undefined}
      >
        {showKit ? (
          <PlayerKitImg
            teamCode={player.team_code}
            elementType={player.element_type}
            position={player.position}
            className="pchip-kit"
            fallbackColor={team.primary}
          />
        ) : (
          <div className="pchip-shirt-stripe" style={{ '--team': team.primary }} />
        )}
        {isCaptain && <span className="pchip-badge pchip-cap">C</span>}
        {isVice && <span className="pchip-badge pchip-vice">V</span>}
      </div>
      <div className="pchip-name">{displayName}</div>
      <div
        className={`pchip-meta${displayMode === 'accountability' ? ' pchip-meta-accountability' : ''}`}
      >
        {displayMode === 'accountability' ? (
          <>
            <span className="pchip-actual">{actualPts ?? 0} Pts</span>
            <span className="pchip-meta-sep" aria-hidden="true">
              |
            </span>
            <span className="pchip-xp">{gwXp.toFixed(1)} xP</span>
          </>
        ) : (
          <>
            <span className="pchip-club">{teamCode}</span>
            <span className="pchip-meta-dot" aria-hidden="true">
              ·
            </span>
            <span className="pchip-xp">{gwXp.toFixed(1)} xP</span>
          </>
        )}
      </div>
      </button>
      {isEditMode && showEditMenu && (
        <EditActionMenu
          showCaptainActions
          onCaptain={onSetCaptain}
          onVice={onSetVice}
          onSwap={onStartSwap}
          onCancel={onCancelEdit}
        />
      )}
    </div>
  )
}

export function PitchView({
  squad,
  players,
  selectedGw,
  currentActiveGw,
  onPlayerClick,
  theme,
  layoutKey,
  isEditMode,
  activeEditPlayer,
  swapSourceId,
  onSetCaptain,
  onSetVice,
  onStartSwap,
  onCancelEdit,
  onDismissEdit,
}) {
  const [animating, setAnimating] = React.useState(false)
  React.useEffect(() => {
    if (layoutKey == null) return
    setAnimating(true)
    const timer = window.setTimeout(() => setAnimating(false), 450)
    return () => window.clearTimeout(timer)
  }, [layoutKey])

  const rows = POSITION_ROWS.map((pos) => {
    const ids = squad.starting[pos] || []
    return {
      pos,
      players: ids.map((id) => players.find((p) => p.id === id)).filter(Boolean),
    }
  })

  React.useEffect(() => {
    if (!isEditMode || (!activeEditPlayer && !swapSourceId)) return undefined
    const onDocDown = (e) => {
      if (e.target.closest('.pchip-slot') || e.target.closest('.edit-popover')) return
      onDismissEdit()
    }
    document.addEventListener('mousedown', onDocDown)
    return () => document.removeEventListener('mousedown', onDocDown)
  }, [isEditMode, activeEditPlayer, swapSourceId, onDismissEdit])

  return (
    <div
      className={`pitch pitch-${theme}${animating ? ' pitch-animate' : ''}${isEditMode ? ' pitch-edit' : ''}`}
    >
      <div className="pitch-bg">
        <div className="pitch-circle" />
        <div className="pitch-line pitch-line-mid" />
        <div className="pitch-box pitch-box-top" />
        <div className="pitch-box pitch-box-bot" />
        <div className="pitch-arc pitch-arc-top" />
        <div className="pitch-arc pitch-arc-bot" />
      </div>
      <div className="pitch-rows">
        {rows.map((row) => (
          <div key={row.pos} className="pitch-row">
            {row.players.map((p) => (
              <PlayerChip
                key={p.id}
                player={p}
                isCaptain={p.id === squad.captain}
                isVice={p.id === squad.vice}
                selectedGw={selectedGw}
                currentActiveGw={currentActiveGw}
                onClick={() => onPlayerClick(p, 'pitch')}
                theme={theme}
                isEditMode={isEditMode}
                isSelected={activeEditPlayer?.id === p.id}
                isSwapSource={swapSourceId === p.id}
                showEditMenu={activeEditPlayer?.id === p.id}
                onSetCaptain={() => onSetCaptain(p.id)}
                onSetVice={() => onSetVice(p.id)}
                onStartSwap={() => onStartSwap(p.id)}
                onCancelEdit={onCancelEdit}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

export function BenchView({
  squad,
  players,
  selectedGw,
  currentActiveGw,
  onPlayerClick,
  theme,
  isEditMode,
  swapSourceId,
}) {
  const benchPlayers = squad.bench.map((id) => players.find((p) => p.id === id)).filter(Boolean)
  return (
    <div className={`bench bench-${theme}${isEditMode ? ' bench-edit' : ''}`}>
      <div className="bench-label">
        {isEditMode && swapSourceId ? 'Bench · tap to swap' : isEditMode ? 'Bench' : 'Bench'}
      </div>
      <div className="bench-row">
        {benchPlayers.map((p, i) => (
          <div
            key={p.id}
            className={`bench-slot${swapSourceId === p.id ? ' bench-slot-selected' : ''}`}
          >
            <span className="bench-num">{i + 1}</span>
            <PlayerChip
              player={p}
              selectedGw={selectedGw}
              currentActiveGw={currentActiveGw}
              onClick={() => onPlayerClick(p, 'bench')}
              theme={theme}
              isEditMode={isEditMode}
              isSwapSource={swapSourceId === p.id}
              isSelected={false}
              showEditMenu={false}
            />
          </div>
        ))}
      </div>
    </div>
  )
}

export function BudgetBar({ used, total, remaining, theme }) {
  const pct = Math.min(100, (used / total) * 100)
  return (
    <div className={`budget budget-${theme}`}>
      <div className="budget-row">
        <span className="budget-lbl">Squad cost</span>
        <span className="budget-val">
          £{used.toFixed(1)}m / £{total.toFixed(1)}m
        </span>
      </div>
      <div className="budget-track">
        <div className="budget-fill" style={{ width: `${pct}%` }} />
      </div>
      <div className="budget-row budget-rem">
        <span>In the bank</span>
        <span>£{(remaining ?? Math.max(0, total - used)).toFixed(1)}m</span>
      </div>
    </div>
  )
}

export function CaptainPanel({ squad, players, theme, selectedGw, isEditMode }) {
  const cap = players.find((p) => p.id === squad.captain)
  const vc = players.find((p) => p.id === squad.vice)
  const gwTag = selectedGw != null ? `GW${selectedGw}` : 'GW'
  return (
    <div className={`captain captain-${theme}`}>
      <div className="captain-row">
        <div className="captain-slot">
          <span className="captain-tag captain-tag-c">C</span>
          <div>
            <div className="captain-name">{cap?.name ?? '—'}</div>
            <div className="captain-meta">
              {gwTag} {(cap?.xp ?? cap?.xPts ?? 0).toFixed(1)} xPts · captain
            </div>
          </div>
        </div>
        <div className="captain-slot">
          <span className="captain-tag captain-tag-v">V</span>
          <div>
            <div className="captain-name">{vc?.name ?? '—'}</div>
            <div className="captain-meta">
              {gwTag} {(vc?.xp ?? vc?.xPts ?? 0).toFixed(1)} xPts · vice
            </div>
          </div>
        </div>
      </div>
      <div className="captain-hint">
        {isEditMode
          ? 'Tap a starter for the action menu · Swap then tap a target.'
          : 'Use Edit Squad to change lineup or captaincy.'}
      </div>
    </div>
  )
}

export function OptimizerPanel({
  onRun,
  running,
  theme,
  error,
  isEditMode,
  onToggleEdit,
  hasManualEdits,
  isSimulationMode,
  onRevert,
}) {
  return (
    <div className={`optim optim-${theme}`}>
      {isSimulationMode && onRevert && (
        <button type="button" className="sim-revert-btn" onClick={onRevert}>
          <span className="sim-revert-icon" aria-hidden="true">
            ↺
          </span>
          Revert to Real Squad
        </button>
      )}
      <div className="optim-actions">
        <button
          type="button"
          className={`edit-btn${isEditMode ? ' edit-btn-on' : ''}`}
          onClick={onToggleEdit}
        >
          {isEditMode ? '💾 Done Editing' : '⚙️ Edit Squad'}
        </button>
        <button
          className="optim-btn"
          disabled={running}
          onClick={onRun}
          type="button"
        >
          {running ? (
            <>
              <span className="optim-spin" />
              Running pipeline…
            </>
          ) : (
            <>
              <span className="optim-icon">⚡</span>
              Run Optimizer
            </>
          )}
        </button>
      </div>
      {isSimulationMode && !isEditMode && (
        <div className="optim-whatif">
          Simulation active · pitch shows staged changes, not your live FPL squad
        </div>
      )}
      {hasManualEdits && !isEditMode && !isSimulationMode && (
        <div className="optim-whatif">What-if lineup active · Projected GW reflects your edits</div>
      )}
      <div className="optim-meta">
        <div>
          <span>Manager Agent</span>
          <b>XI · captaincy · chips</b>
        </div>
        <div>
          <span>Sporting Director</span>
          <b>Transfers</b>
        </div>
      </div>
      {error && (
        <div className="optim-meta" style={{ color: '#ff6b6b' }}>
          <span>{error}</span>
        </div>
      )}
    </div>
  )
}

export function ChipPanel({ used = [], theme }) {
  const tc = used.includes('triple_captain')
  const bb = used.includes('bench_boost')
  return (
    <div className={`chips chips-${theme}`}>
      <div className={`chip-card ${tc ? 'chip-used' : ''}`}>
        <div className="chip-row">
          <span className="chip-label">Triple Captain</span>
          {!tc && <span className="chip-best">EVAL</span>}
        </div>
        <div className="chip-desc">Maximises one explosive haul.</div>
      </div>
      <div className={`chip-card ${bb ? 'chip-used' : ''}`}>
        <div className="chip-row">
          <span className="chip-label">Bench Boost</span>
          {!bb && <span className="chip-best">EVAL</span>}
        </div>
        <div className="chip-desc">All 15 contribute this GW.</div>
      </div>
    </div>
  )
}

function fdrClass(n) {
  const x = Number(n)
  if (x <= 1) return 'fdr fdr-1'
  if (x === 2) return 'fdr fdr-2'
  if (x === 3) return 'fdr fdr-3'
  if (x === 4) return 'fdr fdr-4'
  return 'fdr fdr-5'
}

export function PlayerList({ players, squadIds, onPlayerClick, theme }) {
  const [tab, setTab] = React.useState('ALL')
  const [q, setQ] = React.useState('')
  const [sortMode, setSortMode] = React.useState('xPts')

  const filtered = React.useMemo(() => {
    let rows = [...players]
    if (tab !== 'ALL') rows = rows.filter((p) => p.position === tab)
    const qq = q.trim().toLowerCase()
    if (qq) {
      rows = rows.filter(
        (p) =>
          p.name.toLowerCase().includes(qq) ||
          String(p.team).toLowerCase().includes(qq),
      )
    }
    rows.sort((a, b) => {
      if (sortMode === 'price') return (b.price || 0) - (a.price || 0)
      if (sortMode === 'form') return (b.form || 0) - (a.form || 0)
      return (b.xp ?? b.xPts ?? 0) - (a.xp ?? a.xPts ?? 0)
    })
    return rows
  }, [players, tab, q, sortMode])

  const maxPx = Math.max(...players.map((p) => p.xp ?? p.xPts ?? 0), 1)

  return (
    <div className={`plist plist-${theme}`}>
      <div className="plist-head">
        <div className="plist-tabs">
          {['ALL', 'GKP', 'DEF', 'MID', 'FWD'].map((x) => (
            <button
              key={x}
              type="button"
              className={`plist-tab ${tab === x ? 'on' : ''}`}
              onClick={() => setTab(x)}
            >
              {x}
            </button>
          ))}
        </div>
        <div className="plist-controls">
          <input
            className="plist-search"
            placeholder="Search players…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <select
            className="plist-sort"
            value={sortMode}
            onChange={(e) => setSortMode(e.target.value)}
          >
            <option value="xPts">Sort: xPts</option>
            <option value="price">Sort: Price</option>
            <option value="form">Sort: Form</option>
          </select>
        </div>
      </div>
      <div className="plist-cols">
        <div>#</div>
        <div>Player</div>
        <div className="plist-col-num">£</div>
        <div className="plist-col-num">Form</div>
        <div className="plist-col-num">xPts</div>
        <div className="plist-col-num">Next</div>
        <div>Prospects</div>
        <div />
      </div>
      <div className="plist-body">
        {filtered.length === 0 && (
          <div className="plist-empty">No players match filters.</div>
        )}
        {filtered.map((p, idx) => {
          const inSquad = squadIds.has(p.id)
          const pts = p.xp ?? p.xPts ?? 0
          const pct = Math.round((pts / maxPx) * 100)
          const tm = teamStyle(p.team)
          return (
            <button
              key={p.id}
              type="button"
              className={`prow ${inSquad ? 'prow-in' : ''}`}
              onClick={() => onPlayerClick(p)}
            >
              <span className="prow-num">{idx + 1}</span>
              <div className="prow-name">
                <span
                  className="prow-team-dot"
                  style={{ background: tm.primary }}
                />
                <div>
                  <div className="prow-n">
                    <span
                      className="prow-pos"
                      data-pos={p.position}
                      style={{ marginRight: 6, verticalAlign: 'middle' }}
                    >
                      {p.position}
                    </span>
                    {p.name}
                  </div>
                  <div className="prow-t">{p.team}</div>
                </div>
              </div>
              <span>{p.price?.toFixed?.(1) ?? '—'}</span>
              <span>{p.form ?? '—'}</span>
              <span className="prow-pts">{pts.toFixed(1)}</span>
              <span className="prow-fix">
                <span className={fdrClass(p.fixtureDifficulty)}>
                  {p.fixtureDifficulty}
                  <sup>FDR</sup>
                </span>
              </span>
              <div>
                <div className="xpbar">
                  <div className="xpbar-row">
                    <span>xPts outlook</span>
                    <span className="xpbar-val">{pct}%</span>
                  </div>
                  <div className="xpbar-track">
                    <div className="xpbar-fill" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              </div>
              <span />
            </button>
          )
        })}
      </div>
    </div>
  )
}

function formatStatNum(n, digits = 1) {
  if (n == null || n === '' || Number.isNaN(Number(n))) return '—'
  return Number(n).toFixed(digits)
}

function resolveModalGwXPts(player, deep, selectedGw) {
  const gw = selectedGw ?? deep?.context_gw ?? deep?.current_gw
  const pickEp = (raw) => {
    if (raw == null || raw === '') return null
    const n = Number(raw)
    return Number.isFinite(n) ? n : null
  }
  if (gw != null && deep?.current_gw != null && Number(gw) === Number(deep.current_gw)) {
    return pickEp(deep?.ep_this ?? player?.ep_this)
  }
  if (gw != null && deep?.next_gw != null && Number(gw) === Number(deep.next_gw)) {
    return pickEp(deep?.ep_next ?? player?.ep_next)
  }
  if (gw != null && deep?.next_gw != null && Number(gw) > Number(deep.next_gw)) {
    return pickEp(deep?.ep_next ?? player?.ep_next)
  }
  return pickEp(player?.xp ?? player?.xPts ?? deep?.ep_this ?? deep?.ep_next ?? player?.ep_this ?? player?.ep_next)
}

export function PlayerStatsModal({ player, selectedGw, theme, onClose }) {
  const [deep, setDeep] = React.useState(null)
  const [loading, setLoading] = React.useState(true)

  React.useEffect(() => {
    if (!player?.id) return undefined
    let cancelled = false
    setLoading(true)
    const qs = selectedGw != null ? `?gw=${encodeURIComponent(selectedGw)}` : ''
    fetch(pitchcraftApiUrl(`/api/player/${player.id}${qs}`))
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!cancelled) setDeep(data)
      })
      .catch(() => {
        if (!cancelled) setDeep(null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [player?.id, selectedGw])

  if (!player) return null

  const tm = teamStyle(player.team || deep?.club)
  const gwNum = selectedGw ?? deep?.context_gw ?? deep?.current_gw
  const gwXpRaw = resolveModalGwXPts(player, deep, selectedGw)
  const gwXpLabel = gwNum != null ? `GW${gwNum} xPts` : 'GW xPts'
  const gwStarted = deep?.gw_started
  const gwPtsDisplay =
    gwStarted === false
      ? '—'
      : String(deep?.gw_points ?? player.gw_points ?? player.gw_pts ?? '—')

  const chartHistory = deep?.points_history || []
  const chartTitle =
    gwNum != null && gwNum > 1
      ? `Points · GW1–GW${gwNum - 1}`
      : 'Season points trend'

  const stats = [
    { lbl: 'GW Pts', val: loading ? '…' : gwPtsDisplay, highlight: true },
    {
      lbl: gwXpLabel,
      val: gwXpRaw != null ? formatStatNum(gwXpRaw, 1) : '—',
      highlight: true,
    },
    { lbl: 'Form', val: deep?.form ?? player.form ?? '—' },
    { lbl: 'Season Pts', val: deep?.total_points ?? player.total_points ?? '—' },
    { lbl: 'Median Pts', val: player.median_pts ?? deep?.median_pts ?? '—' },
    { lbl: 'Max Pts', val: deep?.max_pts ?? player.max_pts ?? '—' },
    { lbl: 'Goals', val: deep?.goals ?? player.season_goals ?? player.goals ?? '—' },
    { lbl: 'Assists', val: deep?.assists ?? player.season_assists ?? player.assists ?? '—' },
    { lbl: 'Clean Sheets', val: deep?.clean_sheets ?? '—' },
    { lbl: 'xG', val: formatStatNum(deep?.xg ?? player.xg, 2) },
    { lbl: 'xA', val: formatStatNum(deep?.xa ?? player.xa, 2) },
    { lbl: 'xGA', val: formatStatNum(deep?.xga ?? player.xga, 2) },
    {
      lbl: 'Start %',
      val: deep?.start_pct != null ? `${deep.start_pct}%` : '—',
    },
    { lbl: 'Minutes', val: deep?.minutes ?? player.minutes ?? '—' },
    {
      lbl: 'Minutes %',
      val: deep?.minutes_played_pct != null ? `${deep.minutes_played_pct}%` : '—',
    },
  ]

  const parts = (player.name || '').trim().split(/\s+/)
  const last = player.second_name || parts.pop() || player.name
  const first = player.first_name || parts.join(' ')
  const teamCode = player.team_code ?? deep?.team_code
  const elementType = player.element_type ?? deep?.element_type

  return (
    <div
      className="pdetail-overlay"
      role="dialog"
      aria-modal="true"
      aria-label={`${player.name} stats`}
      onClick={onClose}
    >
      <div
        className={`pdetail pdetail-${theme} pstats-modal`}
        style={{ '--team': tm.primary }}
        onClick={(e) => e.stopPropagation()}
      >
        <button type="button" className="pdetail-close" onClick={onClose} aria-label="Close">
          ✕
        </button>
        <div className="pdetail-head">
          <div className="pstats-kit-wrap">
            <PlayerKitImg
              teamCode={teamCode}
              elementType={elementType}
              position={player.position}
              className="pstats-kit-avatar"
              fallbackColor={tm.primary}
            />
          </div>
          <div className="pdetail-id">
            <div className="pdetail-first">{first}</div>
            <div className="pdetail-last">{last}</div>
            <div className="pdetail-team">
              <span className="pdetail-pos">{player.position}</span>
              <span>{deep?.club || player.team || '—'}</span>
            </div>
          </div>
          <div className="pdetail-price">
            <div className="pdetail-price-val">£{(player.price ?? deep?.price ?? 0).toFixed?.(1)}m</div>
            <div className="pdetail-price-lbl">Price</div>
          </div>
        </div>
        <div className="pdetail-h pstats-kicker">Player stats hub</div>
        <div className="pdetail-grid pstats-grid">
          {stats.map((s) => (
            <div
              key={s.lbl}
              className={`pstats-cell${s.highlight ? ' pstats-cell-hi' : ''}`}
            >
              <div className="pstats-stat-lbl">{s.lbl}</div>
              <div className="pstats-stat-val">{s.val}</div>
            </div>
          ))}
        </div>
        <div className="pstats-chart">
          <div className="pstats-chart-head">{chartTitle}</div>
          {loading ? (
            <div className="pstats-chart-loading">Loading points history…</div>
          ) : (
            <PointsTrendLine history={chartHistory} className="ptl-modal" height={110} />
          )}
        </div>
        {deep?.max_possible_minutes != null && (
          <div className="pstats-foot">
            Max possible minutes: {deep.max_possible_minutes} ({deep.team_matches_played} team matches × 90)
          </div>
        )}
      </div>
    </div>
  )
}

export function PlayerDetail({
  player,
  onClose,
  onSetCaptain,
  onSetVice,
  onTransferOut,
  isStarter,
  theme,
}) {
  if (!player) return null
  const tm = teamStyle(player.team)
  const pts = player.xp ?? player.xPts ?? 0
  const parts = player.name.trim().split(/\s+/)
  const last = parts.pop() || player.name
  const first = parts.join(' ')
  return (
    <div className="pdetail-overlay" role="dialog" aria-modal="true">
      <div className={`pdetail pdetail-${theme}`} style={{ '--team': tm.primary }}>
        <button type="button" className="pdetail-close" onClick={onClose}>
          ✕
        </button>
        <div className="pdetail-head">
          <div className="pdetail-shirt">
            <div className="pdetail-shirt-inner" />
          </div>
          <div className="pdetail-id">
            <div className="pdetail-first">{first}</div>
            <div className="pdetail-last">{last}</div>
            <div className="pdetail-team">
              <span className="pdetail-pos">{player.position}</span>
              <span>{player.team}</span>
            </div>
          </div>
          <div className="pdetail-price">
            <div className="pdetail-price-val">£{player.price?.toFixed?.(1)}m</div>
            <div className="pdetail-price-lbl">Price</div>
          </div>
        </div>
        <div className="pdetail-stats">
          <div className="pdetail-stat">
            <div className="pdetail-stat-lbl">GW xPts</div>
            <div className="pdetail-stat-val">{pts.toFixed(1)}</div>
          </div>
          <div className="pdetail-stat">
            <div className="pdetail-stat-lbl">Form</div>
            <div className="pdetail-stat-val">{player.form ?? '—'}</div>
          </div>
          <div className="pdetail-stat">
            <div className="pdetail-stat-lbl">Ownership</div>
            <div className="pdetail-stat-val">{player.ownership ?? '—'}%</div>
          </div>
          <div className="pdetail-stat">
            <div className="pdetail-stat-lbl">Next</div>
            <div className="pdetail-stat-val">{player.nextFixture ?? '—'}</div>
          </div>
        </div>
        <div className="pdetail-actions">
          {isStarter && (
            <>
              <button
                type="button"
                className="pdetail-btn pdetail-btn-primary"
                onClick={() => onSetCaptain(player.id)}
              >
                Set captain
              </button>
              <button
                type="button"
                className="pdetail-btn"
                onClick={() => onSetVice(player.id)}
              >
                Set vice
              </button>
            </>
          )}
          <button type="button" className="pdetail-btn pdetail-btn-danger" onClick={onTransferOut}>
            Plan transfer out
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Players tab: global FPL player pool (bootstrap-static) ─────────────────

function playerFullName(p) {
  const full = `${p.first_name ?? ''} ${p.second_name ?? ''}`.trim()
  return full || p.web_name || p.name || 'Unknown'
}

function playerXPts(p) {
  const n = playerProjectedXp(p)
  return Number.isFinite(n) ? n : null
}

function formatXPts(p) {
  const n = playerXPts(p)
  return n != null ? n.toFixed(1) : '—'
}

function SortableTh({ label, sortKey, sortConfig, onSort, className }) {
  const active = sortConfig?.key === sortKey
  return (
    <th
      className={`aplayers-sortable ${className}${active ? ' aplayers-sort-active' : ''}`}
      onClick={() => onSort?.(sortKey)}
      aria-sort={
        active ? (sortConfig.direction === 'asc' ? 'ascending' : 'descending') : 'none'
      }
    >
      <span className="aplayers-th-inner">
        {label}
        {active && (
          <span className="aplayers-sort-arrow" aria-hidden>
            {sortConfig.direction === 'asc' ? '↑' : '↓'}
          </span>
        )}
      </span>
    </th>
  )
}

export function AllPlayersTable({
  players,
  loading,
  theme,
  squadIds,
  onPlayerClick,
  selectedTeam,
  onSelectedTeamChange,
  sortConfig,
  onSortHeader,
}) {
  const [q, setQ] = React.useState('')
  const [posFilter, setPosFilter] = React.useState('ALL')

  const teamOptions = React.useMemo(() => {
    const seen = new Map()
    for (const p of players || []) {
      const team = p.team && p.team !== '?' ? p.team : null
      const short = p.teamShort || '???'
      const key = team || short
      if (!key || key === '???') continue
      if (!seen.has(key)) seen.set(key, short)
    }
    return [...seen.entries()]
      .map(([team, short]) => ({ team, short }))
      .sort((a, b) => a.short.localeCompare(b.short))
  }, [players])

  const teamKey = (p) =>
    p.team && p.team !== '?' ? p.team : p.teamShort || ''

  const filtered = React.useMemo(() => {
    let rows = [...(players || [])]
    if (posFilter !== 'ALL') rows = rows.filter((p) => p.position === posFilter)
    if (selectedTeam !== 'ALL') {
      rows = rows.filter((p) => teamKey(p) === selectedTeam)
    }
    const qq = q.trim().toLowerCase()
    if (qq) {
      rows = rows.filter((p) => {
        const full = playerFullName(p).toLowerCase()
        return (
          full.includes(qq) ||
          String(p.web_name || '').toLowerCase().includes(qq) ||
          String(p.teamShort || '').toLowerCase().includes(qq) ||
          String(p.team || '').toLowerCase().includes(qq)
        )
      })
    }
    rows.sort((a, b) => {
      const dir = sortConfig?.direction === 'asc' ? 1 : -1
      const key = sortConfig?.key ?? 'total_points'
      if (key === 'name') {
        return dir * playerFullName(a).localeCompare(playerFullName(b))
      }
      const num = (p) => {
        if (key === 'now_cost') return Number(p.now_cost ?? 0)
        if (key === 'total_points') return Number(p.total_points ?? 0)
        if (key === 'ep_next') return playerXPts(p) ?? -Infinity
        return 0
      }
      return dir * (num(a) - num(b))
    })
    return rows
  }, [players, q, posFilter, selectedTeam, sortConfig])

  return (
    <div className={`aplayers aplayers-${theme}`}>
      <div className="aplayers-head">
        <div>
          <div className="aplayers-title">All FPL players</div>
          <div className="aplayers-sub">
            {loading ? 'Loading…' : `${filtered.length.toLocaleString()} players`}
          </div>
        </div>
        <div className="aplayers-controls">
          <div className="plist-tabs">
            {['ALL', 'GKP', 'DEF', 'MID', 'FWD'].map((x) => (
              <button
                key={x}
                type="button"
                className={`plist-tab ${posFilter === x ? 'on' : ''}`}
                onClick={() => setPosFilter(x)}
              >
                {x}
              </button>
            ))}
          </div>
          <select
            className="aplayers-team-select"
            value={selectedTeam}
            onChange={(e) => onSelectedTeamChange?.(e.target.value)}
            aria-label="Filter by club"
          >
            <option value="ALL">All Teams</option>
            {teamOptions.map(({ team, short }) => (
              <option key={team} value={team}>
                {short}
              </option>
            ))}
          </select>
          <input
            className="plist-search"
            placeholder="Search by name or club…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
      </div>
      <div className="aplayers-scroll">
        <table className="aplayers-table">
          <colgroup>
            <col className="aplayers-col-kit" />
            <col className="aplayers-col-name" />
            <col className="aplayers-col-pos" />
            <col className="aplayers-col-team" />
            <col className="aplayers-col-cost" />
            <col className="aplayers-col-total" />
            <col className="aplayers-col-xpts" />
          </colgroup>
          <thead>
            <tr>
              <th className="aplayers-th-kit aplayers-ta-center">Kit</th>
              <SortableTh
                label="Name"
                sortKey="name"
                sortConfig={sortConfig}
                onSort={onSortHeader}
                className="aplayers-th-name aplayers-ta-left"
              />
              <th className="aplayers-th-pos aplayers-ta-center">Pos</th>
              <th className="aplayers-th-team aplayers-ta-center">Team</th>
              <SortableTh
                label="Cost"
                sortKey="now_cost"
                sortConfig={sortConfig}
                onSort={onSortHeader}
                className="aplayers-th-cost aplayers-ta-right"
              />
              <SortableTh
                label="Total Pts"
                sortKey="total_points"
                sortConfig={sortConfig}
                onSort={onSortHeader}
                className="aplayers-th-total aplayers-ta-center"
              />
              <SortableTh
                label="xPts"
                sortKey="ep_next"
                sortConfig={sortConfig}
                onSort={onSortHeader}
                className="aplayers-th-xpts aplayers-ta-center"
              />
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={7} className="aplayers-loading">
                  Loading player pool…
                </td>
              </tr>
            )}
            {!loading && filtered.length === 0 && (
              <tr>
                <td colSpan={7} className="aplayers-empty">
                  No players match your filters.
                </td>
              </tr>
            )}
            {!loading &&
              filtered.map((p) => {
                const inSquad = squadIds?.has?.(p.id)
                const tm = teamStyle(p.team || p.teamShort)
                const fullName = playerFullName(p)
                return (
                  <tr
                    key={p.id}
                    className={`aplayers-row${inSquad ? ' aplayers-in-squad' : ''}`}
                    onClick={() => onPlayerClick?.(p)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        onPlayerClick?.(p)
                      }
                    }}
                  >
                    <td className="aplayers-kit aplayers-ta-center">
                      <PlayerKitImg
                        teamCode={p.team_code}
                        elementType={p.element_type}
                        position={p.position}
                        className="aplayers-kit-img"
                        fallbackColor={tm.primary}
                      />
                    </td>
                    <td className="aplayers-name aplayers-ta-left">
                      <span className="aplayers-player-name">{fullName}</span>
                    </td>
                    <td className="aplayers-pos aplayers-ta-center">{p.position}</td>
                    <td className="aplayers-team aplayers-ta-center">{p.teamShort || tm.short}</td>
                    <td className="aplayers-cost aplayers-ta-right">
                      £{(p.price ?? (p.now_cost != null ? p.now_cost / 10 : 0)).toFixed(1)}m
                    </td>
                    <td className="aplayers-total aplayers-ta-center">{p.total_points ?? '—'}</td>
                    <td className="aplayers-xpts aplayers-ta-center">{formatXPts(p)}</td>
                  </tr>
                )
              })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─── Players tab: advanced-stats data table with click-to-expand rows ────────

function fmtNum(v, dp = 2) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return n.toFixed(dp)
}

export function PlayerTable({ players, squadIds, theme }) {
  const [tab, setTab] = React.useState('ALL')
  const [q, setQ] = React.useState('')
  const [sortMode, setSortMode] = React.useState('avg_pts')
  const [expandedId, setExpandedId] = React.useState(null)

  const filtered = React.useMemo(() => {
    let rows = [...players]
    if (tab !== 'ALL') rows = rows.filter((p) => p.position === tab)
    const qq = q.trim().toLowerCase()
    if (qq) {
      rows = rows.filter(
        (p) =>
          p.name.toLowerCase().includes(qq) ||
          String(p.team).toLowerCase().includes(qq),
      )
    }
    rows.sort((a, b) => {
      if (sortMode === 'goals') return (b.goals || 0) - (a.goals || 0)
      if (sortMode === 'assists') return (b.assists || 0) - (a.assists || 0)
      if (sortMode === 'xg') return (b.xg || 0) - (a.xg || 0)
      if (sortMode === 'median_pts') return (b.median_pts || 0) - (a.median_pts || 0)
      return (b.avg_pts ?? 0) - (a.avg_pts ?? 0)
    })
    return rows
  }, [players, tab, q, sortMode])

  return (
    <div className={`ptable plist plist-${theme}`}>
      <div className="plist-head">
        <div className="plist-tabs">
          {['ALL', 'GKP', 'DEF', 'MID', 'FWD'].map((x) => (
            <button
              key={x}
              type="button"
              className={`plist-tab ${tab === x ? 'on' : ''}`}
              onClick={() => setTab(x)}
            >
              {x}
            </button>
          ))}
        </div>
        <div className="plist-controls">
          <input
            className="plist-search"
            placeholder="Search players…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <select
            className="plist-sort"
            value={sortMode}
            onChange={(e) => setSortMode(e.target.value)}
          >
            <option value="avg_pts">Sort: Avg Pts</option>
            <option value="median_pts">Sort: Median Pts</option>
            <option value="goals">Sort: Goals</option>
            <option value="assists">Sort: Assists</option>
            <option value="xg">Sort: xG</option>
          </select>
        </div>
      </div>
      <div className="ptable-cols">
        <div>Player</div>
        <div className="plist-col-num">Goals</div>
        <div className="plist-col-num">Assists</div>
        <div className="plist-col-num">xG</div>
        <div className="plist-col-num">xA</div>
        <div className="plist-col-num">Avg</div>
        <div className="plist-col-num">Median</div>
        <div className="plist-col-num">Form</div>
      </div>
      <div className="plist-body">
        {filtered.length === 0 && (
          <div className="plist-empty">No players match filters.</div>
        )}
        {filtered.map((p) => {
          const open = expandedId === p.id
          const tm = teamStyle(p.team)
          const inSquad = squadIds?.has?.(p.id)
          return (
            <div key={p.id} className={`ptrow-wrap ${open ? 'open' : ''}`}>
              <button
                type="button"
                className={`ptrow ${inSquad ? 'prow-in' : ''} ${open ? 'on' : ''}`}
                onClick={() => setExpandedId(open ? null : p.id)}
                aria-expanded={open}
              >
                <div className="prow-name">
                  <span className="prow-team-dot" style={{ background: tm.primary }} />
                  <div>
                    <div className="prow-n">
                      <span
                        className="prow-pos"
                        data-pos={p.position}
                        style={{ marginRight: 6, verticalAlign: 'middle' }}
                      >
                        {p.position}
                      </span>
                      {p.name}
                    </div>
                    <div className="prow-t">{p.team}</div>
                  </div>
                </div>
                <span>{p.goals ?? 0}</span>
                <span>{p.assists ?? 0}</span>
                <span>{fmtNum(p.xg)}</span>
                <span>{fmtNum(p.xa)}</span>
                <span className="prow-pts">{fmtNum(p.avg_pts, 1)}</span>
                <span>{fmtNum(p.median_pts, 1)}</span>
                <span className="ptrow-form">{p.form_trend || '—'}</span>
              </button>
              {open && <PlayerExtended player={p} />}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function PlayerExtended({ player }) {
  const stats = [
    { lbl: 'ICT Index', val: fmtNum(player.ict_index, 1) },
    { lbl: 'Ownership', val: `${fmtNum(player.ownership, 1)}%` },
    { lbl: 'Value', val: `£${fmtNum(player.price, 1)}m` },
    { lbl: 'Pts / Game', val: fmtNum(player.points_per_game, 1) },
    { lbl: 'Total Pts', val: player.total_points ?? '—' },
    { lbl: 'Next', val: player.nextFixture ?? '—' },
  ]
  return (
    <div className="ptrow-detail">
      <div className="ptrow-detail-grid">
        {stats.map((s) => (
          <div key={s.lbl} className="ptrow-detail-cell">
            <div className="ptrow-detail-lbl">{s.lbl}</div>
            <div className="ptrow-detail-val">{s.val}</div>
          </div>
        ))}
      </div>
      <div className="ptrow-detail-foot">
        <span className={fdrClass(player.fixtureDifficulty)}>
          {player.fixtureDifficulty}
          <sup>FDR</sup>
        </span>
        <span className="ptrow-detail-xp">{fmtNum(player.xp ?? player.xPts, 1)} projected xPts</span>
      </div>
    </div>
  )
}

// ─── Minimalist inline SVG points trend line ─────────────────────────────────

export function PointsTrendLine({ history, className = '', height = 92 }) {
  const [hover, setHover] = React.useState(null)
  const gradId = React.useId().replace(/:/g, '')
  const data = (Array.isArray(history) ? history : []).filter(
    (d) => d && Number.isFinite(Number(d.points)),
  )
  if (data.length < 2) {
    return <div className="ptl-empty">Not enough gameweeks for a trend yet.</div>
  }

  const W = 320
  const H = height
  const padX = 8
  const padY = 14
  const pts = data.map((d) => Number(d.points))
  const maxP = Math.max(...pts)
  const minP = Math.min(...pts)
  const range = maxP - minP || 1
  const n = data.length
  const x = (i) => padX + (i * (W - 2 * padX)) / (n - 1)
  const y = (p) => H - padY - ((p - minP) / range) * (H - 2 * padY)
  const linePath = data
    .map((d, i) => `${i === 0 ? 'M' : 'L'} ${x(i).toFixed(1)} ${y(d.points).toFixed(1)}`)
    .join(' ')
  const areaPath = `${linePath} L ${x(n - 1).toFixed(1)} ${H - padY} L ${x(0).toFixed(1)} ${H - padY} Z`

  return (
    <div className={`ptl ${className}`.trim()}>
      <svg
        className="ptl-svg"
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        role="img"
        aria-label="Points trend over recent gameweeks"
      >
        <defs>
          <linearGradient id={`ptl-grad-${gradId}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.35" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={areaPath} className="ptl-area" fill={`url(#ptl-grad-${gradId})`} />
        <path d={linePath} className="ptl-line" fill="none" />
        {data.map((d, i) => (
          <g key={d.gw}>
            <circle
              cx={x(i)}
              cy={y(d.points)}
              r={hover === i ? 4 : 2.4}
              className="ptl-dot"
            />
            <circle
              cx={x(i)}
              cy={y(d.points)}
              r="10"
              fill="transparent"
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
            />
          </g>
        ))}
      </svg>
      {hover != null && (
        <div
          className="ptl-tip"
          style={{ left: `${(x(hover) / W) * 100}%` }}
        >
          GW{data[hover].gw} · {data[hover].points} pts
        </div>
      )}
    </div>
  )
}

// ─── Squad tab: manager-level aggregate analytics panel ───────────────────────

export function SquadAnalytics({ stats, theme }) {
  const s = stats || {}
  const hasData = s && Object.keys(s).length > 0

  // Loading / not-yet-fetched state — sleek skeleton with a status message.
  if (!hasData) {
    return (
      <div className={`sanalytics sanalytics-${theme}`}>
        <div className="sa-head">
          <div className="sa-title">Squad Analytics</div>
        </div>
        <div className="sa-loading">Crunching manager history…</div>
        <div className="sa-grid">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="sa-cell sa-skel">
              <div className="sa-skel-lbl" />
              <div className="sa-skel-val" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  const trend = String(s.overall_trend || '').toLowerCase()
  const arrow = trend === 'up' ? '▲' : trend === 'down' ? '▼' : '—'
  const arrowClass =
    trend === 'up' ? 'sa-up' : trend === 'down' ? 'sa-down' : 'sa-flat'
  const trendLabel = s.overall_trend
    ? `Trending ${s.overall_trend}`
    : 'No trend'

  const metrics = [
    { lbl: 'Squad Form', val: s.squad_form || '—' },
    { lbl: 'Current GW Pts', val: s.current_gw_points ?? '—' },
    { lbl: 'Highest GW Pts', val: s.highest_points ?? '—' },
    { lbl: 'Median GW Pts', val: s.median_points ?? '—' },
  ]

  return (
    <div className={`sanalytics sanalytics-${theme}`}>
      <div className="sa-head">
        <div className="sa-title">Squad Analytics</div>
        <div className={`sa-trend ${arrowClass}`}>
          <span className="sa-trend-arrow">{arrow}</span>
          <span className="sa-trend-lbl">{trendLabel}</span>
        </div>
      </div>
      <div className="sa-grid">
        {metrics.map((m) => (
          <div key={m.lbl} className="sa-cell">
            <div className="sa-lbl">{m.lbl}</div>
            <div className="sa-val">{m.val}</div>
          </div>
        ))}
      </div>
      <div className="sa-trendline">
        <div className="sa-trendline-head">Points trend</div>
        <PointsTrendLine history={s.points_history} />
      </div>
    </div>
  )
}

// ─── Squad tab: compact players list (sidebar, beneath the trend line) ────────

export function SquadTable({ squad, players, loading, theme, onPlayerClick, selectedGw }) {
  const byId = React.useMemo(() => {
    const m = new Map()
    for (const p of players || []) m.set(Number(p.id), p)
    return m
  }, [players])

  const rows = React.useMemo(() => {
    if (!squad || !squad.starting) return []
    const out = []
    for (const pos of ['GKP', 'DEF', 'MID', 'FWD']) {
      for (const id of squad.starting[pos] || []) out.push({ id, pos, starter: true })
    }
    for (const id of squad.bench || []) {
      const p = byId.get(Number(id))
      out.push({ id, pos: p?.position || '—', starter: false })
    }
    return out
  }, [squad, byId])

  // Loading skeleton while the pitch is still populating.
  if (loading && !rows.length) {
    return (
      <div className={`sqlist sqlist-${theme}`}>
        <div className="sqlist-head">
          <div className="sqlist-title">Squad</div>
        </div>
        <div className="sqlist-skel">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="sqlist-skel-row" />
          ))}
        </div>
      </div>
    )
  }

  if (!rows.length) return null

  return (
    <div className={`sqlist sqlist-${theme}`}>
      <div className="sqlist-head">
        <div className="sqlist-title">Squad</div>
        <div className="sqlist-cols">
          <span>GW Pts</span>
          <span>{selectedGw != null ? `GW${selectedGw}` : 'GW'} xPts</span>
        </div>
      </div>
      <div className="sqlist-scroll">
        {rows.map(({ id, pos, starter }) => {
          const p = byId.get(Number(id)) || {}
          const gwPts = Number(p.gw_points ?? p.gw_pts ?? 0)
          const xpts = playerProjectedXp(p)
          const isCap = squad.captain === id
          const isVice = squad.vice === id
          return (
            <button
              key={id}
              type="button"
              className={`sqlist-row sqlist-row-btn${starter ? '' : ' sqlist-bench'}`}
              onClick={() => onPlayerClick?.(p)}
            >
              <span className={`sqlist-badge sqlist-badge-${pos}`}>{pos}</span>
              <span className="sqlist-name">{p.name || 'Unknown'}</span>
              {isCap && <span className="sqlist-tag sqlist-tag-c">C</span>}
              {isVice && <span className="sqlist-tag sqlist-tag-v">V</span>}
              {!starter && <span className="sqlist-tag sqlist-tag-b">BENCH</span>}
              <span className="sqlist-metrics">
                <span className="sqlist-gw">{gwPts}</span>
                <span className="sqlist-xp">{xpts.toFixed(1)}</span>
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

const CHIP_LABELS = {
  wildcard: 'Wildcard',
  freehit: 'Free Hit',
  triple_captain: 'Triple Captain',
  bench_boost: 'Bench Boost',
}

const HIT_WAIVING_CHIPS = new Set(['wildcard', 'freehit'])

export function TransfersView({
  xferPayload,
  theme,
  onClose,
  onApply,
  availableFreeTransfers = 1,
  availableChips = [],
}) {
  const transfers = xferPayload?.transfers ?? []
  const summary = xferPayload?.summary ?? ''
  const hold = xferPayload?.hold_flag

  const [selectedTransfers, setSelectedTransfers] = React.useState([])
  const [activeChip, setActiveChip] = React.useState(null)

  React.useEffect(() => {
    setSelectedTransfers([])
    setActiveChip(null)
  }, [xferPayload])

  const selectedKeys = React.useMemo(
    () => new Set(selectedTransfers.map((t) => transferKey(t))),
    [selectedTransfers],
  )

  const hitCost = React.useMemo(() => {
    if (activeChip && HIT_WAIVING_CHIPS.has(activeChip)) return 0
    return Math.max(0, selectedTransfers.length - availableFreeTransfers) * 4
  }, [selectedTransfers.length, availableFreeTransfers, activeChip])

  const toggleTransfer = (transfer) => {
    setSelectedTransfers((prev) => {
      const key = transferKey(transfer)
      const exists = prev.some((t) => transferKey(t) === key)
      if (exists) {
        return prev.filter((t) => transferKey(t) !== key)
      }
      return [...prev, transfer]
    })
  }

  const toggleChip = (chip) => {
    setActiveChip((prev) => (prev === chip ? null : chip))
  }

  const handleApply = () => {
    if (selectedTransfers.length === 0) return
    onApply?.({ selectedTransfers, activeChip, hitCost })
  }

  return (
    <div className={`tview tview-${theme}`}>
      <div className="tview-head">
        <div>
          <div className="tview-title">Transfer planner</div>
          <div className="tview-sub">{summary || 'Sporting Director recommendations'}</div>
        </div>
        <button type="button" className="tview-close" onClick={onClose}>
          ← Squad
        </button>
      </div>
      <div className="tview-summary">
        <div className="tview-stat">
          <div className="tview-stat-lbl">Selected</div>
          <div className="tview-stat-val">{selectedTransfers.length}</div>
        </div>
        <div className="tview-stat">
          <div className="tview-stat-lbl">Free transfers</div>
          <div className="tview-stat-val">{availableFreeTransfers}</div>
        </div>
        <div className="tview-stat">
          <div className="tview-stat-lbl">Hit cost</div>
          <div className={`tview-stat-val${hitCost > 0 ? ' tview-hit' : ' tview-pos'}`}>
            {hitCost > 0 ? `−${hitCost}` : '0'}
          </div>
        </div>
        <div className="tview-stat">
          <div className="tview-stat-lbl">Planning GW</div>
          <div className="tview-stat-val">{xferPayload?.planning_gameweek ?? xferPayload?.gameweek ?? '—'}</div>
        </div>
      </div>
      {availableChips.length > 0 && (
        <div className="tview-chips-wrap">
          <div className="tview-chips-lbl">Available chips</div>
          <div className="tview-chips">
            {availableChips.map((chip) => (
              <button
                key={chip}
                type="button"
                className={`tview-chip-btn${activeChip === chip ? ' on' : ''}`}
                onClick={() => toggleChip(chip)}
              >
                {CHIP_LABELS[chip] ?? chip}
              </button>
            ))}
          </div>
          {activeChip && HIT_WAIVING_CHIPS.has(activeChip) && (
            <div className="tview-chip-note">
              {CHIP_LABELS[activeChip]} active — transfer hits waived for this plan
            </div>
          )}
        </div>
      )}
      <div className="tview-meta-row">
        <span>Hold squad? <b>{hold ? 'Yes' : 'No'}</b></span>
        <span>
          Agent chip hint:{' '}
          <b>
            {typeof xferPayload?.wildcard_flag === 'string'
              ? xferPayload.wildcard_flag
              : xferPayload?.wildcard_flag
                ? 'Wildcard'
                : '—'}
          </b>
        </span>
      </div>
      <div className="tview-rows">
        {transfers.length === 0 && (
          <div className="plist-empty">No transfer rows yet — run the optimiser.</div>
        )}
        {transfers.map((t, i) => {
          const sell = t.sell || {}
          const buy = t.buy || {}
          const gain = t.net_expected_gain ?? t.expected_gain ?? 0
          const rowKey = transferKey(t) || String(i)
          const selected = selectedKeys.has(rowKey)
          return (
            <button
              key={rowKey}
              type="button"
              className={`trow trow-selectable${selected ? ' trow-selected' : ''}`}
              onClick={() => toggleTransfer(t)}
              aria-pressed={selected}
            >
              <div className="trow-side">
                <span className="trow-arrow trow-arrow-out">−</span>
                <div className="trow-name">{sell.name ?? 'Out'}</div>
                <div className="trow-meta">{sell.position ?? ''}</div>
                <div className="trow-xp">{sell.expected_pts != null ? `${sell.expected_pts.toFixed?.(1) ?? sell.expected_pts} xPts` : ''}</div>
              </div>
              <div className="trow-mid">
                <div className="trow-gain">+{typeof gain === 'number' ? gain.toFixed(1) : gain}</div>
                <div className="trow-cost trow-cost-pos">
                  {selected ? 'In cart' : 'Tap to add'}
                </div>
                <div className="trow-reason">{t.reasoning ?? ''}</div>
              </div>
              <div className="trow-side">
                <span className="trow-arrow trow-arrow-in">+</span>
                <div className="trow-name">{buy.name ?? 'In'}</div>
                <div className="trow-meta">{buy.team ?? ''}</div>
                <div className="trow-xp">{buy.expected_pts != null ? `${buy.expected_pts.toFixed?.(1) ?? buy.expected_pts} xPts` : ''}</div>
              </div>
            </button>
          )
        })}
      </div>
      <div className="tview-actions">
        <button
          type="button"
          className="tview-btn tview-btn-primary"
          disabled={selectedTransfers.length === 0}
          onClick={handleApply}
        >
          Apply &amp; Return
        </button>
        <button type="button" className="tview-btn tview-btn-ghost" onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  )
}

export function TweaksPanel({ children }) {
  const [open, setOpen] = React.useState(false)
  return (
    <>
      <button
        type="button"
        className="twk-fab"
        title="Theme tweaks"
        onClick={() => setOpen((v) => !v)}
      >
        ⚙
      </button>
      {open && (
        <aside className="twk-drawer" data-theme-editor="pitchcraft">
          {children}
        </aside>
      )}
    </>
  )
}

export function TweakSection({ label }) {
  return <div className="twk-section">{label}</div>
}

export function TweakRadio({ label, value, options, onChange }) {
  return (
    <div className="twk-radio-row">
      <span style={{ fontSize: 11, opacity: 0.75 }}>{label}</span>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          className={`twk-radio-opt ${value === o.value ? 'on' : ''}`}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function TweakColor({ label, value, onChange }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <span style={{ fontSize: 11, opacity: 0.75 }}>{label}</span>
      <input
        className="twk-color"
        type="color"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  )
}

export function useTweaks(defaults) {
  const [state, setState] = React.useState(defaults)
  const setTweak = React.useCallback((key, val) => {
    setState((s) => ({ ...s, [key]: val }))
  }, [])
  return [state, setTweak]
}
