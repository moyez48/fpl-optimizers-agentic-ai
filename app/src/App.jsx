import React from 'react'
import { pitchcraftApiUrl } from './lib/pitchcraftApi.js'
import { buildOptimalPitchcraftSquad } from './utils/optimalXI.js'
import { setCaptain, setViceCaptain, swapPlayers } from './utils/squadEdit.js'
import { applySelectedTransfers } from './utils/transferApply.js'
import {
  mergePlayerProjectionFields,
  resolvePlayerXpts,
  shouldPollLiveScores,
} from './utils/gameweekDisplay.js'
import {
  PitchView,
  BenchView,
  BudgetBar,
  CaptainPanel,
  OptimizerPanel,
  ChipPanel,
  AllPlayersTable,
  SquadAnalytics,
  SquadTable,
  PlayerStatsModal,
  TransfersView,
  TweaksPanel,
  TweakSection,
  TweakRadio,
  TweakColor,
  useTweaks,
} from './pitchcraft/PitchcraftUI.jsx'

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/ {
  theme: 'sporty',
  accent: '#7CFF50',
  showOptimizer: true,
} /*EDITMODE-END*/

const ROW_ORDER = ['FWD', 'MID', 'DEF', 'GKP']

function flattenStartingIds(squad) {
  const out = []
  for (const k of ROW_ORDER) {
    out.push(...(squad.starting?.[k] || []))
  }
  return out
}

function squadPlayerIds(squad) {
  const xi = flattenStartingIds(squad)
  return [...xi, ...(squad.bench || [])].slice(0, 15)
}

const EMPTY_SQUAD = {
  starting: { GKP: [], DEF: [], MID: [], FWD: [] },
  bench: [],
  captain: null,
  vice: null,
}

function deepClone(value) {
  try {
    return structuredClone(value)
  } catch {
    return JSON.parse(JSON.stringify(value))
  }
}

function cloneSquad(squad) {
  return deepClone(squad)
}

function squadsEqual(a, b) {
  return JSON.stringify(cloneSquad(a)) === JSON.stringify(cloneSquad(b))
}

function squadPoolFromSquad(squad, players) {
  const ids = new Set(squadPlayerIds(squad))
  return players.filter((p) => ids.has(p.id))
}

// FPL element_type integers → Pitchcraft grid rows.
const ELEMENT_TYPE_TO_POS = { 1: 'GKP', 2: 'DEF', 3: 'MID', 4: 'FWD' }

// Map a raw backend player onto the keys the Pitchcraft UI renders.
// Backend may use FPL-native keys (web_name, element_type, predicted_points)
// or already-normalised ones (name, position, xPts) — handle both.
function normalizePlayer(raw) {
  const rawPos = raw.position ?? raw.element_type
  let position
  if (typeof rawPos === 'number') {
    position = ELEMENT_TYPE_TO_POS[rawPos] ?? 'MID'
  } else if (rawPos === 'GK') {
    position = 'GKP'
  } else {
    position = ELEMENT_TYPE_TO_POS[rawPos] ?? rawPos ?? 'MID'
  }
  const xp = resolvePlayerXpts(raw)
  const price = raw.price ?? (raw.now_cost != null ? raw.now_cost / 10 : 0)
  const webName = raw.web_name ?? raw.name ?? 'Unknown'
  return {
    ...raw,
    id: raw.id ?? raw.element ?? raw.player_id,
    name: webName,
    web_name: webName,
    element_type: raw.element_type ?? rawPos,
    team_code: raw.team_code ?? null,
    position,
    xp,
    xPts: xp,
    price,
  }
}

// Build a Pitchcraft squad object from a flat, normalised player pool when the
// backend returns only a list. Best xPts per line start; rest go to the bench.
function buildSquadFromPlayers(pool) {
  const byPos = { GKP: [], DEF: [], MID: [], FWD: [] }
  for (const p of pool) (byPos[p.position] || (byPos[p.position] = [])).push(p)
  for (const k of Object.keys(byPos)) {
    byPos[k].sort((a, b) => (b.xp ?? 0) - (a.xp ?? 0))
  }
  const want = { GKP: 1, DEF: 4, MID: 4, FWD: 2 }
  const starting = { GKP: [], DEF: [], MID: [], FWD: [] }
  const bench = []
  for (const k of ROW_ORDER.slice().reverse()) {
    const ids = (byPos[k] || []).map((p) => p.id)
    starting[k] = ids.slice(0, want[k] ?? 0)
    bench.push(...ids.slice(want[k] ?? 0))
  }
  const xiIds = ['GKP', 'DEF', 'MID', 'FWD'].flatMap((k) => starting[k])
  const captain =
    xiIds
      .map((id) => pool.find((p) => p.id === id))
      .filter(Boolean)
      .sort((a, b) => (b.xp ?? 0) - (a.xp ?? 0))[0]?.id ?? null
  return { starting, bench, captain, vice: null }
}

