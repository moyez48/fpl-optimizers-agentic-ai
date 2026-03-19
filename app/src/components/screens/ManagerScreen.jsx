import React, { useState } from 'react'
import { DEMO_MANAGER_OUTPUT, DEMO_TRANSFER_OUTPUT } from '../../data/demoOutput'
import PlayerCard from '../ui/PlayerCard'

const TABS = ['Optimal XI', 'Chip Advice', 'Transfers']

const CONF_COLOR = { HIGH: 'text-primary', MEDIUM: 'text-amber', LOW: 'text-danger' }

function PitchRow({ players, captain, viceCaptain }) {
  return (
    <div className="flex gap-2 justify-center">
      {players.map(p => (
        <div key={p.id} className="flex-1 max-w-[90px]">
          <PlayerCard
            player={p}
            isCaptain={p.id === captain?.id}
            isViceCaptain={p.id === viceCaptain?.id}
          />
        </div>
      ))}
    </div>
  )
}

export default function ManagerScreen() {
  const [tab, setTab] = useState(0)
  const { selectedXI, bench, captain, viceCaptain, chipRecommendation, formation, totalProjectedPts } = DEMO_MANAGER_OUTPUT
  const { recommended: transfers } = DEMO_TRANSFER_OUTPUT

  const gkp  = selectedXI.filter(p => p.position === 'GKP')
  const defs = selectedXI.filter(p => p.position === 'DEF')
  const mids = selectedXI.filter(p => p.position === 'MID')
  const fwds = selectedXI.filter(p => p.position === 'FWD')

  return (
    <div className="flex flex-col gap-4 pb-6">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-fpl_text/40 uppercase tracking-widest">Agents 2 & 3 Output</p>
          <p className="text-lg font-black text-fpl_text">Manager Recommendations</p>
        </div>
        <div className="text-right">
          <p className="text-[10px] text-fpl_text/40">Projected</p>
          <p className="text-2xl font-black text-primary">{totalProjectedPts}</p>
          <p className="text-[10px] text-fpl_text/40">pts (w/ chip)</p>
        </div>
      </div>

      {/* Tabs */}
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

      {/* Tab 0: Pitch view */}
      {tab === 0 && (
        <div className="flex flex-col gap-4">
          {/* Formation badge */}
          <div className="flex items-center justify-between">
            <span className="text-xs text-fpl_text/40">Formation</span>
            <span className="text-xs font-black text-primary bg-primary/10 px-2 py-1 rounded-lg border border-primary/20">
              {formation}
            </span>
          </div>

          {/* Pitch */}
          <div className="bg-gradient-to-b from-green-900/30 to-green-950/20 rounded-2xl border border-green-800/20 p-4 flex flex-col gap-4">
            {/* Pitch lines decoration */}
            <div className="text-[10px] text-green-700/40 text-center mb-1 font-mono">── GKP ──</div>
            <PitchRow players={gkp} captain={captain} viceCaptain={viceCaptain} />

            <div className="text-[10px] text-green-700/40 text-center font-mono">── DEF ──</div>
            <PitchRow players={defs} captain={captain} viceCaptain={viceCaptain} />

            <div className="text-[10px] text-green-700/40 text-center font-mono">── MID ──</div>
            <PitchRow players={mids} captain={captain} viceCaptain={viceCaptain} />

            <div className="text-[10px] text-green-700/40 text-center font-mono">── FWD ──</div>
            <PitchRow players={fwds} captain={captain} viceCaptain={viceCaptain} />
          </div>

          {/* Captain legend */}
          <div className="flex gap-3 justify-center">
            <div className="flex items-center gap-1.5">
              <div className="w-4 h-4 rounded-full bg-primary flex items-center justify-center text-background text-[8px] font-black">C</div>
              <span className="text-[11px] text-fpl_text/50">Captain: {captain.name}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-4 h-4 rounded-full bg-secondary flex items-center justify-center text-background text-[8px] font-black">V</div>
              <span className="text-[11px] text-fpl_text/50">VC: {viceCaptain.name}</span>
            </div>
          </div>

          {/* Bench */}
          <div className="bg-card rounded-xl p-3 border border-white/5">
            <p className="text-[10px] text-fpl_text/40 uppercase tracking-widest mb-2">Bench Order</p>
            <div className="flex flex-col gap-1.5">
              {bench.map((p, i) => (
                <div key={p.id} className="flex items-center gap-3">
                  <span className="text-[10px] text-fpl_text/30 w-4">{i + 1}</span>
                  <div className="flex-1">
                    <PlayerCard player={p} compact />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Tab 1: Chip advice */}
      {tab === 1 && (
        <div className="flex flex-col gap-3">
          {chipRecommendation.chip !== 'None' ? (
            <div className="bg-primary/10 border border-primary/30 rounded-2xl p-5">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <p className="text-[10px] text-primary/60 uppercase tracking-widest mb-1">Recommended Chip</p>
                  <p className="text-xl font-black text-primary">{chipRecommendation.chip}</p>
                </div>
                <span className={`text-xs font-bold px-2 py-1 rounded-lg border
                  ${chipRecommendation.confidence === 'HIGH'
                    ? 'bg-primary/15 border-primary/30 text-primary'
                    : 'bg-amber/15 border-amber/30 text-amber'}`}>
                  {chipRecommendation.confidence} confidence
                </span>
              </div>

              <div className="flex items-center gap-2 mb-4">
                <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center text-primary text-lg">⚡</div>
                <div>
                  <p className="text-sm font-bold text-fpl_text">Captain: {chipRecommendation.target}</p>
                  <p className="text-[11px] text-fpl_text/50">{chipRecommendation.reason}</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="bg-black/20 rounded-xl p-3">
                  <p className="text-[10px] text-fpl_text/40 mb-1">Normal captain pts</p>
                  <p className="text-lg font-black text-fpl_text">
                    {(DEMO_MANAGER_OUTPUT.captain.adjustedXPts * 2).toFixed(1)}
                  </p>
                </div>
                <div className="bg-primary/15 rounded-xl p-3">
                  <p className="text-[10px] text-primary/60 mb-1">With Triple Captain</p>
                  <p className="text-lg font-black text-primary">
                    {(DEMO_MANAGER_OUTPUT.captain.adjustedXPts * 3).toFixed(1)}
                  </p>
                </div>
              </div>

              <div className="mt-3 flex items-center justify-between bg-black/20 rounded-xl p-3">
                <span className="text-xs text-fpl_text/50">Extra pts from chip</span>
                <span className="text-base font-black text-primary">+{chipRecommendation.projectedGain.toFixed(1)} pts</span>
              </div>
            </div>
          ) : (
            <div className="bg-card rounded-xl p-5 border border-white/5 text-center">
              <p className="text-fpl_text/40 text-sm">No chip recommended this gameweek</p>
              <p className="text-fpl_text/25 text-xs mt-1">Save chips for a better opportunity</p>
            </div>
          )}

          {/* Other chips status */}
          <div className="bg-card rounded-xl p-4 border border-white/5">
            <p className="text-[10px] text-fpl_text/40 uppercase tracking-widest mb-3">Other Available Chips</p>
            {[
              { name: 'Bench Boost', reason: 'Bench projects 23.1 pts — viable but not optimal this GW', use: false },
              { name: 'Wildcard',    reason: 'No significant improvement identified — hold', use: false },
            ].map(chip => (
              <div key={chip.name} className="flex items-start gap-3 py-2.5 border-b border-white/5 last:border-0">
                <span className="text-sm mt-0.5">{chip.use ? '✅' : '⏸️'}</span>
                <div>
                  <p className="text-xs font-semibold text-fpl_text">{chip.name}</p>
                  <p className="text-[10px] text-fpl_text/40">{chip.reason}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 2: Transfers */}
      {tab === 2 && (
        <div className="flex flex-col gap-3">
          {transfers.map((t, i) => (
            <div
              key={i}
              className={`rounded-xl border p-4
                ${t.isFreeTransfer
                  ? 'bg-primary/5 border-primary/20'
                  : t.netGain > 0
                    ? 'bg-amber/5 border-amber/20'
                    : 'bg-card border-white/5 opacity-60'}`}
            >
              <div className="flex items-center justify-between mb-3">
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full
                  ${t.isFreeTransfer ? 'bg-primary/20 text-primary' : 'bg-amber/20 text-amber'}`}>
                  {t.isFreeTransfer ? 'Free Transfer' : `-4 pt hit`}
                </span>
                <span className={`text-xs font-bold px-2 py-1 rounded-lg
                  ${t.priority === 'HIGH' ? 'bg-primary/15 text-primary border border-primary/20' :
                    t.priority === 'MEDIUM' ? 'bg-amber/15 text-amber border border-amber/20' :
                    'bg-white/5 text-fpl_text/40 border border-white/10'}`}>
                  {t.priority} priority
                </span>
              </div>

              {/* Transfer arrow */}
              <div className="flex items-center gap-2 mb-3">
                <div className="flex-1 bg-danger/10 border border-danger/20 rounded-lg p-2.5">
                  <p className="text-[9px] text-danger/60 uppercase mb-0.5">OUT</p>
                  <p className="text-xs font-bold text-fpl_text">{t.out.name}</p>
                  <div className="flex justify-between mt-0.5">
                    <span className="text-[10px] text-fpl_text/40">{t.out.position}</span>
                    <span className="text-[10px] text-fpl_text/40">£{t.out.price}m</span>
                  </div>
                  <p className="text-[10px] text-danger mt-1">{t.out.xPts.toFixed(1)} xPts</p>
                </div>

                <div className="flex-shrink-0 flex flex-col items-center">
                  <span className="text-primary text-lg">→</span>
                </div>

                <div className="flex-1 bg-primary/10 border border-primary/20 rounded-lg p-2.5">
                  <p className="text-[9px] text-primary/60 uppercase mb-0.5">IN</p>
                  <p className="text-xs font-bold text-fpl_text">{t.in.name}</p>
                  <div className="flex justify-between mt-0.5">
                    <span className="text-[10px] text-fpl_text/40">{t.in.position}</span>
                    <span className="text-[10px] text-fpl_text/40">£{t.in.price}m</span>
                  </div>
                  <p className="text-[10px] text-primary mt-1">{t.in.xPts.toFixed(1)} xPts</p>
                </div>
              </div>

              {/* Stats */}
              <div className="grid grid-cols-3 gap-2">
                <div className="bg-black/20 rounded-lg p-2 text-center">
                  <p className="text-[9px] text-fpl_text/30">xPts gain</p>
                  <p className="text-sm font-black text-primary">+{t.xPtsGain.toFixed(1)}</p>
                </div>
                <div className="bg-black/20 rounded-lg p-2 text-center">
                  <p className="text-[9px] text-fpl_text/30">Hit cost</p>
                  <p className={`text-sm font-black ${t.hitCost > 0 ? 'text-danger' : 'text-fpl_text/50'}`}>
                    {t.hitCost > 0 ? `-${t.hitCost}` : '0'}
                  </p>
                </div>
                <div className="bg-black/20 rounded-lg p-2 text-center">
                  <p className="text-[9px] text-fpl_text/30">Net gain</p>
                  <p className={`text-sm font-black ${t.netGain > 0 ? 'text-primary' : 'text-danger'}`}>
                    {t.netGain > 0 ? '+' : ''}{t.netGain.toFixed(1)}
                  </p>
                </div>
              </div>

              {!t.isFreeTransfer && t.netGain <= 0 && (
                <p className="text-[10px] text-danger/60 mt-2 text-center">
                  Net gain negative — not recommended this GW
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
