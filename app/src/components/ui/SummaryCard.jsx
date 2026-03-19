import React from 'react'

export default function SummaryCard({ label, value, sub, accent = false, icon }) {
  return (
    <div className={`rounded-xl p-4 border flex flex-col gap-1
      ${accent
        ? 'bg-primary/10 border-primary/30'
        : 'bg-card border-white/5'
      }`}
    >
      <div className="flex items-center gap-2">
        {icon && <span className="text-base">{icon}</span>}
        <p className="text-[11px] text-fpl_text/50 uppercase tracking-widest font-semibold">{label}</p>
      </div>
      <p className={`text-2xl font-black leading-tight ${accent ? 'text-primary' : 'text-fpl_text'}`}>
        {value}
      </p>
      {sub && <p className="text-[11px] text-fpl_text/40">{sub}</p>}
    </div>
  )
}
