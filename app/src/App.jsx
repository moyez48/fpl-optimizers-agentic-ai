import React, { useState, useRef, useCallback } from 'react'
import InputScreen   from './components/screens/InputScreen'
import LoadingScreen  from './components/screens/LoadingScreen'
import StatsScreen    from './components/screens/StatsScreen'
import ManagerScreen  from './components/screens/ManagerScreen'
import Dashboard      from './components/screens/Dashboard'
import {
  fetchStats,
  adaptToStatsOutput,
  fetchTransfers,
  adaptToTransferOutput,
  fetchManager,
  adaptToManagerOutput,
  parseDatasetGwMaxFromStatsError,
} from './services/statsAgent'

// App screens in order
const SCREENS = {
  INPUT:    'input',
  LOADING:  'loading',
  STATS:    'stats',
  MANAGER:  'manager',
  DASHBOARD:'dashboard',
}

const RESULT_TABS = [
  { key: SCREENS.STATS,    label: 'Stats',    icon: '📊' },
  { key: SCREENS.MANAGER,  label: 'Manager',  icon: '🏟️' },
  { key: SCREENS.DASHBOARD,label: 'Dashboard',icon: '📈' },
]

export default function App() {
  const [screen, setScreen] = useState(SCREENS.INPUT)
  const [userInput, setUserInput] = useState(null)
  const [agentData, setAgentData] = useState(null)
  const [agentError, setAgentError] = useState(null)
  const [statsGwLoading, setStatsGwLoading] = useState(false)
  const [agentWarning, setAgentWarning] = useState(null)
  /** Upper GW bound for the CSV/model (from API or inferred when a bad GW request fails). */
  const [gwDatasetCap, setGwDatasetCap] = useState(null)

  // Holds the in-flight API promises so LoadingScreen can await them
  const statsPromiseRef     = useRef(null)
  const transfersPromiseRef = useRef(null)
  const managerPromiseRef   = useRef(null)
  const userInputRef        = useRef(null)

  const handleRun = (input) => {
    setUserInput(input)
    userInputRef.current = input
    setAgentData(null)
    setAgentError(null)

    // Kick off stats call immediately — runs in parallel with the loading animation
    statsPromiseRef.current = fetchStats({ gameweek: input.gameweek ?? null })

    // Kick off Sporting Director call only when the user has a real FPL squad
    // (demo/fake player IDs won't match FPL element IDs in the dataset)
    if (input.isLiveData && input.squadIds?.length === 15) {
      transfersPromiseRef.current = fetchTransfers({
        playerIds:     input.squadIds,
        bank:          input.bank ?? 0,
        freeTransfers: input.freeTransfers ?? 1,
        gameweek:      input.gameweek ?? null,
      })
      managerPromiseRef.current = fetchManager({
        playerIds:     input.squadIds,
        bank:          input.bank ?? 0,
        gameweek:      input.gameweek ?? null,
        tripleCaptain: input.chips?.tripleCaptain ?? true,
        benchBoost:    input.chips?.benchBoost ?? true,
      })
    } else {
      transfersPromiseRef.current = null
      managerPromiseRef.current = null
    }

    setScreen(SCREENS.LOADING)
  }

  // Called by LoadingScreen when its animation finishes.
  // Awaits both API promises so the screen only advances once all data is ready.
  const handleLoadingComplete = async () => {
    try {
      const rawStats = await statsPromiseRef.current
      if (!rawStats || typeof rawStats !== 'object') {
        throw new Error(
          'No stats response from /api/stats. Start the API and check app/vite.config.js proxy (VITE_API_PROXY → your port).'
        )
      }
      const allRanked = rawStats.ranked?.ALL
      if (!Array.isArray(allRanked) || allRanked.length === 0) {
        throw new Error(
          'Stats API returned no players (ranked.ALL is empty). Restart uvicorn so the cache resets (schema bump) and try again.'
        )
      }
      const squadIds = userInputRef.current?.isLiveData ? userInputRef.current?.squadIds : null
      const adapted = adaptToStatsOutput(rawStats, squadIds)

      // Transfers are optional — don't fail the whole pipeline if they error
      if (transfersPromiseRef.current) {
        try {
          const rawTransfers = await transfersPromiseRef.current
          adapted.transferRecommendation = adaptToTransferOutput(rawTransfers)
        } catch (_transferErr) {
          // Transfers failed but stats succeeded — continue without them
        }
      }

      if (managerPromiseRef.current) {
        try {
          const rawManager = await managerPromiseRef.current
          adapted.managerRecommendation = adaptToManagerOutput(rawManager)
        } catch (_mgrErr) {
          // Manager agent optional if it errors independently
        }
      }

      if (adapted.transferRecommendation?.planningGameweek != null) {
        adapted.planningGameweek = adapted.transferRecommendation.planningGameweek
      }

      const gwCap = adapted.datasetMaxGw ?? adapted.gameweek
      if (gwCap != null) {
        setGwDatasetCap(gwCap)
      }
      setAgentWarning(adapted.gwFallbackWarning ?? null)
      setAgentData(adapted)
    } catch (err) {
      setAgentError(err.message ?? String(err))
    }
    setScreen(SCREENS.STATS)
  }

  const handleReset = () => {
    setScreen(SCREENS.INPUT)
    setUserInput(null)
    setAgentData(null)
    setAgentError(null)
    setAgentWarning(null)
    setStatsGwLoading(false)
    setGwDatasetCap(null)
  }

  const handleStatsGameweekChange = useCallback(async (gw) => {
    const ui = userInputRef.current
    if (!ui || gw == null || Number.isNaN(Number(gw))) return
    const g = Number(gw)
    const max = gwDatasetCap ?? agentData?.datasetMaxGw ?? agentData?.gameweek
    if (max != null && g > max) {
      setAgentError(
        `GW${g} is not in the dataset yet (available: GW1–GW${max}). Refresh data after that gameweek is processed.`,
      )
      return
    }
    setStatsGwLoading(true)
    setAgentError(null)
    try {
      const rawStats = await fetchStats({ gameweek: g, season: null })
      const allRanked = rawStats.ranked?.ALL
      if (!Array.isArray(allRanked) || allRanked.length === 0) {
        throw new Error(
          rawStats.detail || `No model rows for GW${g}. Pick GW1–GW${max ?? '?'}.`,
        )
      }
      const squadIds = ui.isLiveData ? ui.squadIds : null
      let adapted = adaptToStatsOutput(rawStats, squadIds)

      if (ui.isLiveData && ui.squadIds?.length === 15) {
        try {
          const [rawTransfers, rawManager] = await Promise.all([
            fetchTransfers({
              playerIds: ui.squadIds,
              bank: ui.bank ?? 0,
              freeTransfers: ui.freeTransfers ?? 1,
              gameweek: g,
            }),
            fetchManager({
              playerIds: ui.squadIds,
              bank: ui.bank ?? 0,
              gameweek: g,
              tripleCaptain: ui.chips?.tripleCaptain ?? true,
              benchBoost: ui.chips?.benchBoost ?? true,
            }),
          ])
          adapted.transferRecommendation = adaptToTransferOutput(rawTransfers)
          adapted.managerRecommendation = adaptToManagerOutput(rawManager)
          if (adapted.transferRecommendation?.planningGameweek != null) {
            adapted.planningGameweek = adapted.transferRecommendation.planningGameweek
          }
        } catch (_e) {
          /* keep stats-only */
        }
      }

      const gwCap = adapted.datasetMaxGw ?? adapted.gameweek
      if (gwCap != null) {
        setGwDatasetCap(gwCap)
      }
      setAgentWarning(adapted.gwFallbackWarning ?? null)
      setAgentData(adapted)
    } catch (err) {
      const msg = err.message ?? String(err)
      const inferred = parseDatasetGwMaxFromStatsError(msg)
      if (inferred != null) {
        setGwDatasetCap((prev) => (prev == null ? inferred : Math.min(prev, inferred)))
      }
      setAgentError(msg)
    } finally {
      setStatsGwLoading(false)
    }
  }, [agentData?.datasetMaxGw, agentData?.gameweek, gwDatasetCap])

  const isResultScreen = [SCREENS.STATS, SCREENS.MANAGER, SCREENS.DASHBOARD].includes(screen)

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* ── Top nav bar ────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-40 bg-surface/80 backdrop-blur border-b border-white/5">
        <div className="max-w-lg mx-auto px-4 h-14 flex items-center justify-between">
          {/* Logo */}
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-primary flex items-center justify-center">
              <span className="text-background text-sm font-black">F</span>
            </div>
            <span className="font-black text-fpl_text text-sm tracking-tight">FPL Optimizer</span>
          </div>

          {/* GW badge */}
          <div className="flex items-center gap-2">
            {agentData?.gameweek != null && (
              <span className="text-[10px] font-bold text-primary/70 bg-primary/10 px-2 py-1 rounded-lg border border-primary/20">
                GW{agentData.gameweek}
              </span>
            )}
            {screen !== SCREENS.INPUT && screen !== SCREENS.LOADING && (
              <button
                onClick={handleReset}
                className="text-[10px] text-fpl_text/30 hover:text-fpl_text transition-colors"
              >
                ← New squad
              </button>
            )}
          </div>
        </div>
      </header>

      {/* ── Step indicator (INPUT + LOADING only) ──────────────────────── */}
      {(screen === SCREENS.INPUT || screen === SCREENS.LOADING) && (
        <div className="bg-surface border-b border-white/5">
          <div className="max-w-lg mx-auto px-4 py-2 flex items-center gap-2">
            {[
              { label: '1. Squad Setup',  active: screen === SCREENS.INPUT   },
              { label: '2. Processing',   active: screen === SCREENS.LOADING },
              { label: '3. Results',      active: false },
            ].map((step, i, arr) => (
              <React.Fragment key={step.label}>
                <span className={`text-[10px] font-semibold whitespace-nowrap ${step.active ? 'text-primary' : 'text-fpl_text/20'}`}>
                  {step.label}
                </span>
                {i < arr.length - 1 && <span className="text-fpl_text/10 text-[10px]">›</span>}
              </React.Fragment>
            ))}
          </div>
        </div>
      )}

      {/* ── Result tab bar (STATS / MANAGER / DASHBOARD) ───────────────── */}
      {isResultScreen && (
        <div className="sticky top-14 z-30 bg-surface border-b border-white/5">
          <div className="max-w-lg mx-auto px-4">
            <div className="flex">
              {RESULT_TABS.map(tab => (
                <button
                  key={tab.key}
                  onClick={() => setScreen(tab.key)}
                  className={`flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-semibold border-b-2 transition-all
                    ${screen === tab.key
                      ? 'border-primary text-primary'
                      : 'border-transparent text-fpl_text/30 hover:text-fpl_text/60'}`}
                >
                  <span>{tab.icon}</span>
                  <span>{tab.label}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Main content ───────────────────────────────────────────────── */}
      <main className="flex-1 max-w-lg mx-auto w-full px-4 pt-4">
        {screen === SCREENS.INPUT    && <InputScreen    onRun={handleRun} />}
        {screen === SCREENS.LOADING  && <LoadingScreen  onComplete={handleLoadingComplete} />}
        {screen === SCREENS.STATS    && (
          <StatsScreen
            agentData={agentData}
            agentError={agentError}
            agentWarning={agentWarning}
            userInput={userInput}
            statsGwLoading={statsGwLoading}
            onGameweekChange={handleStatsGameweekChange}
            selectableGwMax={gwDatasetCap ?? agentData?.datasetMaxGw ?? agentData?.gameweek ?? null}
          />
        )}
        {screen === SCREENS.MANAGER  && <ManagerScreen agentData={agentData} userInput={userInput} />}
        {screen === SCREENS.DASHBOARD&& <Dashboard agentData={agentData} userInput={userInput} onReset={handleReset} />}
      </main>
    </div>
  )
}