export default function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS)
  const [actualSquad, setActualSquad] = React.useState(EMPTY_SQUAD)
  const [actualPlayers, setActualPlayers] = React.useState([])
  const [displaySquad, setDisplaySquad] = React.useState(EMPTY_SQUAD)
  const [stagedTransfers, setStagedTransfers] = React.useState([])
  const [isSimulationMode, setIsSimulationMode] = React.useState(false)
  const [currentActiveGw, setCurrentActiveGw] = React.useState(null)
  const [players, setPlayers] = React.useState([])
  const [bankRemaining, setBankRemaining] = React.useState(0.5)
  const [freeTransfers, setFreeTransfers] = React.useState(1)
  const [availableChips, setAvailableChips] = React.useState([])
  const [gwMeta, setGwMeta] = React.useState({ gameweek: null, season: null })
  const [overallRank, setOverallRank] = React.useState(null)
  const [managerInitials, setManagerInitials] = React.useState('FC')
  const [xferPayload, setXferPayload] = React.useState(null)
  const [squadStats, setSquadStats] = React.useState(null)
  const [fplId, setFplId] = React.useState('')
  const [selectedGw, setSelectedGw] = React.useState(null)
  const [squadLayoutKey, setSquadLayoutKey] = React.useState(0)

  const [squadLoading, setSquadLoading] = React.useState(false)
  const [squadError, setSquadError] = React.useState(null)

  const [allPlayers, setAllPlayers] = React.useState([])
  const [allPlayersLoading, setAllPlayersLoading] = React.useState(true)
  const [allPlayersError, setAllPlayersError] = React.useState(null)
  const [selectedTeam, setSelectedTeam] = React.useState('ALL')
  const [sortConfig, setSortConfig] = React.useState({
    key: 'total_points',
    direction: 'desc',
  })

  const [selectedPlayer, setSelectedPlayer] = React.useState(null)
  const [view, setView] = React.useState('squad')
  const [optimRunning, setOptimRunning] = React.useState(false)
  const [optimError, setOptimError] = React.useState(null)

  const [isEditMode, setIsEditMode] = React.useState(false)
  const [activeEditPlayer, setActiveEditPlayer] = React.useState(null)
  const [swapSourceId, setSwapSourceId] = React.useState(null)
  const [hasManualEdits, setHasManualEdits] = React.useState(false)

  // Fetch a manager's squad from the hosted backend by FPL ID.
  // Hits ${VITE_API_BASE}/api/squad?entry=<fpl_id>; maps backend keys → UI state.
  const fetchManagerSquad = React.useCallback(async (id, gw = null) => {
    const clean = String(id ?? '').trim()
    if (!clean) return
    setSquadLoading(true)
    setSquadError(null)
    try {
      const params = new URLSearchParams()
      params.set('entry', clean)
      if (gw != null) params.set('gw', String(gw))
      const url = pitchcraftApiUrl(`/api/squad?${params.toString()}`)
      const res = await fetch(url)
      if (!res.ok) {
        const msg = await res.text().catch(() => '')
        throw new Error(msg || `Squad HTTP ${res.status}`)
      }
      const data = await res.json()
      // Backend may return a bare player list or an envelope {squad, players, …}.
      const rawList = Array.isArray(data) ? data : data.players || []
      const pool = rawList.map(normalizePlayer).filter((p) => p.id != null)
      const frozenPool = deepClone(pool.map((p) => mergePlayerProjectionFields(p)))
      setActualPlayers(frozenPool)
      setPlayers(deepClone(frozenPool))
      let activeGw = null
      let viewGw = gw != null ? Number(gw) : null
      if (!Array.isArray(data)) {
        if (typeof data.bank === 'number') setBankRemaining(data.bank)
        if (typeof data.available_free_transfers === 'number') {
          setFreeTransfers(data.available_free_transfers)
        } else if (typeof data.free_transfers === 'number') {
          setFreeTransfers(data.free_transfers)
        }
        if (Array.isArray(data.available_chips)) setAvailableChips(data.available_chips)
        setGwMeta({ gameweek: data.gameweek ?? null, season: data.season ?? null })
        setOverallRank(data.overall_rank ?? null)
        if (data.manager_initials) setManagerInitials(data.manager_initials)
        setSquadStats(data.squad_stats || null)
        activeGw =
          data.current_active_gw != null ? Number(data.current_active_gw) : null
        if (data.picks_gameweek != null) {
          viewGw = Number(data.picks_gameweek)
          setSelectedGw(viewGw)
        }
      }
      const resolvedActiveGw = activeGw ?? viewGw
      setCurrentActiveGw(resolvedActiveGw)
      const optimalSquad = buildOptimalPitchcraftSquad(pool)
      const sourceSquad = deepClone(optimalSquad || EMPTY_SQUAD)
      setActualSquad(deepClone(sourceSquad))
      setDisplaySquad(deepClone(sourceSquad))
      setStagedTransfers([])
      setIsSimulationMode(false)
      setSquadLayoutKey((k) => k + 1)
      setIsEditMode(false)
      setActiveEditPlayer(null)
      setSwapSourceId(null)
      setHasManualEdits(false)
      setSelectedPlayer(null)
      setXferPayload(null)
    } catch (e) {
      console.error('[fetchManagerSquad] failed:', e)
      setSquadError(e.message || String(e))
    } finally {
      setSquadLoading(false)
    }
  }, [])

  React.useEffect(() => {
    let cancelled = false
    setAllPlayersLoading(true)
    setAllPlayersError(null)
    const params = new URLSearchParams()
    if (selectedGw != null) params.set('gw', String(selectedGw))
    if (gwMeta.season) params.set('season', gwMeta.season)
    const qs = params.toString() ? `?${params.toString()}` : ''
    fetch(pitchcraftApiUrl(`/api/players${qs}`))
      .then((res) => {
        if (!res.ok) throw new Error(`Players HTTP ${res.status}`)
        return res.json()
      })
      .then((data) => {
        if (cancelled) return
        const raw = Array.isArray(data) ? data : data.players || []
        setAllPlayers(
          raw.map((p) => ({
            ...normalizePlayer(p),
            first_name: p.first_name ?? '',
            second_name: p.second_name ?? '',
            team: p.team ?? '',
            total_points: p.total_points ?? 0,
            form: p.form ?? '—',
            ep_next: p.ep_next,
            ep_this: p.ep_this,
            xg: p.xg,
            xa: p.xa,
            xga: p.xga,
            teamShort: p.teamShort,
            prediction_gw: p.prediction_gw ?? data.gameweek ?? selectedGw,
            xpts_source: p.xpts_source,
            gw_pts: p.gw_pts ?? p.gw_points ?? null,
            gw_points: p.gw_points ?? p.gw_pts ?? null,
          })),
        )
      })
      .catch((e) => {
        if (!cancelled) setAllPlayersError(e.message || String(e))
      })
      .finally(() => {
        if (!cancelled) setAllPlayersLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [selectedGw, gwMeta.season])

  // Step to a specific historical gameweek (re-fetches that GW's lineup).
  const goToGameweek = React.useCallback(
    (gw) => {
      if (!fplId.trim() || gw == null) return
      setSelectedGw(gw)
      fetchManagerSquad(fplId, gw)
    },
    [fplId, fetchManagerSquad],
  )

  // Optional convenience bootstrap: auto-load when a VITE_FPL_ENTRY_ID is baked
  // into the env. Otherwise we wait for the user to enter an ID + click Load Team.
  React.useEffect(() => {
    const entry = import.meta.env.VITE_FPL_ENTRY_ID
    if (entry) {
      setFplId(String(entry))
      fetchManagerSquad(String(entry))
    }
  }, [fetchManagerSquad])

  React.useEffect(() => {
    setIsSimulationMode(
      !squadsEqual(displaySquad, actualSquad) || stagedTransfers.length > 0,
    )
  }, [displaySquad, actualSquad, stagedTransfers])

  // Live gw_pts refresh for the active gameweek (FPL /event/{gw}/live/).
  React.useEffect(() => {
    if (!shouldPollLiveScores(selectedGw, currentActiveGw)) return undefined
    let cancelled = false

    const refreshLiveScores = () => {
      fetch(pitchcraftApiUrl(`/api/event/${encodeURIComponent(selectedGw)}/live-points`))
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (cancelled || !data?.points) return
          const liveMap = data.points
          setPlayers((prev) =>
            prev.map((p) => {
              const pts = liveMap[String(p.id)] ?? liveMap[p.id]
              if (pts == null) return p
              return { ...p, gw_points: Number(pts), gw_pts: Number(pts) }
            }),
          )
        })
        .catch(() => {})
    }

    refreshLiveScores()
    const timer = window.setInterval(refreshLiveScores, 60_000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [selectedGw, currentActiveGw])

  const allStartingIds = flattenStartingIds(displaySquad)
  const squadIds = new Set([...allStartingIds, ...(displaySquad.bench || [])])
  const squadEmpty = squadIds.size === 0

  const totalCost = [...allStartingIds, ...(displaySquad.bench || [])]
    .map((id) => players.find((p) => p.id === id))
    .filter(Boolean)
    .reduce((s, p) => s + (p.price || 0), 0)

  const totalXp = allStartingIds
    .map((id) => players.find((p) => p.id === id))
    .filter(Boolean)
    .reduce((s, p) => {
      const pts = p.xp ?? p.xPts ?? 0
      return s + (p.id === displaySquad.captain ? pts * 2 : pts)
    }, 0)

  const playersById = React.useMemo(() => {
    const m = new Map()
    for (const p of players) m.set(p.id, p)
    return m
  }, [players])

  const clearEditUi = () => {
    setActiveEditPlayer(null)
    setSwapSourceId(null)
  }

  const applySquadChange = (next) => {
    if (!squadsEqual(next, displaySquad)) {
      setDisplaySquad(deepClone(next))
      setHasManualEdits(true)
    }
  }

  const handleRevertSquad = () => {
    setPlayers(deepClone(actualPlayers).map((p) => mergePlayerProjectionFields(p)))
    setDisplaySquad(deepClone(actualSquad))
    setStagedTransfers([])
    setXferPayload(null)
    setHasManualEdits(false)
    setIsSimulationMode(false)
    setIsEditMode(false)
    clearEditUi()
    setSelectedPlayer(null)
    setSquadLayoutKey((k) => k + 1)
  }

  const handlePlayerClick = (p, zone = null) => {
    if (!isEditMode) {
      setSelectedPlayer(p)
      return
    }

    if (swapSourceId != null) {
      if (p.id !== swapSourceId) {
        applySquadChange(swapPlayers(displaySquad, swapSourceId, p.id, playersById))
      }
      clearEditUi()
      return
    }

    if (zone === 'pitch') {
      setActiveEditPlayer(p)
    }
  }

  const handleSetCaptain = (playerId) => {
    applySquadChange(setCaptain(displaySquad, playerId))
    clearEditUi()
  }

  const handleSetVice = (playerId) => {
    applySquadChange(setViceCaptain(displaySquad, playerId))
    clearEditUi()
  }

  const handleStartSwap = (playerId) => {
    setSwapSourceId(playerId)
    setActiveEditPlayer(null)
  }

  const handleToggleEditMode = () => {
    setIsEditMode((on) => !on)
    clearEditUi()
    setSelectedPlayer(null)
  }

  const handleRunOptim = async () => {
    const ids = squadPlayerIds(displaySquad)
    if (!fplId.trim() && ids.length !== 15) {
      setOptimError('Load a team (FPL ID) or fill all 15 squad slots before optimising.')
      return
    }
    setOptimRunning(true)
    setOptimError(null)
    try {
      const res = await fetch(pitchcraftApiUrl('/api/optimize'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          fpl_id: fplId.trim() || undefined,
          player_ids: ids,
          bank: bankRemaining,
          free_transfers: freeTransfers,
          gameweek: gwMeta.gameweek ?? undefined,
          season: gwMeta.season ?? undefined,
        }),
      })
      if (!res.ok) {
        const txt = await res.text().catch(() => '')
        throw new Error(txt || `Optimize HTTP ${res.status}`)
      }
      const data = await res.json()
      // Optimised player pool / lineup may come back with native backend keys.
      const optimisedPool = Array.isArray(data.players)
        ? data.players.map(normalizePlayer).filter((p) => p.id != null)
        : Array.isArray(data.lineup)
          ? data.lineup.map(normalizePlayer).filter((p) => p.id != null)
          : null
      if (optimisedPool) setPlayers(optimisedPool)
      const optimisedSquad =
        data.squad || (optimisedPool ? buildSquadFromPlayers(optimisedPool) : null)
      setDisplaySquad(deepClone(optimisedSquad || displaySquad))
      const xfer = data.transfers || null
      setXferPayload(xfer)
      setStagedTransfers(xfer?.transfers || [])
      if (typeof data.available_free_transfers === 'number') {
        setFreeTransfers(data.available_free_transfers)
      } else if (typeof xfer?.available_free_transfers === 'number') {
        setFreeTransfers(xfer.available_free_transfers)
      }
      if (Array.isArray(data.available_chips)) {
        setAvailableChips(data.available_chips)
      } else if (Array.isArray(xfer?.available_chips)) {
        setAvailableChips(xfer.available_chips)
      }
      setHasManualEdits(false)
      setIsEditMode(false)
      clearEditUi()
      if (typeof data.bank === 'number') setBankRemaining(data.bank)
      setGwMeta({
        gameweek: data.gameweek ?? gwMeta.gameweek,
        season: data.season ?? gwMeta.season,
      })
      setView('transfers')
    } catch (e) {
      setOptimError(e.message || String(e))
    } finally {
      setOptimRunning(false)
    }
  }

  const gwLabel =
    gwMeta.gameweek != null && gwMeta.season
      ? `${gwMeta.season} · GW${gwMeta.gameweek}`
      : 'FPL Optimizer'

  const resolveBuyPlayer = React.useCallback(
    (buyId, buyMeta) => {
      const targetId = Number(buyId)
      const fromGlobal = allPlayers.find((p) => Number(p.id) === targetId)
      const fromSquad = players.find((p) => Number(p.id) === targetId)
      if (fromGlobal) {
        return mergePlayerProjectionFields(fromGlobal)
      }
      if (fromSquad) {
        return mergePlayerProjectionFields(fromSquad)
      }
      if (!buyMeta) return null
      return mergePlayerProjectionFields(
        normalizePlayer({
          id: buyId,
          element: buyId,
          web_name: buyMeta.name,
          name: buyMeta.name,
          position: buyMeta.position,
          element_type: buyMeta.position,
          expected_pts: buyMeta.expected_pts,
          predicted_points: buyMeta.expected_pts ?? buyMeta.xp,
          xPts: buyMeta.expected_pts ?? buyMeta.xp,
          ep_next: buyMeta.ep_next,
          price: buyMeta.cost ?? buyMeta.price,
          team: buyMeta.team,
          teamShort: buyMeta.team,
        }),
      )
    },
    [players, allPlayers],
  )

  const handleApplyTransfers = React.useCallback(
    ({ selectedTransfers, activeChip }) => {
      if (!selectedTransfers?.length) return
      const { squad, players: nextPool } = applySelectedTransfers({
        players: deepClone(players),
        selectedTransfers,
        resolveBuyPlayer,
      })
      const sandboxPlayers = nextPool.map((p) => mergePlayerProjectionFields(p))
      setPlayers(sandboxPlayers)
      setDisplaySquad(deepClone(squad))
      setStagedTransfers(selectedTransfers)
      setHasManualEdits(false)
      setIsEditMode(false)
      clearEditUi()
      setSelectedPlayer(null)
      setSquadLayoutKey((k) => k + 1)
      if (activeChip) {
        setXferPayload((prev) => (prev ? { ...prev, active_chip: activeChip } : prev))
      }
      setView('squad')
    },
    [players, resolveBuyPlayer, clearEditUi],
  )

  const handleSortHeader = React.useCallback((key) => {
    setSortConfig((prev) => {
      if (prev.key === key) {
        return { key, direction: prev.direction === 'asc' ? 'desc' : 'asc' }
      }
      return { key, direction: key === 'name' ? 'asc' : 'desc' }
    })
  }, [])

  return (
    <div className={`app app-${t.theme}`} style={{ '--accent': t.accent }}>
      <Header
        view={view}
        setView={setView}
        totalXp={totalXp}
        theme={t.theme}
        gwLabel={gwLabel}
        overallRank={overallRank}
        initials={managerInitials}
        fplId={fplId}
        setFplId={setFplId}
        onLoadTeam={() => fetchManagerSquad(fplId)}
        loading={squadLoading}
        selectedGw={selectedGw}
        onGwChange={goToGameweek}
        isSimulationMode={isSimulationMode}
      />

      {squadLoading && (
        <div className="pc-loading" role="status">
          Loading squad & model projections…
        </div>
      )}
      {squadError && (
        <div className="pc-banner" role="alert">
          Couldn’t load squad — {squadError}
        </div>
      )}

      {view === 'squad' && (
        <div className="layout">
          <div className={`col col-pitch${isSimulationMode ? ' col-pitch-sim' : ''}`}>
            {squadEmpty && !squadLoading ? (
              <div className="pc-empty">
                <p className="pc-empty-msg">
                  Enter your FPL ID and click Load Team to view your squad.
                </p>
              </div>
            ) : (
              <>
                <PitchView
                  squad={displaySquad}
                  players={players}
                  selectedGw={selectedGw}
                  currentActiveGw={currentActiveGw}
                  onPlayerClick={handlePlayerClick}
                  theme={t.theme}
                  layoutKey={squadLayoutKey}
                  isEditMode={isEditMode}
                  activeEditPlayer={activeEditPlayer}
                  swapSourceId={swapSourceId}
                  onSetCaptain={handleSetCaptain}
                  onSetVice={handleSetVice}
                  onStartSwap={handleStartSwap}
                  onCancelEdit={clearEditUi}
                  onDismissEdit={clearEditUi}
                />
                <BenchView
                  squad={displaySquad}
                  players={players}
                  selectedGw={selectedGw}
                  currentActiveGw={currentActiveGw}
                  onPlayerClick={handlePlayerClick}
                  theme={t.theme}
                  isEditMode={isEditMode}
                  swapSourceId={swapSourceId}
                />
              </>
            )}
          </div>

          <div className="col col-side">
            <BudgetBar
              used={totalCost}
              total={100.0}
              remaining={bankRemaining}
              theme={t.theme}
            />
            <CaptainPanel
              squad={displaySquad}
              players={players}
              theme={t.theme}
              selectedGw={selectedGw}
              isEditMode={isEditMode}
            />
            <OptimizerPanel
              onRun={handleRunOptim}
              running={optimRunning}
              theme={t.theme}
              error={optimError}
              isEditMode={isEditMode}
              onToggleEdit={handleToggleEditMode}
              hasManualEdits={hasManualEdits}
              isSimulationMode={isSimulationMode}
              onRevert={handleRevertSquad}
            />
            <ChipPanel used={[]} theme={t.theme} />
          </div>

          <div className="col col-list">
            <SquadAnalytics stats={squadStats} theme={t.theme} />
            {!squadEmpty && (
              <SquadTable
                squad={displaySquad}
                players={players}
                loading={squadLoading}
                theme={t.theme}
                onPlayerClick={handlePlayerClick}
                selectedGw={selectedGw}
              />
            )}
          </div>
        </div>
      )}

      {view === 'players' && (
        <div className="layout layout-players">
          {allPlayersError && (
            <div className="pc-banner" role="alert">
              Couldn’t load player pool — {allPlayersError}
            </div>
          )}
          <AllPlayersTable
            players={allPlayers}
            loading={allPlayersLoading}
            theme={t.theme}
            squadIds={squadIds}
            onPlayerClick={setSelectedPlayer}
            selectedTeam={selectedTeam}
            onSelectedTeamChange={setSelectedTeam}
            sortConfig={sortConfig}
            onSortHeader={handleSortHeader}
          />
        </div>
      )}

      {view === 'transfers' && (
        <TransfersView
          xferPayload={xferPayload}
          theme={t.theme}
          onClose={() => setView('squad')}
          onApply={handleApplyTransfers}
          availableFreeTransfers={freeTransfers}
          availableChips={availableChips}
        />
      )}

      {selectedPlayer && !isEditMode && (
        <PlayerStatsModal
          player={selectedPlayer}
          selectedGw={selectedGw}
          onClose={() => setSelectedPlayer(null)}
          theme={t.theme}
        />
      )}

      <TweaksPanel>
        <TweakSection label="Theme" />
        <TweakRadio
          label="Visual style"
          value={t.theme}
          options={[
            { value: 'sporty', label: 'Sporty' },
            { value: 'terminal', label: 'Terminal' },
            { value: 'editorial', label: 'Editorial' },
          ]}
          onChange={(v) => setTweak('theme', v)}
        />
        <TweakColor label="Accent color" value={t.accent} onChange={(v) => setTweak('accent', v)} />
        <TweakSection label="Quick accents" />
        <div className="twk-swatches">
          {[
            { c: '#7CFF50', n: 'Pitch' },
            { c: '#FF4D4D', n: 'Heat' },
            { c: '#3DA5FF', n: 'Sky' },
            { c: '#FFB000', n: 'Amber' },
            { c: '#C77DFF', n: 'Violet' },
            { c: '#000000', n: 'Mono' },
          ].map((sw) => (
            <button
              key={sw.c}
              className="twk-sw"
              style={{ background: sw.c }}
              onClick={() => setTweak('accent', sw.c)}
              title={sw.n}
              type="button"
            />
          ))}
        </div>
      </TweaksPanel>
    </div>
  )
}

