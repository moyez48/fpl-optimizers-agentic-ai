import React from 'react'
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell, Legend,
} from 'recharts'

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-surface border border-white/10 rounded-lg px-3 py-2 text-xs shadow-xl">
      <p className="text-fpl_text/60 mb-1 font-semibold">{label}</p>
      {payload.map((entry) => (
        <p key={entry.name} style={{ color: entry.color }} className="font-bold">
          {entry.name}: {entry.value ?? '—'}
        </p>
      ))}
    </div>
  )
}

export default function PointsChart({ data }) {
  return (
    <ResponsiveContainer width="100%" height={200}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
        <XAxis
          dataKey="gw"
          tick={{ fill: 'rgba(234,234,234,0.4)', fontSize: 11 }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          tick={{ fill: 'rgba(234,234,234,0.4)', fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          domain={[0, 'auto']}
        />
        <Tooltip content={<CustomTooltip />} />
        <Legend
          wrapperStyle={{ fontSize: '11px', color: 'rgba(234,234,234,0.5)', paddingTop: '8px' }}
        />
        <Bar dataKey="actual" name="Actual pts" radius={[4,4,0,0]} maxBarSize={32}>
          {data.map((entry, i) => (
            <Cell
              key={i}
              fill={entry.actual != null ? 'rgba(15,52,96,0.9)' : 'transparent'}
              stroke={entry.actual != null ? 'rgba(4,245,255,0.3)' : 'none'}
            />
          ))}
        </Bar>
        <Bar dataKey="projected" name="Projected pts" radius={[4,4,0,0]} maxBarSize={32}>
          {data.map((entry, i) => (
            <Cell
              key={i}
              fill={entry.projected != null ? 'rgba(0,255,135,0.25)' : 'transparent'}
              stroke={entry.projected != null ? '#00FF87' : 'none'}
              strokeWidth={1}
            />
          ))}
        </Bar>
      </ComposedChart>
    </ResponsiveContainer>
  )
}
