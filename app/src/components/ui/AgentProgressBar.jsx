import React from 'react'

const STATUS_STYLES = {
  pending:    { dot: 'bg-white/20',   bar: 'bg-white/10',  label: 'text-fpl_text/30' },
  active:     { dot: 'bg-secondary',  bar: 'bg-secondary',  label: 'text-secondary'   },
  complete:   { dot: 'bg-primary',    bar: 'bg-primary',    label: 'text-primary'      },
}

export default function AgentProgressBar({ name, description, status, progress = 0, thought }) {
  const styles = STATUS_STYLES[status] ?? STATUS_STYLES.pending
  const isActive = status === 'active'
  const isDone   = status === 'complete'

  return (
    <div className={`rounded-xl p-4 border transition-all duration-500
      ${isDone   ? 'bg-primary/5 border-primary/20'   :
        isActive ? 'bg-secondary/5 border-secondary/20' :
                   'bg-card/50 border-white/5'}`}
    >
      <div className="flex items-center gap-3 mb-3">
        {/* Status dot */}
        <div className="relative flex-shrink-0">
          <div className={`w-3 h-3 rounded-full ${styles.dot}`} />
          {isActive && (
            <div className="absolute inset-0 rounded-full bg-secondary/40 pulse-dot" />
          )}
        </div>

        <div className="flex-1">
          <div className="flex items-center justify-between">
            <p className={`text-sm font-bold ${styles.label}`}>{name}</p>
            {isDone && <span className="text-primary text-xs font-bold">✓ Done</span>}
            {isActive && (
              <span className="text-secondary text-xs animate-pulse">{Math.round(progress)}%</span>
            )}
          </div>
          <p className="text-[11px] text-fpl_text/40">{description}</p>
        </div>
      </div>

      {/* Progress bar */}
      <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ${styles.bar}`}
          style={{ width: `${isDone ? 100 : progress}%` }}
        />
      </div>

      {/* Thinking text */}
      {isActive && thought && (
        <p className="text-[10px] text-secondary/60 mt-2 italic truncate">
          💭 {thought}
        </p>
      )}
    </div>
  )
}
