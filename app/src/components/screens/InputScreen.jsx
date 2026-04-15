import React, { useState, useMemo, useEffect } from 'react'
import { PLAYERS, DEMO_SQUAD_IDS } from '../../data/players'
import { isSquadValid, squadErrors, totalPrice, countByPosition } from '../../utils/formations'
import { importFPLTeam, fetchBootstrap, getCurrentEvent, transformPlayers } from '../../services/fplApi'
import PlayerCard from '../ui/PlayerCard'

const POSITIONS = ['GKP', 'DEF', 'MID', 'FWD']
const POS_TARGETS = { GKP: 2, DEF: 5, MID: 5, FWD: 3 }

// Import status states
const STATUS = { IDLE: 'idle', LOADING: 'loading', SUCCESS: 'success', ERROR: 'error' }

export default function InputScreen({ onRun }) {
  // ── Squad / config state ────────────────────────────────────────────────────
  const [playerPool, setPlayerPool] = useState(PLAYERS)  // can be swapped for real FPL data
  const [squadIds, setSquadIds]       = useState([])
  const [gameweek, setGameweek]       = useState(30)
  const [bank, setBank]               = useState(2.3)
  const [freeTransfers, setFreeTransfers] = useState(1)
  const [chips, setChips]             = useState({ tripleCaptain: true, benchBoost: true, wildcard: false, freeHit: false })
  const [riskTolerance, setRiskTolerance] = useState(50)
  const [searchQuery, setSearchQuery] = useState('')
  const [filterPos, setFilterPos]     = useState('ALL')
  const [showPicker, setShowPicker]   = useState(false)

  // ── Load real FPL players + current gameweek on mount ───────────────────────
  useEffect(() => {
    fetchBootstrap()
      .then(bootstrap => {
        const event = getCurrentEvent(bootstrap.events)
        if (event?.id) setGameweek(event.id)
        const realPlayers = transformPlayers(bootstrap)
        if (realPlayers.length > 0) setPlayerPool(realPlayers)
      })
      .catch(() => {}) // silently keep fake data if FPL API is unreachable
  }, [])

  // ── FPL import state ────────────────────────────────────────────────────────
  const [teamIdInput, setTeamIdInput] = useState('')
  const [importStatus, setImportStatus] = useState(STATUS.IDLE)
  const [importMessage, setImportMessage] = useState('')
  const [importedTeamInfo, setImportedTeamInfo] = useState(null)  // { teamName, managerName, ... }
  const isLiveData = importedTeamInfo !== null

  // ── Derived squad values ─────────────────────────────────────────────────────
  // Look up players from the current pool (works for both fake and real data)
  const squad    = squadIds.map(id => playerPool.find(p => p.id === id)).filter(Boolean)
  const valid    = isSquadValid(squad)
  const errors   = squadErrors(squad)
  const spent    = totalPrice(squad)
  const remaining = 100 - spent + bank
  const posCounts = countByPosition(squad)

  const filteredPool = useMemo(() => {
    return playerPool.filter(p => {
      if (squadIds.includes(p.id)) return false
      if (filterPos !== 'ALL' && p.position !== filterPos) return false
      if (searchQuery && !p.name.toLowerCase().includes(searchQuery.toLowerCase()) &&
          !p.team.toLowerCase().includes(searchQuery.toLowerCase())) return false
      return true
    }).sort((a, b) => b.xPts - a.xPts)
  }, [playerPool, squadIds, filterPos, searchQuery])

  // ── Squad actions ────────────────────────────────────────────────────────────
  const addPlayer    = (player) => {
    if (squadIds.length >= 15 || squadIds.includes(player.id)) return
    setSquadIds(prev => [...prev, player.id])
  }
  const removePlayer = (id) => setSquadIds(prev => prev.filter(x => x !== id))

  const loadDemo = () => {
    // Always reset to fake data pool when loading demo
    setPlayerPool(PLAYERS)
    setSquadIds([...DEMO_SQUAD_IDS])
    setImportedTeamInfo(null)
    setImportStatus(STATUS.IDLE)
    setImportMessage('')
  }

  const toggleChip   = (key) => setChips(prev => ({ ...prev, [key]: !prev[key] }))

  // ── FPL API import ───────────────────────────────────────────────────────────
  const handleImport = async () => {
    if (!teamIdInput.trim()) {
      setImportStatus(STATUS.ERROR)
      setImportMessage('Please enter your FPL Team ID.')
      return
    }

    setImportStatus(STATUS.LOADING)
    setImportMessage('')

    try {
      const result = await importFPLTeam(teamIdInput.trim())

      // Swap player pool to real FPL data and populate squad
      setPlayerPool(result.players)
      setSquadIds(result.squadIds)
      setGameweek(result.gameweek)
      setBank(parseFloat(result.bank.toFixed(1)))
      setFreeTransfers(result.freeTransfers)
      setChips(result.chips)
      setImportedTeamInfo(result.teamInfo)
      setImportStatus(STATUS.SUCCESS)
      setImportMessage(`Loaded GW${result.gameweek} squad — ${result.players.length} real players available.`)
    } catch (err) {
      setImportStatus(STATUS.ERROR)
      setImportMessage(err.message || 'Failed to import. Check your Team ID and try again.')
    }
  }

  const handleClearImport = () => {
    setPlayerPool(PLAYERS)
    setSquadIds([])
    setImportedTeamInfo(null)
    setImportStatus(STATUS.IDLE)
    setImportMessage('')
    setTeamIdInput('')
  }

  // ─────────────────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-4 pb-6">

      {/* ── Header bar ──────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs text-fpl_text/40 uppercase tracking-widest">Squad Setup</p>
          <p className="text-lg font-black text-fpl_text">GW{gameweek} Optimizer</p>
        </div>
        <button
          onClick={loadDemo}
          className="text-xs border border-secondary/40 text-secondary px-3 py-1.5 rounded-lg hover:bg-secondary/10 transition-colors"
        >
          Load Demo Squad
        </button>
      </div>

      {/* ── FPL Import card ─────────────────────────────────────────────────── */}
      <div className="bg-card rounded-xl border border-white/5 overflow-hidden">
        {/* Card header */}
        <div className="flex items-center gap-2 px-4 pt-4 pb-3 border-b border-white/5">
          <span className="text-primary text-sm">🔗</span>
          <p className="text-xs font-bold text-fpl_text tracking-wide">Import from FPL</p>
          {isLiveData && (
            <span className="ml-auto text-[10px] font-bold text-primary bg-primary/10 border border-primary/20 px-2 py-0.5 rounded-full">
              LIVE DATA
            </span>
          )}
        </div>

        <div className="p-4 flex flex-col gap-3">
          {/* Success state: show team info */}
          {importedTeamInfo ? (
            <div className="flex flex-col gap-2">
              <div className="bg-primary/10 border border-primary/20 rounded-lg p-3 flex items-start gap-3">
                <span className="text-primary text-lg mt-0.5">✓</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-bold text-primary truncate">{importedTeamInfo.teamName}</p>
                  <p className="text-xs text-fpl_text/60">{importedTeamInfo.managerName}</p>
                  {importedTeamInfo.overallRank && (
                    <p className="text-[10px] text-fpl_text/40 mt-0.5">
                      Overall rank: #{importedTeamInfo.overallRank.toLocaleString()} · {importedTeamInfo.overallPoints} pts
                    </p>
                  )}
                </div>
              </div>
              <p className="text-[10px] text-fpl_text/40 text-center">{importMessage}</p>
              <button
                onClick={handleClearImport}
                className="text-xs text-fpl_text/40 hover:text-danger transition-colors text-center"
              >
                × Clear import &amp; use demo data
              </button>
            </div>
          ) : (
            /* Input state */
            <div className="flex flex-col gap-3">
              <div className="flex gap-2">
                <div className="flex-1">
                  <input
                    type="number"
                    min={1}
                    placeholder="Your FPL Team ID"
                    value={teamIdInput}
                    onChange={e => setTeamIdInput(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleImport()}
                    className="w-full bg-surface rounded-lg px-3 py-2.5 text-sm text-fpl_text placeholder-fpl_text/30 outline-none border border-white/5 focus:border-primary/40 transition-colors"
                  />
                </div>
                <button
                  onClick={handleImport}
                  disabled={importStatus === STATUS.LOADING}
                  className={`px-4 py-2.5 rounded-lg text-xs font-bold transition-all whitespace-nowrap
                    ${importStatus === STATUS.LOADING
                      ? 'bg-primary/20 text-primary/50 cursor-not-allowed'
                      : 'bg-primary text-background hover:bg-primary/90 active:scale-95'}`}
                >
                  {importStatus === STATUS.LOADING ? (
                    <span className="flex items-center gap-1.5">
                      <span className="inline-block w-3 h-3 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
                      Loading…
                    </span>
                  ) : 'Import Team'}
                </button>
              </div>

              {/* Error message */}
              {importStatus === STATUS.ERROR && (
                <p className="text-xs text-danger bg-danger/10 border border-danger/20 rounded-lg px-3 py-2">
                  ⚠ {importMessage}
                </p>
              )}

              {/* Help text */}
              <p className="text-[10px] text-fpl_text/30 leading-relaxed">
                Find your Team ID in the FPL URL:{' '}
                <span className="font-mono text-fpl_text/40">
                  fantasy.premierleague.com/entry/<span className="text-secondary">{'{your-id}'}</span>/history
                </span>
              </p>
            </div>
          )}
        </div>
      </div>

      {/* ── Config row ──────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-3 gap-2">
        <div className="bg-card rounded-xl p-3 border border-white/5">
          <p className="text-[10px] text-fpl_text/40 uppercase tracking-widest mb-1">Gameweek</p>
          <input
            type="number" min={1} max={38}
            value={gameweek}
            onChange={e => setGameweek(Number(e.target.value))}
            className="w-full bg-transparent text-lg font-black text-fpl_text outline-none"
          />
        </div>
        <div className="bg-card rounded-xl p-3 border border-white/5">
          <p className="text-[10px] text-fpl_text/40 uppercase tracking-widest mb-1">Bank</p>
          <div className="flex items-baseline gap-0.5">
            <span className="text-fpl_text/40 text-xs">£</span>
            <input
              type="number" min={0} max={10} step={0.1}
              value={bank}
              onChange={e => setBank(parseFloat(e.target.value) || 0)}
              className="w-full bg-transparent text-lg font-black text-fpl_text outline-none"
            />
            <span className="text-fpl_text/40 text-xs">m</span>
          </div>
        </div>
        <div className="bg-card rounded-xl p-3 border border-white/5">
          <p className="text-[10px] text-fpl_text/40 uppercase tracking-widest mb-1">Free Xfers</p>
          <input
            type="number" min={0} max={2}
            value={freeTransfers}
            onChange={e => setFreeTransfers(Number(e.target.value))}
            className="w-full bg-transparent text-lg font-black text-fpl_text outline-none"
          />
        </div>
      </div>

      {/* ── Chips ───────────────────────────────────────────────────────────── */}
      <div className="bg-card rounded-xl p-4 border border-white/5">
        <p className="text-[10px] text-fpl_text/40 uppercase tracking-widest mb-3">Available Chips</p>
        <div className="grid grid-cols-2 gap-2">
          {[
            { key: 'tripleCaptain', label: 'Triple Captain', icon: '⚡' },
            { key: 'benchBoost',   label: 'Bench Boost',     icon: '📈' },
            { key: 'wildcard',     label: 'Wildcard',        icon: '🃏' },
            { key: 'freeHit',      label: 'Free Hit',        icon: '🎯' },
          ].map(({ key, label, icon }) => (
            <button
              key={key}
              onClick={() => toggleChip(key)}
              className={`flex items-center gap-2 rounded-lg px-3 py-2 border text-sm font-medium transition-all
                ${chips[key]
                  ? 'bg-primary/15 border-primary/40 text-primary'
                  : 'bg-surface border-white/5 text-fpl_text/30'}`}
            >
              <span>{icon}</span>
              <span className="text-xs">{label}</span>
              <span className="ml-auto text-[10px]">{chips[key] ? '✓' : '✕'}</span>
            </button>
          ))}
        </div>
      </div>

      {/* ── Risk Tolerance ──────────────────────────────────────────────────── */}
      <div className="bg-card rounded-xl p-4 border border-white/5">
        <div className="flex justify-between items-center mb-2">
          <p className="text-[10px] text-fpl_text/40 uppercase tracking-widest">Risk Tolerance</p>
          <span className="text-xs font-bold text-primary">{riskTolerance}%</span>
        </div>
        <input
          type="range" min={0} max={100} value={riskTolerance}
          onChange={e => setRiskTolerance(Number(e.target.value))}
        />
        <div className="flex justify-between text-[10px] text-fpl_text/30 mt-1">
          <span>Conservative</span>
          <span>Aggressive</span>
        </div>
      </div>

      {/* ── Squad status ─────────────────────────────────────────────────────── */}
      <div className="bg-card rounded-xl p-4 border border-white/5">
        <div className="flex justify-between items-center mb-3">
          <p className="text-[10px] text-fpl_text/40 uppercase tracking-widest">
            Squad ({squad.length}/15)
            {isLiveData && (
              <span className="ml-2 text-primary">· live</span>
            )}
          </p>
          <p className="text-xs text-fpl_text/50">
            Budget:{' '}
            <span className={remaining < 0 ? 'text-danger font-bold' : 'text-primary font-bold'}>
              £{remaining.toFixed(1)}m left
            </span>
          </p>
        </div>

        {/* Position counters */}
        <div className="flex gap-2 mb-4">
          {POSITIONS.map(pos => (
            <div
              key={pos}
              className={`flex-1 rounded-lg py-1.5 text-center border
                ${(posCounts[pos] || 0) === POS_TARGETS[pos]
                  ? 'bg-primary/10 border-primary/30'
                  : 'bg-surface border-white/5'}`}
            >
              <p className="text-[9px] text-fpl_text/40">{pos}</p>
              <p className={`text-sm font-black ${(posCounts[pos] || 0) === POS_TARGETS[pos] ? 'text-primary' : 'text-fpl_text'}`}>
                {posCounts[pos] || 0}/{POS_TARGETS[pos]}
              </p>
            </div>
          ))}
        </div>

        {/* Squad by position */}
        {POSITIONS.map(pos => {
          const posPlayers = squad.filter(p => p.position === pos)
          if (posPlayers.length === 0) return null
          return (
            <div key={pos} className="mb-3">
              <p className="text-[10px] text-fpl_text/30 mb-1.5 uppercase tracking-wider">{pos}</p>
              <div className="flex flex-col gap-1.5">
                {posPlayers.map(player => (
                  <PlayerCard
                    key={player.id}
                    player={player}
                    compact
                    showRemove
                    onClick={() => removePlayer(player.id)}
                  />
                ))}
              </div>
            </div>
          )
        })}

        {/* Add player button */}
        {squad.length < 15 && (
          <button
            onClick={() => setShowPicker(true)}
            className="w-full mt-2 border-2 border-dashed border-white/10 rounded-xl py-3 text-sm text-fpl_text/30 hover:border-primary/30 hover:text-primary transition-all"
          >
            + Add Player
          </button>
        )}
      </div>

      {/* ── Validation errors ────────────────────────────────────────────────── */}
      {errors.length > 0 && (
        <div className="bg-danger/10 border border-danger/20 rounded-xl p-3">
          {errors.map((e, i) => (
            <p key={i} className="text-xs text-danger">{e}</p>
          ))}
        </div>
      )}

      {/* ── Run button ──────────────────────────────────────────────────────── */}
      <button
        onClick={() => valid && onRun({ squadIds, gameweek, bank, freeTransfers, chips, riskTolerance, players: playerPool, isLiveData })}
        disabled={!valid}
        className={`w-full py-4 rounded-xl text-base font-black tracking-wide transition-all duration-200
          ${valid
            ? 'bg-primary text-background shadow-lg shadow-primary/20 hover:shadow-primary/40 hover:scale-[1.01] active:scale-[0.99]'
            : 'bg-white/5 text-fpl_text/20 cursor-not-allowed'}`}
      >
        {valid
          ? `▶  Run Optimizer (3 Agents)${isLiveData ? ' · Live Data' : ''}`
          : `Complete squad to continue (${15 - squad.length} left)`}
      </button>

      {/* ── Player Picker Modal ──────────────────────────────────────────────── */}
      {showPicker && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-end sm:items-center justify-center p-4">
          <div className="bg-surface rounded-2xl w-full max-w-md max-h-[80vh] flex flex-col border border-white/10 shadow-2xl">
            <div className="flex items-center justify-between p-4 border-b border-white/5">
              <div>
                <p className="font-bold text-fpl_text">Add Player</p>
                {isLiveData && (
                  <p className="text-[10px] text-primary/60 mt-0.5">Live FPL player pool</p>
                )}
              </div>
              <button
                onClick={() => setShowPicker(false)}
                className="text-fpl_text/40 hover:text-fpl_text text-xl leading-none"
              >
                ×
              </button>
            </div>

            {/* Search */}
            <div className="p-3 border-b border-white/5">
              <input
                autoFocus
                placeholder="Search name or team…"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                className="w-full bg-card rounded-lg px-3 py-2 text-sm text-fpl_text placeholder-fpl_text/30 outline-none border border-white/5 focus:border-primary/40"
              />
              <div className="flex gap-2 mt-2">
                {['ALL', ...POSITIONS].map(pos => (
                  <button
                    key={pos}
                    onClick={() => setFilterPos(pos)}
                    className={`flex-1 py-1 rounded-lg text-[10px] font-bold transition-colors
                      ${filterPos === pos ? 'bg-primary text-background' : 'bg-card text-fpl_text/40 hover:text-fpl_text'}`}
                  >
                    {pos}
                  </button>
                ))}
              </div>
            </div>

            {/* Player list */}
            <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-1.5">
              {filteredPool.slice(0, 50).map(player => (
                <button
                  key={player.id}
                  onClick={() => { addPlayer(player); setShowPicker(false); setSearchQuery('') }}
                  className="w-full text-left"
                >
                  <PlayerCard player={player} compact />
                </button>
              ))}
              {filteredPool.length === 0 && (
                <p className="text-center text-sm text-fpl_text/30 py-8">No players found</p>
              )}
              {filteredPool.length > 50 && (
                <p className="text-center text-[10px] text-fpl_text/30 py-2">
                  Showing 50 of {filteredPool.length} — search to filter
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
