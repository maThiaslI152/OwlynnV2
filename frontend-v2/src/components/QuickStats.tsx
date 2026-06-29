import { useState, useEffect, useCallback } from 'react'
import { useAppStore } from '../state/useAppStore'
import { fetchWithAuth } from '../lib/localRunToken'

interface TargetsSummary {
  hosts: number
  ports: number
  services: number
}

export function QuickStats() {
  const activeEngagementId = useAppStore((s) => s.activeEngagementId)
  const [targetsSummary, setTargetsSummary] = useState<TargetsSummary>({ hosts: 0, ports: 0, services: 0 })
  const [evidenceCount, setEvidenceCount] = useState(0)

  const loadStats = useCallback(async () => {
    if (!activeEngagementId) return
    try {
      const [targetsResp, evidenceResp] = await Promise.all([
        fetchWithAuth(`/api/pentest/engagements/${activeEngagementId}/targets/summary`),
        fetchWithAuth(`/api/pentest/engagements/${activeEngagementId}/evidence`),
      ])
      if (targetsResp.ok) {
        const data = await targetsResp.json()
        if (data.summary) setTargetsSummary(data.summary)
      }
      if (evidenceResp.ok) {
        const data = await evidenceResp.json()
        setEvidenceCount((data.evidence || []).length)
      }
    } catch { /* non-critical */ }
  }, [activeEngagementId])

  useEffect(() => {
    void loadStats()
    const interval = setInterval(loadStats, 10000)
    return () => clearInterval(interval)
  }, [loadStats])

  if (!activeEngagementId) return null

  return (
    <div className="quick-stats">
      <span className="quick-stat">
        <span className="quick-stat-value">{targetsSummary.hosts}</span>
        <span className="quick-stat-label">hosts</span>
      </span>
      <span className="quick-stat">
        <span className="quick-stat-value">{targetsSummary.ports}</span>
        <span className="quick-stat-label">ports</span>
      </span>
      <span className="quick-stat">
        <span className="quick-stat-value">{evidenceCount}</span>
        <span className="quick-stat-label">evidence</span>
      </span>
    </div>
  )
}
