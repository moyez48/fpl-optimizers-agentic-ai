import React, { useState } from 'react'
import InputScreen   from './components/screens/InputScreen'
import LoadingScreen  from './components/screens/LoadingScreen'
import StatsScreen    from './components/screens/StatsScreen'
import ManagerScreen  from './components/screens/ManagerScreen'
import Dashboard      from './components/screens/Dashboard'

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

  const handleRun = (input) => {
    setUserInput(input)
    setScreen(SCREENS.LOADING)
  }

  const handleLoadingComplete = () => {
    setScreen(SCREENS.STATS)
  }

  const handleReset = () => {
    setScreen(SCREENS.INPUT)
    setUserInput(null)
  }

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
            {userInput && (
              <span className="text-[10px] font-bold text-primary/70 bg-primary/10 px-2 py-1 rounded-lg border border-primary/20">
                GW{userInput.gameweek}
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
        {screen === SCREENS.STATS    && <StatsScreen />}
        {screen === SCREENS.MANAGER  && <ManagerScreen />}
        {screen === SCREENS.DASHBOARD&& <Dashboard onReset={handleReset} />}
      </main>
    </div>
  )
}
