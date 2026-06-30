import { useState, useEffect, useCallback } from 'react'
import { fetchWithAuth } from '../lib/localRunToken'
import { useAppStore } from '../state/useAppStore'

interface Finding {
  id: string
  title: string
  severity: string
  status: string
  target: string
  description: string
  remediation: string
  cvss: number | null
  cwe: string
  cve: string
  owasp_category: string
  tags: string[]
  discovered_at: string
}

interface FindingsTableProps {
  engagementId: string
}

const SEVERITY_ORDER: Record<string, number> = {
  critical: 0, high: 1, medium: 2, low: 3, info: 4,
}

export function FindingsTable({ engagementId }: FindingsTableProps) {
  const [findings, setFindings] = useState<Finding[]>([])
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [filterSev, setFilterSev] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const activityCount = useAppStore((s) => s.activityFeedItems.length)

  const loadFindings = useCallback(async () => {
    try {
      const params = new URLSearchParams()
      if (filterSev) params.set('severity', filterSev)
      const resp = await fetchWithAuth(
        `/api/pentest/engagements/${engagementId}/findings?${params}`
      )
      if (resp.ok) {
        const data = await resp.json()
        const sorted = (data.findings || []).sort(
          (a: Finding, b: Finding) =>
            (SEVERITY_ORDER[a.severity] ?? 5) - (SEVERITY_ORDER[b.severity] ?? 5)
        )
        setFindings(sorted)
      }
    } catch { /* non-critical */ }
    finally { setLoading(false) }
  }, [engagementId, filterSev])

  useEffect(() => {
    void loadFindings()
    const interval = setInterval(loadFindings, 10000)
    return () => clearInterval(interval)
  }, [loadFindings, activityCount])

  if (loading && findings.length === 0) {
    return <div className="pd-panel"><div className="pd-panel-header">Findings</div><div className="pd-empty">Loading...</div></div>
  }

  return (
    <div className="pd-panel" style={{ height: '100%' }}>
      <div className="pd-panel-header">
        <span>Findings ({findings.length})</span>
        <select
          value={filterSev}
          onChange={(e) => setFilterSev(e.target.value)}
          style={{
            background: 'transparent', border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: 4, color: 'inherit', fontSize: 10, padding: '2px 4px',
          }}
        >
          <option value="">All</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
          <option value="info">Info</option>
        </select>
      </div>
      <div className="pd-panel-body" style={{ padding: 0 }}>
        {findings.length === 0 ? (
          <div className="pd-empty">No findings yet</div>
        ) : (
          <table className="findings-table">
            <thead>
              <tr>
                <th className="sev-cell">Sev</th>
                <th>Title</th>
                <th>Target</th>
                <th>Status</th>
                <th>CVSS</th>
                <th>CWE</th>
              </tr>
            </thead>
            <tbody>
              {findings.map((f) => (
                <>
                  <tr key={f.id} onClick={() => setExpandedId(expandedId === f.id ? null : f.id)}>
                    <td className="sev-cell">
                      <span className={`severity-badge severity-${f.severity}`}>
                        {f.severity.slice(0, 4).toUpperCase()}
                      </span>
                    </td>
                    <td>{f.title}</td>
                    <td style={{ opacity: 0.6 }}>{f.target || '—'}</td>
                    <td style={{ opacity: 0.6 }}>{f.status}</td>
                    <td style={{ opacity: 0.6 }}>{f.cvss ?? '—'}</td>
                    <td style={{ opacity: 0.6 }}>{f.cwe || '—'}</td>
                  </tr>
                  {expandedId === f.id && (
                    <tr key={`${f.id}-detail`}>
                      <td colSpan={6} style={{ padding: '8px 12px', background: 'rgba(255,255,255,0.02)' }}>
                        <div style={{ fontSize: 11, lineHeight: 1.6 }}>
                          {f.description && <div style={{ marginBottom: 6 }}><strong>Description:</strong> {f.description}</div>}
                          {f.remediation && <div style={{ marginBottom: 6 }}><strong>Remediation:</strong> {f.remediation}</div>}
                          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', opacity: 0.6, fontSize: 10 }}>
                            {f.cve && <span>CVE: {f.cve}</span>}
                            {f.owasp_category && <span>OWASP: {f.owasp_category}</span>}
                            {f.tags.length > 0 && <span>Tags: {f.tags.join(', ')}</span>}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
