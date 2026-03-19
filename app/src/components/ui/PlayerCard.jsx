import React from 'react'

const FDR_COLORS = {
  1: 'bg-primary text-background',
  2: 'bg-primary text-background',
  3: 'bg-amber text-background',
  4: 'bg-danger text-white',
  5: 'bg-danger text-white',
}

const XPTS_COLOR = (xPts) => {
  if (xPts >= 10) return 'text-primary'
  if (xPts >= 6)  return 'text-amber'
  return 'text-danger'
}

const POS_COLORS = {
  GKP: 'bg-amber/20 text-amber border border-amber/30',
  DEF: 'bg-blue-500/20 text-blue-300 border border-blue-500/30',
  MID: 'bg-primary/20 text-primary border border-primary/30',
  FWD: 'bg-danger/20 text-danger border border-danger/30',
}

export default function PlayerCard({
  player,
  isSelected = false,
  isCaptain = false,
  isViceCaptain = false,
  onClick,
  showRemove = false,
  compact = false,
}) {
  if (!player) return null

  const xPtsColor = XPTS_COLOR(player.adjustedXPts ?? player.xPts)
  const fdrClass  = FDR_COLORS[player.fixtureDifficulty] ?? FDR_COLORS[3]

  if (compact) {
    return (
      <div
        onClick={onClick}
        className={`relative flex items-center gap-2 rounded-xl px-3 py-2 cursor-pointer transition-all
          ${isSelected
            ? 'bg-primary/10 border border-primary/40'
            : 'bg-card border border-white/5 hover:border-primary/30'
          }`}
      >
        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${POS_COLORS[player.position]}`}>
          {player.position}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold text-fpl_text truncate">{player.name}</p>
          <p className="text-[10px] text-fpl_text/50">{player.team}</p>
        </div>
        <div className="text-right">
          <p className={`text-xs font-bold ${xPtsColor}`}>{(player.adjustedXPts ?? player.xPts).toFixed(1)}</p>
          <p className="text-[10px] text-fpl_text/40">£{player.price}m</p>
        </div>
        {player.injured && (
          <span className="absolute -top-1 -right-1 text-[10px]">⚠️</span>
        )}
      </div>
    )
  }

  return (
    <div
      onClick={onClick}
      className={`relative rounded-xl p-3 cursor-pointer transition-all duration-200 select-none
        ${isSelected
          ? 'bg-primary/10 border-2 border-primary shadow-lg shadow-primary/10'
          : 'bg-card border border-white/5 hover:border-primary/30 hover:bg-card/80'
        }`}
    >
      {/* Captain badges */}
      {isCaptain && (
        <div className="absolute -top-2 -right-2 w-6 h-6 rounded-full bg-primary flex items-center justify-center text-background text-[10px] font-black shadow-lg z-10">
          C
        </div>
      )}
      {isViceCaptain && (
        <div className="absolute -top-2 -right-2 w-6 h-6 rounded-full bg-secondary flex items-center justify-center text-background text-[10px] font-black shadow-lg z-10">
          V
        </div>
      )}

      {/* Injury badge */}
      {player.injured && (
        <div className="absolute -top-2 -left-2 text-base z-10">⚠️</div>
      )}

      {/* Position tag */}
      <div className="flex items-center justify-between mb-2">
        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${POS_COLORS[player.position]}`}>
          {player.position}
        </span>
        <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${fdrClass}`}>
          FDR {player.fixtureDifficulty}
        </span>
      </div>

      {/* Player avatar placeholder */}
      <div className="w-10 h-10 rounded-full bg-surface flex items-center justify-center mx-auto mb-2 text-lg">
        {player.position === 'GKP' ? '🧤' :
         player.position === 'DEF' ? '🛡️' :
         player.position === 'MID' ? '⚡' : '🎯'}
      </div>

      {/* Name + team */}
      <p className="text-xs font-bold text-fpl_text text-center truncate leading-tight">{player.name}</p>
      <p className="text-[10px] text-fpl_text/50 text-center mb-2">{player.team}</p>

      {/* Stats row */}
      <div className="flex justify-between items-center">
        <span className="text-[10px] text-fpl_text/40">£{player.price}m</span>
        <span className={`text-sm font-black ${xPtsColor}`}>
          {(player.adjustedXPts ?? player.xPts).toFixed(1)}
          <span className="text-[9px] text-fpl_text/40 font-normal ml-0.5">xPts</span>
        </span>
      </div>

      {/* Next fixture */}
      <p className="text-[9px] text-fpl_text/30 text-center mt-1 truncate">{player.nextFixture}</p>

      {/* Remove button */}
      {showRemove && (
        <button
          onClick={(e) => { e.stopPropagation(); onClick && onClick() }}
          className="absolute top-1 right-1 w-4 h-4 rounded-full bg-danger/80 flex items-center justify-center text-white text-[8px] hover:bg-danger transition-colors"
        >
          ✕
        </button>
      )}
    </div>
  )
}
