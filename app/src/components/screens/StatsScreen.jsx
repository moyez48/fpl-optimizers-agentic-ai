import React, { useState } from 'react'
import { DEMO_STATS_OUTPUT } from '../../data/demoOutput'

const FDR_BADGE = (fdr) => {
  if (fdr <= 2) return <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-primary text-background">FDR {fdr}</span>
  if (fdr === 3) return <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber text-background">FDR {fdr}</span>
  return <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-danger text-white">FDR {fdr}</span>
}

const XPTS_COLOR = (v) => v >= 10 ? 'text-primary' : v >= 6 ? 'text-amber' : 'text-danger'

const TABS = ['Top 11 xPts', 'Full Stats', 'Risk Matrix']

export default function StatsScreen() {
  const [tab, setTab] = useState(0)
  const { rankedPlayers, injuryAlerts, squadTotalXPts } = DEMO_STATS_OUTPUT

  return (
    <div className="flex flex-col gap-4 pb-6">
      <div>
        <p className="text-xs text-fpl_text/40 uppercase tracking-widest">Agent 1 Output</p>
        <p className="text-lg font-black text-fpl_text">Statistician Report</p>
      </div>

      {/* Summary pills */}
      <div className="grid grid-cols-2 gap-2">
        <div className="bg-card rounded-xl p-3 border border-white/5">
          <p className="text-[10px] text-fpl_text/40 uppercase tracking-widest">Squad xPts</p>
          <p className="text-2xl font-black text-fpl_text">{squadTotalXPts}</p>
          <p className="text-[10px] text-fpl_text/40">current starting 11</p>
        </div>
        <div className="bg-danger/10 border border-danger/20 rounded-xl p-3">
          <p className="text-[10px] text-danger/70 uppercase tracking-widest">Injury Alerts</p>
          <p className="text-2xl font-black text-danger">{injuryAlerts.length}</p>
          <p className="text-[10px] text-danger/60">{injuryAlerts.map(p => p.name).join(', ')}</p>
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 bg-card rounded-xl p-1 border border-white/5">
        {TABS.map((t, i) => (
          <button
            key={t}
            onClick={() => setTab(i)}
            className={`flex-1 py-2 rounded-lg text-xs font-semibold transition-all
              ${tab === i ? 'bg-primary text-background' : 'text-fpl_text/40 hover:text-fpl_text'}`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Tab 0: Top 11 xPts */}
      {tab === 0 && (
        <div className="bg-card rounded-xl border border-white/5 overflow-hidden">
          {/* Table header */}
          <div className="grid grid-cols-[1.5rem_1fr_2.5rem_3rem_3rem] gap-2 px-4 py-2 border-b border-white/5">
            <span className="text-[10px] text-fpl_text/30">#</span>
            <span className="text-[10px] text-fpl_text/30">Player</span>
            <span className="text-[10px] text-fpl_text/30 text-center">Pos</span>
            <span className="text-[10px] text-fpl_text/30 text-right">xPts</span>
            <span className="text-[10px] text-fpl_text/30 text-right">FDR</span>
          </div>
          {rankedPlayers.map((player, i) => (
            <div
              key={player.id}
              className={`grid grid-cols-[1.5rem_1fr_2.5rem_3rem_3rem] gap-2 px-4 py-3 border-b border-white/5 last:border-0
                ${player.injured ? 'bg-amber/5' : i % 2 === 0 ? 'bg-transparent' : 'bg-white/[0.02]'}`}
            >
              <span className="text-[11px] text-fpl_text/30 self-center">{i + 1}</span>
              <div className="min-w-0 self-center">
                <div className="flex items-center gap-1.5">
                  <p className="text-xs font-semibold text-fpl_text truncate">{player.name}</p>
                  {player.injured && <span className="text-[10px]">⚠️</span>}
                </div>
                <p className="text-[10px] text-fpl_text/40">{player.team} · {player.nextFixture}</p>
              </div>
              <span className="text-[10px] font-bold text-fpl_text/60 self-center text-center">{player.position}</span>
              <span className={`text-sm font-black self-center text-right ${XPTS_COLOR(player.adjustedXPts)}`}>
                {player.adjustedXPts.toFixed(1)}
              </span>
              <div className="self-center flex justify-end">{FDR_BADGE(player.fixtureDifficulty)}</div>
            </div>
          ))}
        </div>
      )}

      {/* Tab 1: Full Stats */}
      {tab === 1 && (
        <div className="bg-card rounded-xl border border-white/5 overflow-hidden overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-white/5">
                {['Player', 'xPts', 'xG', 'xA', 'Form', 'Own%'].map(h => (
                  <th key={h} className="text-left px-3 py-2 text-fpl_text/30 font-semibold text-[10px] whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rankedPlayers.map((p, i) => (
                <tr key={p.id} className={`border-b border-white/5 last:border-0 ${i % 2 === 0 ? '' : 'bg-white/[0.02]'}`}>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-1.5">
                      <span className={`text-[9px] font-bold px-1 py-0.5 rounded
                        ${p.position === 'GKP' ? 'bg-amber/20 text-amber' :
                          p.position === 'DEF' ? 'bg-blue-500/20 text-blue-300' :
                          p.position === 'MID' ? 'bg-primary/20 text-primary' :
                          'bg-danger/20 text-danger'}`}>
                        {p.position}
                      </span>
                      <span className="text-fpl_text font-medium truncate max-w-[80px]">{p.name}</span>
                      {p.injured && <span className="text-[9px]">⚠️</span>}
                    </div>
                  </td>
                  <td className={`px-3 py-2.5 font-black ${XPTS_COLOR(p.adjustedXPts)}`}>{p.adjustedXPts.toFixed(1)}</td>
                  <td className="px-3 py-2.5 text-fpl_text/70">{p.xG.toFixed(2)}</td>
                  <td className="px-3 py-2.5 text-fpl_text/70">{p.xA.toFixed(2)}</td>
                  <td className="px-3 py-2.5 text-fpl_text/70">{p.form}</td>
                  <td className="px-3 py-2.5 text-fpl_text/50">{p.ownership}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Tab 2: Risk Matrix */}
      {tab === 2 && (
        <div className="flex flex-col gap-2">
          {rankedPlayers.map(p => (
            <div key={p.id} className={`bg-card rounded-xl p-3 border ${p.injured ? 'border-amber/20' : 'border-white/5'}`}>
              <div className="flex items-center justify-between mb-2">
                <div>
                  <span className="text-xs font-semibold text-fpl_text">{p.name}</span>
                  {p.injured && <span className="ml-1 text-[10px]">⚠️</span>}
                  <p className="text-[10px] text-fpl_text/40">{p.team}</p>
                </div>
                <div className="text-right">
                  <p className={`text-sm font-black ${XPTS_COLOR(p.adjustedXPts)}`}>{p.adjustedXPts.toFixed(1)} xPts</p>
                  <p className="text-[10px] text-fpl_text/40">±{p.variance.toFixed(1)} variance</p>
                </div>
              </div>
              {/* Variance bar */}
              <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${(p.variance / 5) * 100}%`,
                    backgroundColor: p.variance > 3.5 ? '#E63946' : p.variance > 2.5 ? '#FFB703' : '#00FF87',
                  }}
                />
              </div>
              <div className="flex justify-between text-[9px] text-fpl_text/25 mt-0.5">
                <span>Low risk</span>
                <span>High risk</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Injury alert banner */}
      {injuryAlerts.length > 0 && (
        <div className="bg-amber/10 border border-amber/20 rounded-xl p-4">
          <p className="text-amber font-bold text-xs mb-1">⚠️ Injury Alerts</p>
          {injuryAlerts.map(p => (
            <p key={p.id} className="text-xs text-amber/80">
              {p.name} ({p.position}, {p.team ?? ''}) — Doubtful · xPts reduced to {p.adjustedXPts.toFixed(1)}
            </p>
          ))}
          <p className="text-[10px] text-amber/50 mt-1">Transfer recommendation: move out injured players before GW starts</p>
        </div>
      )}
    </div>
  )
}
