import { useState, useEffect, useCallback } from 'react'
import { fetchWithAuth } from '../../lib/localRunToken'
import { useAppStore } from '../../state/useAppStore'

interface ScopeData {
  targets: string[]
  exclusions: string[]
  rules_of_engagement: string
}

interface ScopeBarProps {
  engagementId: string
}

export function ScopeBar({ engagementId }: ScopeBarProps) {
  const [scope, setScope] = useState<ScopeData>({ targets: [], exclusions: [], rules_of_engagement: '' })
  const [editing, setEditing] = useState(false)
  const [editTargets, setEditTargets] = useState('')
  const [editExclusions, setEditExclusions] = useState('')
  const [editRules, setEditRules] = useState('')
  const activityCount = useAppStore((s) => s.activityFeedItems.length)

  const loadScope = useCallback(async () => {
    try {
      const resp = await fetchWithAuth(`/api/pentest/engagements/${engagementId}/scope`)
      if (resp.ok) {
        const data = await resp.json()
        if (data.scope) setScope(data.scope)
      }
    } catch { /* non-critical */ }
  }, [engagementId])

  useEffect(() => { void loadScope() }, [loadScope, activityCount])

  const startEdit = () => {
    setEditTargets(scope.targets.join(', '))
    setEditExclusions(scope.exclusions.join(', '))
    setEditRules(scope.rules_of_engagement)
    setEditing(true)
  }

  const saveEdit = async () => {
    try {
      await fetchWithAuth(`/api/pentest/engagements/${engagementId}/scope`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          targets: editTargets.split(',').map((t) => t.trim()).filter(Boolean),
          exclusions: editExclusions.split(',').map((t) => t.trim()).filter(Boolean),
          rules_of_engagement: editRules,
        }),
      })
      setEditing(false)
      void loadScope()
    } catch { /* non-critical */ }
  }

  if (editing) {
    return (
      <div className="scope-bar" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 6 }}>
        <div style={{ display: 'flex', gap: 8 }}>
          <div style={{ flex: 1 }}>
            <div className="scope-bar-label" style={{ marginBottom: 2 }}>Targets</div>
            <input value={editTargets} onChange={(e) => setEditTargets(e.target.value)} placeholder="192.168.1.0/24, *.example.com" style={{ width: '100%', padding: '3px 6px', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 4, color: 'inherit', fontSize: 11, boxSizing: 'border-box' }} />
          </div>
          <div style={{ flex: 1 }}>
            <div className="scope-bar-label" style={{ marginBottom: 2 }}>Exclusions</div>
            <input value={editExclusions} onChange={(e) => setEditExclusions(e.target.value)} placeholder="192.168.1.1" style={{ width: '100%', padding: '3px 6px', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 4, color: 'inherit', fontSize: 11, boxSizing: 'border-box' }} />
          </div>
        </div>
        <div>
          <div className="scope-bar-label" style={{ marginBottom: 2 }}>Rules of Engagement</div>
          <textarea value={editRules} onChange={(e) => setEditRules(e.target.value)} rows={2} style={{ width: '100%', padding: '3px 6px', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 4, color: 'inherit', fontSize: 11, fontFamily: 'inherit', resize: 'vertical', boxSizing: 'border-box' }} />
        </div>
        <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
          <button type="button" onClick={() => setEditing(false)} style={{ padding: '3px 10px', borderRadius: 4, border: '1px solid rgba(255,255,255,0.1)', background: 'transparent', color: 'inherit', fontSize: 11, cursor: 'pointer' }}>Cancel</button>
          <button type="button" onClick={saveEdit} style={{ padding: '3px 10px', borderRadius: 4, border: '1px solid rgba(76,175,80,0.3)', background: 'rgba(76,175,80,0.15)', color: '#4caf50', fontSize: 11, cursor: 'pointer' }}>Save</button>
        </div>
      </div>
    )
  }

  return (
    <div className="scope-bar">
      <div>
        <span className="scope-bar-label">Targets: </span>
        <span>{scope.targets.length > 0 ? scope.targets.join(', ') : 'none'}</span>
      </div>
      {scope.exclusions.length > 0 && (
        <div>
          <span className="scope-bar-label">Excl: </span>
          <span>{scope.exclusions.join(', ')}</span>
        </div>
      )}
      {scope.rules_of_engagement && (
        <div style={{ opacity: 0.5, fontSize: 10 }}>
          <span className="scope-bar-label">Rules: </span>
          {scope.rules_of_engagement.slice(0, 100)}{scope.rules_of_engagement.length > 100 ? '...' : ''}
        </div>
      )}
      <button
        type="button"
        onClick={startEdit}
        style={{
          marginLeft: 'auto', background: 'transparent',
          border: '1px solid rgba(255,255,255,0.08)', borderRadius: 4,
          color: 'inherit', fontSize: 10, padding: '2px 6px', cursor: 'pointer',
        }}
      >
        Edit
      </button>
    </div>
  )
}