const GW_OPTIONS = Array.from({ length: 38 }, (_, i) => i + 1)

function Header({
  view,
  setView,
  totalXp,
  theme,
  gwLabel,
  overallRank,
  initials,
  fplId,
  setFplId,
  onLoadTeam,
  loading,
  selectedGw,
  onGwChange,
  isSimulationMode,
}) {
  const rankDisp =
    overallRank != null ? Number(overallRank).toLocaleString('en-GB') : '—'
  return (
    <header className={`hdr hdr-${theme}`} data-screen-label="Header">
      <div className="hdr-brand">
        <div className="hdr-mark">
          <span className="hdr-mark-d">▮▮▮</span>
        </div>
        <div className="hdr-name">
          <div className="hdr-title">PITCHCRAFT</div>
          <div className="hdr-sub">FPL Optimizer · {gwLabel}</div>
        </div>
      </div>
      <nav className="hdr-nav">
        <button
          className={view === 'squad' ? 'hdr-tab on' : 'hdr-tab'}
          onClick={() => setView('squad')}
          type="button"
        >
          Squad
        </button>
        <button
          className={view === 'players' ? 'hdr-tab on' : 'hdr-tab'}
          onClick={() => setView('players')}
          type="button"
        >
          Players
        </button>
        <button
          className={view === 'transfers' ? 'hdr-tab on' : 'hdr-tab'}
          onClick={() => setView('transfers')}
          type="button"
        >
          Transfers
        </button>
      </nav>
      {selectedGw != null && (
        <div className="hdr-gw" role="group" aria-label="Gameweek selection">
          <div className="hdr-gw-select-wrap">
            <select
              className="hdr-gw-select"
              value={String(selectedGw)}
              disabled={loading}
              aria-label="Select gameweek"
              onChange={(e) => onGwChange(Number(e.target.value))}
            >
              {GW_OPTIONS.map((gw) => (
                <option key={gw} value={gw}>
                  Gameweek {gw}
                </option>
              ))}
            </select>
            <span className="hdr-gw-chevron" aria-hidden="true">
              ▾
            </span>
          </div>
        </div>
      )}
      <div className="hdr-stats">
        <div className={`hdr-stat${isSimulationMode ? ' hdr-stat-sim' : ''}`}>
          <div className="hdr-stat-lbl">
            {isSimulationMode ? 'Simulated GW' : 'Projected GW'}
          </div>
          <div className="hdr-stat-val">{totalXp.toFixed(1)}</div>
        </div>
        <div className="hdr-stat">
          <div className="hdr-stat-lbl">Overall Rank</div>
          <div className="hdr-stat-val">{rankDisp}</div>
        </div>
        <div className="hdr-load">
          {initials && initials !== 'FC' && (
            <div className="hdr-avatar" title="Loaded manager">
              {initials}
            </div>
          )}
          <input
            className="hdr-load-input"
            type="text"
            inputMode="numeric"
            placeholder="FPL ID"
            value={fplId}
            onChange={(e) => setFplId(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') onLoadTeam()
            }}
            aria-label="Manager FPL ID"
          />
          <button
            className="hdr-load-btn"
            type="button"
            onClick={onLoadTeam}
            disabled={loading || !fplId.trim()}
          >
            {loading ? '…' : 'Load Team'}
          </button>
        </div>
      </div>
    </header>
  )
}
