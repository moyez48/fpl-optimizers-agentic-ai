import React from 'react'
import { exportCSV, exportJSON } from '../../utils/export'

export default function Dashboard({ agentData = null, userInput = null, onReset }) {
  if (!agentData) return null

  const gameweek  = agentData.gameweek ?? userInput?.gameweek ?? '—'
  const captain   = agentData.captainShortlist?.[0]
  const transfer  = agentData.transferRecommendation?.transfers?.[0] ?? null

  // Squad-specific xPts if available, otherwise global top 11
  const isSquadSpecific = Boolean(agentData.squadXPts != null)
  const displayXPts     = agentData.squadXPts ?? agentData.globalTop11XPts ?? 0
  const xPtsLabel       = isSquadSpecific ? 'Your Squad Top 11 xPts' : 'Global Top 11 xPts'

  // Position breakdown from squad players (live) or global top 50 (demo)
  const sourcePlayers = agentData.squadPlayers ?? agentData.rankedPlayers.slice(0, 50)
  const posBreakdown = ['GK', 'DEF', 'MID', 'FWD'].map(pos => {
    const players = sourcePlayers.filter(p => p.position === pos || (pos === 'GK' && p.position === 'GKP'))
    const pts = parseFloat(players.reduce((s, p) => s + p.xPts, 0).toFixed(1))
    return { label: pos, pts, color: pos === 'GK' ? '#FFB703' : pos === 'DEF' ? '#3B82F6' : pos === 'MID' ? '#00FF87' : '#E63946' }
  })
  const maxPos = Math.max(...posBreakdown.map(p => p.pts), 1)

  // Squad value from squad players
  const squadValue = agentData.squadPlayers
    ? parseFloat(agentData.squadPlayers.reduce((s, p) => s + (p.price ?? 0), 0).toFixed(1))
    : null

  const handleExportCSV  = () => exportCSV({ rankedPlayers: agentData.rankedPlayers })
  const handleExportJSON = () => exportJSON(agentData)

  const handleCopy = () => {
    const lines = [
      `FPL Optimizer GW${gameweek} Summary`,
      `${xPtsLabel}: ${displayXPts}`,
      captain ? `Captain: ${captain.name} (${captain.expectedPts} xPts)` : '',
      transfer ? `Top transfer: ${transfer.out?.name} → ${transfer.in?.name} (+${transfer.netGain?.toFixed(1)} net pts)` : '',
      squadValue ? `Squad value: £${squadValue}m` : '',
    ].filter(Boolean).join('\n')
    navigator.clipboard.writeText(lines).catch(() => {})
  }

  return (
    <div className="flex flex-col gap-4 pb-6">

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-fpl_text/40 uppercase tracking-widest">Results</p>
          <p className="text-lg font-black text-fpl_text">GW{gameweek} Dashboard</p>
          <p className="text-[10px] text-primary/70 mt-0.5">● Live agent data</p>
        </div>
        <button
          onClick={onReset}
          className="text-xs border border-white/10 text-fpl_text/40 px-3 py-1.5 rounded-lg hover:border-white/20 hover:text-fpl_text/60 transition-colors"
        >
          ↺ Re-run
        </button>
      </div>

      {/* Hero metric */}
      <div className="bg-gradient-to-br from-primary/15 to-secondary/5 rounded-2xl border border-primary/30 p-5">
        <p className="text-[10px] text-primary/60 uppercase tracking-widest mb-1">{xPtsLabel}</p>
        <p className="text-5xl font-black text-primary">{displayXPts}</p>
        <p className="text-xs text-fpl_text/40 mt-1">
          {isSquadSpecific ? 'Best XI from your imported squad' : 'Best XI globally — import FPL team for squad-specific analysis'}
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 gap-2">
        <div className="bg-card rounded-xl p-3 border border-white/5">
          <p className="text-[10px] text-fpl_text/40 uppercase tracking-widest">Captain Pick</p>
          <p className="text-base font-black text-primary truncate">{captain?.name ?? '—'}</p>
          <p className="text-[10px] text-fpl_text/40">{captain ? `${captain.expectedPts} xPts · ${(captain.startProb * 100).toFixed(0)}% start` : 'Run optimizer'}</p>
        </div>
        <div className="bg-card rounded-xl p-3 border border-white/5">
          <p className="text-[10px] text-fpl_text/40 uppercase tracking-widest">Squad Value</p>
          <p className="text-base font-black text-fpl_text">{squadValue != null ? `£${squadValue}m` : '—'}</p>
          <p className="text-[10px] text-fpl_text/40">{squadValue != null ? '15-player squad' : 'Import FPL team'}</p>
        </div>
        <div className="bg-card rounded-xl p-3 border border-white/5">
          <p className="text-[10px] text-fpl_text/40 uppercase tracking-widest">Squad injury flags</p>
          <p className="text-base font-black text-danger">{agentData.injuryAlerts?.length ?? 0}</p>
          <p className="text-[10px] text-fpl_text/40">
            {isSquadSpecific ? 'Your 15 only · see Manager tab' : 'Import FPL team'}
          </p>
        </div>
        <div className="bg-card rounded-xl p-3 border border-white/5">
          <p className="text-[10px] text-fpl_text/40 uppercase tracking-widest">Players Ranked</p>
          <p className="text-base font-black text-fpl_text">{agentData.rankedPlayers?.length ?? 0}</p>
          <p className="text-[10px] text-fpl_text/40">XGBoost predictions</p>
        </div>
      </div>

      {/* Position breakdown */}
      <div className="bg-card rounded-xl p-4 border border-white/5">
        <p className="text-xs font-semibold text-fpl_text/50 uppercase tracking-widest mb-1">
          {isSquadSpecific ? 'Squad Position Breakdown' : 'Top 50 Position Breakdown'}
        </p>
        <p className="text-[10px] text-fpl_text/30 mb-3">Total xPts by position</p>
        <div className="flex flex-col gap-3">
          {posBreakdown.map(({ label, pts, color }) => (
            <div key={label} className="flex items-center gap-3">
              <span className="text-[10px] font-bold text-fpl_text/40 w-7">{label}</span>
              <div className="flex-1 h-5 bg-white/5 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full flex items-center px-2 transition-all"
                  style={{ width: `${(pts / maxPos) * 100}%`, backgroundColor: color + '55', border: `1px solid ${color}40` }}
                >
                  <span className="text-[9px] font-bold" style={{ color }}>{pts}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Transfer impact (only if sporting director ran) */}
      {transfer && (
        <div className="bg-card rounded-xl p-4 border border-white/5">
          <p className="text-xs font-semibold text-fpl_text/50 uppercase tracking-widest mb-3">Top Transfer Recommendation</p>
          <div className="flex items-center gap-2">
            <div className="flex-1 text-center">
              <p className="text-[10px] text-danger/60 uppercase mb-1">OUT</p>
              <p className="text-sm font-bold text-fpl_text">{transfer.out?.name}</p>
              <p className="text-xs text-danger">{transfer.out?.xPts?.toFixed(1)} xPts</p>
            </div>
            <div className="flex flex-col items-center">
              <span className="text-primary text-xl">→</span>
              <span className="text-[10px] text-primary font-bold">+{transfer.netGain?.toFixed(1)} net</span>
            </div>
            <div className="flex-1 text-center">
              <p className="text-[10px] text-primary/60 uppercase mb-1">IN</p>
              <p className="text-sm font-bold text-fpl_text">{transfer.in?.name}</p>
              <p className="text-xs text-primary">{transfer.in?.xPts?.toFixed(1)} xPts</p>
            </div>
          </div>
          <div className="mt-3 flex justify-between text-xs text-fpl_text/40 border-t border-white/5 pt-3">
            <span>{transfer.isFreeTransfer ? 'Free transfer' : '-4 pt hit'}</span>
            <span className={`font-bold ${transfer.priority === 'HIGH' ? 'text-primary' : 'text-amber'}`}>{transfer.priority} priority</span>
          </div>
        </div>
      )}

      {!transfer && (
        <div className="bg-card rounded-xl p-4 border border-white/5 text-center">
          <p className="text-fpl_text/40 text-sm">No transfer data</p>
          <p className="text-fpl_text/25 text-xs mt-1">Import your FPL team for Sporting Director recommendations</p>
        </div>
      )}

      {/* Export */}
      <div className="bg-card rounded-xl p-4 border border-white/5">
        <p className="text-xs font-semibold text-fpl_text/50 uppercase tracking-widest mb-3">Export</p>
        <div className="grid grid-cols-2 gap-2 mb-2">
          <button onClick={handleExportCSV} className="py-3 rounded-xl border border-white/10 text-xs font-semibold text-fpl_text/60 hover:border-primary/30 hover:text-primary transition-all flex items-center justify-center gap-2">
            <span>⬇</span> Export CSV
          </button>
          <button onClick={handleExportJSON} className="py-3 rounded-xl border border-white/10 text-xs font-semibold text-fpl_text/60 hover:border-secondary/30 hover:text-secondary transition-all flex items-center justify-center gap-2">
            <span>⬇</span> Export JSON
          </button>
        </div>
        <button onClick={handleCopy} className="w-full py-3 rounded-xl border border-white/10 text-xs font-semibold text-fpl_text/60 hover:border-white/20 hover:text-fpl_text transition-all flex items-center justify-center gap-2">
          <span>📋</span> Copy Summary
        </button>
      </div>
    </div>
  )
}
