import { useState, useEffect, useCallback } from 'react'
import { useAppStore } from '../state/useAppStore'
import { fetchWithAuth } from '../lib/localRunToken'

const PHASES = ['scope', 'recon', 'exploit', 'report', 'completed']

export function PhaseTracker() {
  const activeEngagementId = useAppStore((s) => s.activeEngagementId)
  const [currentPhase, setCurrentPhase] = useState('scope')

  const loadPhase = useCallback(async () => {
    if (!activeEngagementId) return
    try {
      const resp = await fetchWithAuth(`/api/pentest/engagements/${activeEngagementId}`)
      if (resp.ok) {
        const data = await resp.json()
        setCurrentPhase(data.engagement?.phase || 'scope')
      }
    } catch { /* non-critical */ }
  }, [activeEngagementId])

  useEffect(() => { void loadPhase() }, [loadPhase])

  const handleAdvance = async (phase: string) => {
    if (!activeEngagementId) return
    // Confirm destructive transitions
    if (phase === 'recon' && currentPhase === 'scope') {
      if (!confirm('Begin active reconnaissance? This will start active scanning.')) return
    }
    if (phase === 'report' && currentPhase === 'exploit') {
      if (!confirm('Generate report? This will start StirlingPDF.')) return
    }
    if (phase === 'completed') {
      if (!confirm('Mark engagement as completed?')) return
    }
    try {
      await fetchWithAuth(`/api/pentest/engagements/${activeEngagementId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phase }),
      })
      setCurrentPhase(phase)
    } catch { /* non-critical */ }
  }

  if (!activeEngagementId) return null

  const currentIdx = PHASES.indexOf(currentPhase)

  return (
    <div className="phase-tracker">
      {PHASES.map((phase, i) => (
        <span key={phase} style={{ display: 'contents' }}>
          <span
            className={`phase-step ${i === currentIdx ? 'phase-step-active' : i < currentIdx ? 'phase-step-completed' : ''}`}
            onClick={() => i > currentIdx && handleAdvance(phase)}
            title={i > currentIdx ? `Advance to ${phase}` : phase}
          >
            {i < currentIdx ? '✓' : ''} {phase}
          </span>
          {i < PHASES.length - 1 && <span className="phase-arrow">→</span>}
        </span>
      ))}
    </div>
  )
}
