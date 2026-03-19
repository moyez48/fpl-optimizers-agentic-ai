import React from 'react'
import { DEMO_SUMMARY, DEMO_MANAGER_OUTPUT, DEMO_TRANSFER_OUTPUT } from '../../data/demoOutput'
import SummaryCard from '../ui/SummaryCard'
import PointsChart from '../ui/PointsChart'
import { exportCSV, exportJSON } from '../../utils/export'

const POS_BREAKDOWN = [
  { label: 'GKP', pts: 7.6,  color: '#FFB703' },
  { label: 'DEF', pts: 33.1, color: '#3B82F6' },
  { label: 'MID', pts: 44.2, color: '#00FF87' },
  { label: 'FWD', pts: 39.4, color: '#E63946', note: '(incl. TC)' },
]
const MAX_POS = Math.max(...POS_BREAKDOWN.map(p => p.pts))

export default function Dashboard({ onReset }) {
  const { currentXPts, optimizedXPts, gainVsCurrent, recommendedCaptain, chipUsed, chartData, squadValueAfter } = DEMO_SUMMARY
  const transfer = DEMO_TRANSFER_OUTPUT.recommended[0]

  const handleExportCSV  = () => exportCSV(DEMO_MANAGER_OUTPUT)
  const handleExportJSON = () => exportJSON(DEMO_SUMMARY)

  const handleCopy = () => {
    const text = `FPL Optimizer GW25 Summary\n` +
      `Projected pts: ${optimizedXPts} (+${gainVsCurrent} vs current)\n` +
      `Captain: ${recommendedCaptain} (${chipUsed})\n` +
      `Transfer: ${transfer.out.name} → ${transfer.in.name} (+${transfer.netGain.toFixed(1)} net pts)\n` +
      `Squad value: £${squadValueAfter}m`
    navigator.clipboard.writeText(text).catch(() => {})
  }

  return (
    <div className="flex flex-col gap-4 pb-6">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-fpl_text/40 uppercase tracking-widest">Results</p>
          <p className="text-lg font-black text-fpl_text">GW25 Dashboard</p>
        </div>
        <button
          onClick={onReset}
          className="text-xs border border-white/10 text-fpl_text/40 px-3 py-1.5 rounded-lg hover:border-white/20 hover:text-fpl_text/60 transition-colors"
        >
          ↺ Re-run
        </button>
      </div>

      {/* Key metric — gain hero card */}
      <div className="bg-gradient-to-br from-primary/15 to-secondary/5 rounded-2xl border border-primary/30 p-5">
        <p className="text-[10px] text-primary/60 uppercase tracking-widest mb-1">Total pts gain</p>
        <div className="flex items-end gap-3">
          <p className="text-5xl font-black text-primary">+{gainVsCurrent}</p>
          <div className="pb-1">
            <p className="text-sm text-fpl_text/60">pts vs current</p>
            <p className="text-xs text-fpl_text/40">{currentXPts} → {optimizedXPts} projected</p>
          </div>
        </div>
      </div>

      {/* Summary cards grid */}
      <div className="grid grid-cols-2 gap-2">
        <SummaryCard
          label="Projected"
          value={optimizedXPts}
          sub="with Triple Captain"
          icon="📊"
          accent
        />
        <SummaryCard
          label="Squad Value"
          value={`£${squadValueAfter}m`}
          sub="after transfer"
          icon="💰"
        />
        <SummaryCard
          label="Captain"
          value={recommendedCaptain}
          sub={chipUsed}
          icon="©"
          accent
        />
        <SummaryCard
          label="Bank"
          value={`£${DEMO_TRANSFER_OUTPUT.recommended[0]?.bankAfter ?? 2.3}m`}
          sub="remaining"
          icon="🏦"
        />
      </div>

      {/* Points chart */}
      <div className="bg-card rounded-xl p-4 border border-white/5">
        <p className="text-xs font-semibold text-fpl_text/50 mb-1 uppercase tracking-widest">Points History</p>
        <p className="text-[10px] text-fpl_text/30 mb-3">Actual vs GW25 projected</p>
        <PointsChart data={chartData} />
      </div>

      {/* Position breakdown */}
      <div className="bg-card rounded-xl p-4 border border-white/5">
        <p className="text-xs font-semibold text-fpl_text/50 uppercase tracking-widest mb-3">Position Breakdown</p>
        <div className="flex flex-col gap-3">
          {POS_BREAKDOWN.map(({ label, pts, color, note }) => (
            <div key={label} className="flex items-center gap-3">
              <span className="text-[10px] font-bold text-fpl_text/40 w-7">{label}</span>
              <div className="flex-1 h-5 bg-white/5 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full flex items-center px-2 transition-all"
                  style={{ width: `${(pts / MAX_POS) * 100}%`, backgroundColor: color + '55', border: `1px solid ${color}40` }}
                >
                  <span className="text-[9px] font-bold" style={{ color }}>{pts}</span>
                </div>
              </div>
              {note && <span className="text-[9px] text-fpl_text/25 w-16">{note}</span>}
            </div>
          ))}
        </div>
      </div>

      {/* Transfer summary */}
      {transfer && (
        <div className="bg-card rounded-xl p-4 border border-white/5">
          <p className="text-xs font-semibold text-fpl_text/50 uppercase tracking-widest mb-3">Transfer Impact</p>
          <div className="flex items-center gap-2">
            <div className="flex-1 text-center">
              <p className="text-[10px] text-danger/60 uppercase mb-1">OUT</p>
              <p className="text-sm font-bold text-fpl_text">{transfer.out.name}</p>
              <p className="text-xs text-danger">{transfer.out.xPts.toFixed(1)} xPts</p>
            </div>
            <div className="flex flex-col items-center">
              <span className="text-primary text-xl">→</span>
              <span className="text-[10px] text-primary font-bold">+{transfer.netGain.toFixed(1)} net</span>
            </div>
            <div className="flex-1 text-center">
              <p className="text-[10px] text-primary/60 uppercase mb-1">IN</p>
              <p className="text-sm font-bold text-fpl_text">{transfer.in.name}</p>
              <p className="text-xs text-primary">{transfer.in.xPts.toFixed(1)} xPts</p>
            </div>
          </div>
          <div className="mt-3 flex justify-between text-xs text-fpl_text/40 border-t border-white/5 pt-3">
            <span>Free transfer (0 pt cost)</span>
            <span className="text-primary font-bold">HIGH priority</span>
          </div>
        </div>
      )}

      {/* Export actions */}
      <div className="bg-card rounded-xl p-4 border border-white/5">
        <p className="text-xs font-semibold text-fpl_text/50 uppercase tracking-widest mb-3">Export</p>
        <div className="grid grid-cols-2 gap-2 mb-2">
          <button
            onClick={handleExportCSV}
            className="py-3 rounded-xl border border-white/10 text-xs font-semibold text-fpl_text/60 hover:border-primary/30 hover:text-primary transition-all flex items-center justify-center gap-2"
          >
            <span>⬇</span> Export CSV
          </button>
          <button
            onClick={handleExportJSON}
            className="py-3 rounded-xl border border-white/10 text-xs font-semibold text-fpl_text/60 hover:border-secondary/30 hover:text-secondary transition-all flex items-center justify-center gap-2"
          >
            <span>⬇</span> Export JSON
          </button>
        </div>
        <button
          onClick={handleCopy}
          className="w-full py-3 rounded-xl border border-white/10 text-xs font-semibold text-fpl_text/60 hover:border-white/20 hover:text-fpl_text transition-all flex items-center justify-center gap-2"
        >
          <span>📋</span> Copy Summary
        </button>
      </div>
    </div>
  )
}
