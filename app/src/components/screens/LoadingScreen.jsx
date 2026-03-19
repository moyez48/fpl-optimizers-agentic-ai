import React, { useState, useEffect } from 'react'
import AgentProgressBar from '../ui/AgentProgressBar'

const AGENTS = [
  {
    key: 'statistician',
    name: 'Statistician Agent',
    description: 'Calculates xPts, xG, xA · flags injuries · ranks squad',
    thoughts: [
      'Fetching fixture difficulty ratings...',
      'Computing adjustedXPts with form weighting...',
      'Flagging Rice (Arsenal) as doubtful — applying 10% penalty...',
      'Ranking 15 players by adjusted projected points...',
      'Generating injury alerts and risk metrics...',
    ],
    duration: 2200,
  },
  {
    key: 'manager',
    name: 'Manager Agent',
    description: 'Selects optimal XI · assigns captain · evaluates chips',
    thoughts: [
      'Enforcing formation rules: 1 GKP, min 3 DEF, min 2 MID, min 1 FWD...',
      'Checking 3-per-club constraint across all 15 players...',
      'Captain: Haaland (xPts 14.2, FDR 2) — strongest option...',
      'Triple Captain trigger: xPts > 12 AND FDR ≤ 2 → ACTIVATED...',
      'Ordering bench by coverage value...',
    ],
    duration: 2000,
  },
  {
    key: 'transfer',
    name: 'Transfer Agent',
    description: 'Ranks transfers by ROI · calculates hit penalties',
    thoughts: [
      'Identifying weakest squad players by adjustedXPts...',
      'Rice (4.6 xPts, injured) flagged as priority transfer out...',
      'Searching affordable MID replacements within £8.9m budget...',
      'Mbeumo: +5.5 net xPts gain, free transfer — HIGH priority...',
      'Evaluating Mykolenko hit: net -0.1 pts → NOT recommended...',
    ],
    duration: 1800,
  },
]

export default function LoadingScreen({ onComplete }) {
  const [agentIndex, setAgentIndex] = useState(0)
  const [progress, setProgress] = useState(0)
  const [thoughtIndex, setThoughtIndex] = useState(0)
  const [completedAgents, setCompletedAgents] = useState(new Set())

  useEffect(() => {
    if (agentIndex >= AGENTS.length) {
      setTimeout(onComplete, 400)
      return
    }

    const agent = AGENTS[agentIndex]
    const tickInterval = agent.duration / 100
    let ticks = 0

    const progressTimer = setInterval(() => {
      ticks++
      setProgress(ticks)
      if (ticks >= 100) {
        clearInterval(progressTimer)
        setCompletedAgents(prev => new Set([...prev, agent.key]))
        setTimeout(() => {
          setAgentIndex(i => i + 1)
          setProgress(0)
          setThoughtIndex(0)
        }, 200)
      }
    }, tickInterval)

    const thoughtTimer = setInterval(() => {
      setThoughtIndex(i => Math.min(i + 1, agent.thoughts.length - 1))
    }, agent.duration / agent.thoughts.length)

    return () => {
      clearInterval(progressTimer)
      clearInterval(thoughtTimer)
    }
  }, [agentIndex])

  const getStatus = (index) => {
    if (completedAgents.has(AGENTS[index]?.key)) return 'complete'
    if (index === agentIndex && agentIndex < AGENTS.length) return 'active'
    return 'pending'
  }

  const currentAgent = AGENTS[agentIndex]

  return (
    <div className="flex flex-col gap-4 pb-6">
      <div>
        <p className="text-xs text-fpl_text/40 uppercase tracking-widest">Processing</p>
        <p className="text-lg font-black text-fpl_text">Analysing your squad...</p>
      </div>

      {/* Overall progress */}
      <div className="bg-card rounded-xl p-4 border border-white/5">
        <div className="flex justify-between items-center mb-2">
          <p className="text-xs text-fpl_text/50">Agent pipeline</p>
          <p className="text-xs text-primary font-bold">
            {completedAgents.size}/{AGENTS.length} complete
          </p>
        </div>
        <div className="h-2 bg-white/5 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-primary to-secondary rounded-full transition-all duration-500"
            style={{ width: `${(completedAgents.size / AGENTS.length) * 100}%` }}
          />
        </div>
      </div>

      {/* Agent bars */}
      <div className="flex flex-col gap-2">
        {AGENTS.map((agent, i) => (
          <AgentProgressBar
            key={agent.key}
            name={agent.name}
            description={agent.description}
            status={getStatus(i)}
            progress={i === agentIndex ? progress : 0}
            thought={i === agentIndex ? agent.thoughts[thoughtIndex] : null}
          />
        ))}
      </div>

      {/* Live insight */}
      {currentAgent && agentIndex < AGENTS.length && (
        <div className="bg-secondary/5 border border-secondary/15 rounded-xl p-4">
          <p className="text-[10px] text-secondary/60 uppercase tracking-widest mb-1">Live insight</p>
          <p className="text-sm text-fpl_text/70 italic">
            💡 {currentAgent.thoughts[thoughtIndex]}
          </p>
        </div>
      )}

      {completedAgents.size === AGENTS.length && (
        <div className="bg-primary/10 border border-primary/30 rounded-xl p-4 text-center">
          <p className="text-primary font-bold text-sm">All agents complete — loading results...</p>
        </div>
      )}
    </div>
  )
}
