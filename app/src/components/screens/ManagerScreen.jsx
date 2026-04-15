import React, { useMemo, useState } from 'react'
import { selectOptimalXI } from '../../utils/formations'

// ── TransferCard ──────────────────────────────────────────────────────────────
function TransferCard({ t }) {
  const [showAlts, setShowAlts] = useState(false)
  const hasAlts = t.alternatives?.length > 0

  return (
    <div className={`rounded-xl border p-4
      ${t.isFreeTransfer ? 'bg-primary/5 border-primary/20' : t.netGain > 0 ? 'bg-amber/5 border-amber/20' : 'bg-card border-white/5 opacity-60'}`}>

      {/* Header row */}
      <div className="flex items-center justify-between mb-3">
        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${t.isFreeTransfer ? 'bg-primary/20 text-primary' : 'bg-amber/20 text-amber'}`}>
          {t.isFreeTransfer ? 'Free Transfer' : '-4 pt hit'}
        </span>
        <span className={`text-xs font-bold px-2 py-1 rounded-lg
          ${t.priority === 'HIGH'   ? 'bg-primary/15 text-primary border border-primary/20' :
            t.priority === 'MEDIUM' ? 'bg-amber/15 text-amber border border-amber/20' :
            'bg-white/5 text-fpl_text/40 border border-white/10'}`}>
          {t.priority} priority
        </span>
      </div>

      {/* Primary recommendation: OUT → IN */}
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
        <span className="text-primary text-lg flex-shrink-0">→</span>
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

      {/* Gain metrics */}
      <div className="grid grid-cols-3 gap-2 mb-3">
        <div className="bg-black/20 rounded-lg p-2 text-center">
          <p className="text-[9px] text-fpl_text/30">xPts gain</p>
          <p className="text-sm font-black text-primary">+{t.xPtsGain.toFixed(1)}</p>
        </div>
        <div className="bg-black/20 rounded-lg p-2 text-center">
          <p className="text-[9px] text-fpl_text/30">Hit cost</p>
          <p className={`text-sm font-black ${t.hitCost > 0 ? 'text-danger' : 'text-fpl_text/50'}`}>{t.hitCost > 0 ? `-${t.hitCost}` : '0'}</p>
        </div>
        <div className="bg-black/20 rounded-lg p-2 text-center">
          <p className="text-[9px] text-fpl_text/30">Net gain</p>
          <p className={`text-sm font-black ${t.netGain > 0 ? 'text-primary' : 'text-danger'}`}>{t.netGain > 0 ? '+' : ''}{t.netGain.toFixed(1)}</p>
        </div>
      </div>

      {t.reasoning && <p className="text-[10px] text-fpl_text/40 mb-3 italic leading-relaxed">{t.reasoning}</p>}

      {/* See Alternatives toggle */}
      {hasAlts && (
        <div>
          <button
            onClick={() => setShowAlts(v => !v)}
            className="w-full flex items-center justify-between px-3 py-2 rounded-lg border border-white/10 bg-white/5 hover:border-white/20 hover:bg-white/8 transition-all text-[11px] font-semibold text-fpl_text/50 hover:text-fpl_text/70"
          >
            <span>See {showAlts ? 'fewer' : `${t.alternatives.length} alternative${t.alternatives.length > 1 ? 's' : ''}`}</span>
            <span className={`transition-transform duration-200 ${showAlts ? 'rotate-180' : ''}`}>▾</span>
          </button>

          {showAlts && (
            <div className="mt-2 flex flex-col gap-1.5">
              {t.alternatives.map((alt, j) => (
                <div key={alt.in.id ?? j} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/4 border border-white/8">
                  <span className="text-[10px] font-black text-fpl_text/30 w-4 shrink-0">#{j + 2}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-semibold text-fpl_text truncate">{alt.in.name}</p>
                    <p className="text-[10px] text-fpl_text/40">{alt.in.position} · £{alt.in.price}m</p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-xs font-black text-primary">{alt.in.xPts.toFixed(1)} xP</p>
                    <p className={`text-[10px] font-semibold ${alt.netGain > 0 ? 'text-primary/60' : 'text-danger/60'}`}>
                      {alt.netGain > 0 ? '+' : ''}{alt.netGain.toFixed(1)} net
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const TABS = ['Optimal XI', 'Captain Picks', 'Transfers']

const POS_STYLE = {
  GK:  'bg-amber/20 text-amber',
  GKP: 'bg-amber/20 text-amber',
  DEF: 'bg-blue-500/20 text-blue-300',
  MID: 'bg-primary/20 text-primary',
  FWD: 'bg-danger/20 text-danger',
}

function PitchPlayerCard({ player, isCaptain, isViceCaptain }) {
  const xpColor = player.adjustedXPts >= 6 ? 'text-primary' : player.adjustedXPts >= 3 ? 'text-amber' : 'text-danger'
  return (
    <div className="flex flex-col items-center gap-0.5 max-w-[72px]">
      <div className={`relative w-10 h-10 rounded-full flex items-center justify-center border-2 text-[10px] font-black
        ${isCaptain ? 'border-primary bg-primary/20 text-primary' : isViceCaptain ? 'border-secondary bg-secondary/20 text-secondary' : 'border-white/20 bg-white/10 text-fpl_text'}`}>
        {player.name?.split(' ').pop()?.slice(0, 3) ?? '???'}
        {isCaptain    && <span className="absolute -top-1 -right-1 w-4 h-4 bg-primary rounded-full text-background text-[8px] font-black flex items-center justify-center">C</span>}
        {isViceCaptain && <span className="absolute -top-1 -right-1 w-4 h-4 bg-secondary rounded-full text-background text-[8px] font-black flex items-center justify-center">V</span>}
      </div>
      <p className="text-[9px] text-fpl_text font-semibold truncate w-full text-center">{player.name?.split(' ').pop() ?? '—'}</p>
      <p className={`text-[9px] font-black ${xpColor}`}>{player.adjustedXPts?.toFixed(1)}</p>
      {player.injured && <span className="text-[8px]">⚠️</span>}
    </div>
  )
}

export default function ManagerScreen({ agentData = null, userInput = null }) {
  const [tab, setTab] = useState(0)

  const gameweek         = agentData?.gameweek ?? userInput?.gameweek ?? '—'
  const captainShortlist = agentData?.captainShortlist ?? []
  const liveTransferRec  = agentData?.transferRecommendation ?? null
  const planningGameweek = agentData?.planningGameweek ?? liveTransferRec?.planningGameweek
  const transfers        = liveTransferRec?.transfers ?? []
  const hasLiveTransfers = Boolean(liveTransferRec)
  const squadPlayers     = agentData?.squadPlayers ?? null  // null for demo data
  const managerRec       = agentData?.managerRecommendation ?? null
  const hasManagerAgent  = Boolean(managerRec?.xi?.length === 11)

  // Client-side fallback XI (live import only) when Manager Agent API did not return
  const optimalXI = useMemo(() => {
    if (!squadPlayers?.length) return null
    return selectOptimalXI(squadPlayers)
  }, [squadPlayers])

  const displayXI = useMemo(() => {
    if (hasManagerAgent) {
      return {
        formation: managerRec.formation,
        xi:        managerRec.xi,
        bench:     managerRec.bench,
        captain:   managerRec.captainId != null
          ? { id: managerRec.captainId, name: managerRec.captain }
          : null,
        viceCaptain: managerRec.viceCaptainId != null
          ? { id: managerRec.viceCaptainId, name: managerRec.viceCaptain }
          : null,
      }
    }
    return optimalXI
  }, [hasManagerAgent, managerRec, optimalXI])

  const normalize = pos => (pos === 'GKP' ? 'GK' : pos)

  return (
    <div className="flex flex-col gap-4 pb-6">

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-fpl_text/40 uppercase tracking-widest">Agents 2 & 3 Output</p>
          <p className="text-lg font-black text-fpl_text">Manager Recommendations</p>
          {hasManagerAgent ? (
            <p className="text-[10px] text-primary/70 mt-0.5">
              ● Live · xPts GW{gameweek}
              {planningGameweek != null && planningGameweek !== gameweek
                ? ` · transfers GW${planningGameweek}`
                : ''}{' '}
              · Manager Agent v2
            </p>
          ) : hasLiveTransfers ? (
            <p className="text-[10px] text-primary/70 mt-0.5">
              ● Live · xPts GW{gameweek}
              {planningGameweek != null && planningGameweek !== gameweek
                ? ` · transfers GW${planningGameweek}`
                : ''}{' '}
              · Sporting Director
            </p>
          ) : agentData ? (
            <p className="text-[10px] text-amber/60 mt-0.5">⚠ Import your FPL team for live XI, captain and transfer recommendations</p>
          ) : null}
        </div>
        <div className="text-right">
          <p className="text-[10px] text-fpl_text/40">Model GW</p>
          <p className="text-2xl font-black text-primary">{gameweek}</p>
          {planningGameweek != null && planningGameweek !== gameweek && (
            <p className="text-[10px] text-fpl_text/45 mt-0.5">Plan · GW{planningGameweek}</p>
          )}
        </div>
      </div>

      {/* Squad-only injury / availability (live import) */}
      {userInput?.isLiveData && (
        <div className="bg-amber/10 border border-amber/25 rounded-xl p-4">
          <p className="text-amber font-bold text-xs mb-1">⚠️ Your squad — injury &amp; availability</p>
          <p className="text-[10px] text-fpl_text/40 mb-3">
            FPL status for your 15 players this gameweek. Full league list: official FPL app.
          </p>
          {(agentData?.injuryAlerts?.length ?? 0) > 0 ? (
            <div className="flex flex-col gap-1.5">
              {agentData.injuryAlerts.map(p => (
                <div key={p.id} className="flex items-start gap-2">
                  <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded shrink-0 mt-0.5
                    ${p.statusCode === 'i' ? 'bg-danger/30 text-danger' :
                      p.statusCode === 's' ? 'bg-danger/30 text-danger' :
                      'bg-amber/30 text-amber'}`}>
                    {p.statusLabel}
                  </span>
                  <div className="min-w-0">
                    <p className="text-xs text-amber/90 font-semibold flex flex-wrap gap-1">
                      {p.name}
                      <span className="text-amber/50 font-normal"> · {p.position} · {p.team}</span>
                      {p.startProb != null && (
                        <span className="text-amber/50 font-normal"> · {(p.startProb * 100).toFixed(0)}% chance</span>
                      )}
                    </p>
                    {p.news && <p className="text-[10px] text-amber/50 truncate">{p.news}</p>}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-[11px] text-fpl_text/45">No flagged players in your squad for this round.</p>
          )}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 bg-card rounded-xl p-1 border border-white/5">
        {TABS.map((t, i) => (
          <button key={t} onClick={() => setTab(i)}
            className={`flex-1 py-2 rounded-lg text-xs font-semibold transition-all
              ${tab === i ? 'bg-primary text-background' : 'text-fpl_text/40 hover:text-fpl_text'}`}>
            {t}
          </button>
        ))}
      </div>

      {/* Tab 0: Optimal XI */}
      {tab === 0 && (
        <div className="flex flex-col gap-4">
          {!displayXI ? (
            <div className="bg-card rounded-xl p-6 border border-white/5 text-center">
              <p className="text-fpl_text/40 text-sm">No squad data available</p>
              <p className="text-fpl_text/25 text-xs mt-1">Import your FPL team on the setup screen to see your optimal XI</p>
            </div>
          ) : (
            <>
              {hasManagerAgent && managerRec?.projectedPoints != null && (
                <div className="bg-primary/5 border border-primary/20 rounded-xl px-3 py-2 flex justify-between items-center">
                  <span className="text-[10px] text-fpl_text/50">Starting XI xP</span>
                  <span className="text-sm font-black text-primary">{managerRec.projectedPoints}</span>
                </div>
              )}

              {hasManagerAgent && managerRec?.chipRecommendation && (
                <div className="bg-secondary/10 border border-secondary/25 rounded-xl p-3">
                  <p className="text-[10px] text-secondary font-bold uppercase tracking-wider mb-1">Chip suggestion</p>
                  <p className="text-xs text-fpl_text font-semibold capitalize">
                    {String(managerRec.chipRecommendation.chip || '').replace(/_/g, ' ')}
                    {managerRec.chipRecommendation.confidence != null && (
                      <span className="text-fpl_text/50 font-normal">
                        {' '}· {Math.round((managerRec.chipRecommendation.confidence || 0) * 100)}% confidence
                      </span>
                    )}
                  </p>
                  {managerRec.chipRecommendation.reasoning && (
                    <p className="text-[10px] text-fpl_text/45 mt-1 leading-relaxed">{managerRec.chipRecommendation.reasoning}</p>
                  )}
                </div>
              )}

              <div className="flex items-center justify-between">
                <span className="text-xs text-fpl_text/40">Formation</span>
                <span className="text-xs font-black text-primary bg-primary/10 px-2 py-1 rounded-lg border border-primary/20">{displayXI.formation}</span>
              </div>

              {/* Pitch */}
              <div className="bg-gradient-to-b from-green-900/30 to-green-950/20 rounded-2xl border border-green-800/20 p-4 flex flex-col gap-5">
                {/* GKP row */}
                <div>
                  <p className="text-[9px] text-green-700/40 text-center font-mono mb-2">── GK ──</p>
                  <div className="flex justify-center gap-3">
                    {displayXI.xi.filter(p => normalize(p.position) === 'GK').map(p => (
                      <PitchPlayerCard key={p.id} player={p}
                        isCaptain={displayXI.captain?.id === p.id}
                        isViceCaptain={displayXI.viceCaptain?.id === p.id} />
                    ))}
                  </div>
                </div>
                {/* DEF row */}
                <div>
                  <p className="text-[9px] text-green-700/40 text-center font-mono mb-2">── DEF ──</p>
                  <div className="flex justify-center gap-2">
                    {displayXI.xi.filter(p => p.position === 'DEF').map(p => (
                      <PitchPlayerCard key={p.id} player={p}
                        isCaptain={displayXI.captain?.id === p.id}
                        isViceCaptain={displayXI.viceCaptain?.id === p.id} />
                    ))}
                  </div>
                </div>
                {/* MID row */}
                <div>
                  <p className="text-[9px] text-green-700/40 text-center font-mono mb-2">── MID ──</p>
                  <div className="flex justify-center gap-2">
                    {displayXI.xi.filter(p => p.position === 'MID').map(p => (
                      <PitchPlayerCard key={p.id} player={p}
                        isCaptain={displayXI.captain?.id === p.id}
                        isViceCaptain={displayXI.viceCaptain?.id === p.id} />
                    ))}
                  </div>
                </div>
                {/* FWD row */}
                <div>
                  <p className="text-[9px] text-green-700/40 text-center font-mono mb-2">── FWD ──</p>
                  <div className="flex justify-center gap-2">
                    {displayXI.xi.filter(p => p.position === 'FWD').map(p => (
                      <PitchPlayerCard key={p.id} player={p}
                        isCaptain={displayXI.captain?.id === p.id}
                        isViceCaptain={displayXI.viceCaptain?.id === p.id} />
                    ))}
                  </div>
                </div>
              </div>

              {/* Caption legend */}
              <div className="flex gap-4 justify-center">
                <div className="flex items-center gap-1.5">
                  <div className="w-4 h-4 rounded-full bg-primary flex items-center justify-center text-background text-[8px] font-black">C</div>
                  <span className="text-[11px] text-fpl_text/50">Captain: {displayXI.captain?.name ?? '—'}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className="w-4 h-4 rounded-full bg-secondary flex items-center justify-center text-background text-[8px] font-black">V</div>
                  <span className="text-[11px] text-fpl_text/50">VC: {displayXI.viceCaptain?.name ?? '—'}</span>
                </div>
              </div>

              {/* Bench */}
              <div className="bg-card rounded-xl p-3 border border-white/5">
                <p className="text-[10px] text-fpl_text/40 uppercase tracking-widest mb-2">Bench</p>
                <div className="flex flex-col gap-1.5">
                  {displayXI.bench.map((p, i) => (
                    <div key={p.id} className="flex items-center gap-3">
                      <span className="text-[10px] text-fpl_text/30 w-4">{p.benchOrder ?? i + 1}</span>
                      <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${POS_STYLE[p.position] ?? ''}`}>{p.position}</span>
                      <span className="text-xs text-fpl_text flex-1">{p.name}</span>
                      <span className="text-xs font-bold text-fpl_text/50">{p.adjustedXPts?.toFixed(1)} xP</span>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* Tab 1: Captain shortlist */}
      {tab === 1 && (
        <div className="flex flex-col gap-3">
          {captainShortlist.length === 0 ? (
            <div className="bg-card rounded-xl p-6 border border-white/5 text-center">
              <p className="text-fpl_text/40 text-sm">No captain data available</p>
              <p className="text-fpl_text/25 text-xs mt-1">Run the optimizer to get live captain recommendations</p>
            </div>
          ) : (
            captainShortlist.map((p, i) => (
              <div key={p.name} className={`rounded-xl border p-4 flex items-center justify-between
                ${i === 0 ? 'bg-primary/10 border-primary/30' : 'bg-card border-white/5'}`}>
                <div className="flex items-center gap-3">
                  {i === 0 && <div className="w-7 h-7 rounded-full bg-primary flex items-center justify-center text-background text-[10px] font-black">C</div>}
                  {i === 1 && <div className="w-7 h-7 rounded-full bg-secondary flex items-center justify-center text-background text-[10px] font-black">V</div>}
                  {i > 1  && <div className="w-7 h-7 rounded-full bg-white/10 flex items-center justify-center text-fpl_text/50 text-[10px] font-black">{i + 1}</div>}
                  <div>
                    <p className="text-sm font-bold text-fpl_text">{p.name}</p>
                    <p className="text-[10px] text-fpl_text/40">{p.team} · {p.position}</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className={`text-lg font-black ${i === 0 ? 'text-primary' : 'text-fpl_text/70'}`}>{p.expectedPts.toFixed(1)}</p>
                  <p className="text-[10px] text-fpl_text/40">xPts</p>
                  <p className="text-[10px] text-fpl_text/30">{(p.startProb * 100).toFixed(0)}% start</p>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Tab 2: Transfers */}
      {tab === 2 && (
        <div className="flex flex-col gap-3">
          {liveTransferRec?.holdFlag && (
            <div className="bg-amber/10 border border-amber/30 rounded-xl p-4">
              <p className="text-amber font-bold text-xs">⏸ Hold Recommendation</p>
              <p className="text-[11px] text-amber/70 mt-1">{liveTransferRec.summary}</p>
            </div>
          )}
          {liveTransferRec?.wildcardFlag && (
            <div className="bg-primary/10 border border-primary/30 rounded-xl p-4">
              <p className="text-primary font-bold text-xs">🃏 Wildcard Flagged</p>
              <p className="text-[11px] text-primary/70 mt-1">{liveTransferRec.summary}</p>
            </div>
          )}

          {transfers.length === 0 ? (
            <div className="bg-card rounded-xl p-6 border border-white/5 text-center">
              <p className="text-fpl_text/40 text-sm">No transfer data available</p>
              <p className="text-fpl_text/25 text-xs mt-1">Import your FPL team to get personalised transfer recommendations from the Sporting Director agent</p>
            </div>
          ) : (
            transfers.map((t, i) => <TransferCard key={t.out.id ?? i} t={t} />)
          )}
        </div>
      )}
    </div>
  )
}
