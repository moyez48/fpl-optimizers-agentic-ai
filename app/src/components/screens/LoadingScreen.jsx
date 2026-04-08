import React, { useState, useEffect } from 'react'
import AgentProgressBar from '../ui/AgentProgressBar'

const AGENTS = [
  {
    key: 'statistician',
    name: 'Statistician Agent',
    description: 'Fetches FPL data · engineers features · runs XGBoost predictions',
    thoughts: [
      'Fetching FPL bootstrap and fixture data...',
      'Engineering 180+ player features per gameweek...',
      'Running XGBoost model across all players...',
      'Computing start probabilities and risk adjustments...',
      'Ranking all players by expected points...',
    ],
    duration: 2200,
  },
  {
    key: 'manager',
    name: 'Manager Agent',
    description: 'Analyses captain options · identifies form leaders',
    thoughts: [
      'Analysing top player predictions by expected points...',
      'Computing captain shortlist...',
      'Filtering by start probability and fixture difficulty...',
      'Identifying form leaders and in-form differentials...',
      'Building gameweek summary...',
    ],
    duration: 2000,
  },
  {
    key: 'sporting_director',
    name: 'Sporting Director Agent',
    description: 'Evaluates transfer options · scores sell/buy pairs',
    thoughts: [
      'Loading full player pool from predictions...',
      'Fetching upcoming fixture schedules...',
      'Enumerating valid transfer pairs...',
      'Scoring transfers by expected net gain...',
      'Detecting wildcard and hold conditions...',
    ],
    duration: 1800,
  },
]

export default function LoadingScreen({ onComplete }) {
  const [agentIndex, setAgentIndex]         = useState(0)
  const [progress, setProgress]             = useState(0)
  const [thoughtIndex, setThoughtIndex]     = useState(0)
  const [completedAgents, setCompletedAgents] = useState(new Set())
  const [waitingForApi, setWaitingForApi]   = useState(false)

  useEffect(() => {
    if (agentIndex >= AGENTS.length) {
      setWaitingForApi(true)
      // Still need to await the real API — onComplete handles that
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
  const allDone = completedAgents.size === AGENTS.length

  return (
    <div className="flex flex-col gap-4 pb-6">
      <div>
        <p className="text-xs text-fpl_text/40 uppercase tracking-widest">Processing</p>
        <p className="text-lg font-black text-fpl_text">Running agent pipeline...</p>
      </div>

      {/* Overall progress */}
      <div className="bg-card rounded-xl p-4 border border-white/5">
        <div className="flex justify-between items-center mb-2">
          <p className="text-xs text-fpl_text/50">Agent pipeline</p>
          <p className="text-xs text-primary font-bold">{completedAgents.size}/{AGENTS.length} complete</p>
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

      {/* Live insight while animating */}
      {currentAgent && !allDone && (
        <div className="bg-secondary/5 border border-secondary/15 rounded-xl p-4">
          <p className="text-[10px] text-secondary/60 uppercase tracking-widest mb-1">Live insight</p>
          <p className="text-sm text-fpl_text/70 italic">💡 {currentAgent.thoughts[thoughtIndex]}</p>
        </div>
      )}

      {/* Waiting for real API response */}
      {allDone && (
        <div className="bg-primary/10 border border-primary/30 rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className="w-4 h-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin shrink-0" />
            <div>
              <p className="text-primary font-bold text-sm">Awaiting agent response...</p>
              <p className="text-[10px] text-primary/50 mt-0.5">XGBoost pipeline running — this takes ~60s on first load, then results are cached.</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
