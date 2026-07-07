import { useState, useEffect, useCallback } from 'react'
import { useAppStore } from '../state/useAppStore'
import { fetchWithAuth } from '../lib/localRunToken'
import type { EngagementTab } from '../state/slices/modesSlice'

interface Engagement {
  id: string
  name: string
  client: string
  phase: string
  status: string
  is_active: boolean
  findings_summary: { total: number; critical: number; high: number; medium: number; low: number }
}

export function EngagementTabs() {
  const activeEngagementId = useAppStore((s) => s.activeEngagementId)
  const setActiveEngagementId = useAppStore((s) => s.setActiveEngagementId)
  const engagementTabs = useAppStore((s) => s.engagementTabs)
  const addEngagementTab = useAppStore((s) => s.addEngagementTab)
  const removeEngagementTab = useAppStore((s) => s.removeEngagementTab)
  const [switching, setSwitching] = useState<string | null>(null)

  const loadEngagements = useCallback(async () => {
    try {
      const resp = await fetchWithAuth('/api/pentest/engagements')
      if (resp.ok) {
        const data = await resp.json()
        const engs: Engagement[] = data.engagements || []
        for (const eng of engs) {
          const tab: EngagementTab = {
            id: eng.id,
            name: eng.name,
            phase: eng.phase,
            findingCounts: {
              critical: eng.findings_summary?.critical || 0,
              high: eng.findings_summary?.high || 0,
              medium: eng.findings_summary?.medium || 0,
              low: eng.findings_summary?.low || 0,
            },
            lastActivity: Date.now(),
          }
          addEngagementTab(tab)
          if (eng.is_active && activeEngagementId !== eng.id) {
            setActiveEngagementId(eng.id)
          }
        }
      }
    } catch { /* non-critical */ }
  }, [addEngagementTab, setActiveEngagementId, activeEngagementId])

  useEffect(() => {
    void loadEngagements()
    const interval = setInterval(loadEngagements, 15000)
    return () => clearInterval(interval)
  }, [loadEngagements])

  const handleSwitch = async (id: string) => {
    if (id === activeEngagementId) return
    setSwitching(id)
    try {
      const resp = await fetchWithAuth(`/api/pentest/engagements/${id}/resume`, { method: 'POST' })
      if (resp.ok) {
        setActiveEngagementId(id)
      }
    } catch { /* non-critical */ }
    finally { setSwitching(null) }
  }

  const handleClose = (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    removeEngagementTab(id)
  }

  const severityColor = (count: number, severity: string) => {
    if (count === 0) return 'rgba(255,255,255,0.15)'
    const colors: Record<string, string> = {
      critical: '#e94560', high: '#ff6b35', medium: '#ffa726', low: '#66bb6a',
    }
    return colors[severity] || 'rgba(255,255,255,0.15)'
  }

  if (engagementTabs.length === 0) return null

  return (
    <div style={{
      display: 'flex', gap: 2, padding: '0 8px', overflowX: 'auto',
      borderBottom: '1px solid rgba(255,255,255,0.05)',
      background: 'rgba(0,0,0,0.2)',
    }}>
      {engagementTabs.map((tab) => {
        const isActive = tab.id === activeEngagementId
        const total = tab.findingCounts.critical + tab.findingCounts.high + tab.findingCounts.medium + tab.findingCounts.low
        return (
          <div
            key={tab.id}
            onClick={() => void handleSwitch(tab.id)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '6px 12px', cursor: switching === tab.id ? 'wait' : 'pointer',
              opacity: switching === tab.id ? 0.5 : 1,
              borderBottom: isActive ? '2px solid #e94560' : '2px solid transparent',
              background: isActive ? 'rgba(233,69,96,0.08)' : 'transparent',
              borderRadius: '4px 4px 0 0', fontSize: 11, whiteSpace: 'nowrap',
              transition: 'all 0.15s ease',
            }}
          >
            <span style={{ fontWeight: isActive ? 600 : 400 }}>{tab.name}</span>
            <span style={{
              fontSize: 9, padding: '1px 5px', borderRadius: 3,
              background: isActive ? 'rgba(233,69,96,0.15)' : 'rgba(255,255,255,0.06)',
              color: isActive ? '#e94560' : '#888',
            }}>
              {tab.phase}
            </span>
            {total > 0 && (
              <span style={{ display: 'flex', gap: 2 }}>
                {tab.findingCounts.critical > 0 && (
                  <span style={{
                    fontSize: 9, padding: '0 3px', borderRadius: 2,
                    background: severityColor(tab.findingCounts.critical, 'critical'),
                    color: '#fff', fontWeight: 600,
                  }}>
                    {tab.findingCounts.critical}
                  </span>
                )}
                {tab.findingCounts.high > 0 && (
                  <span style={{
                    fontSize: 9, padding: '0 3px', borderRadius: 2,
                    background: severityColor(tab.findingCounts.high, 'high'),
                    color: '#fff', fontWeight: 600,
                  }}>
                    {tab.findingCounts.high}
                  </span>
                )}
              </span>
            )}
            <span
              onClick={(e) => handleClose(tab.id, e)}
              style={{
                fontSize: 10, opacity: 0.3, marginLeft: 4, cursor: 'pointer',
                padding: '0 2px', borderRadius: 2,
              }}
              title="Close tab"
            >
              ✕
            </span>
          </div>
        )
      })}
    </div>
  )
}
