import { useState, useEffect, useCallback, useRef } from 'react'
import { fetchWithAuth } from '../lib/localRunToken'
import { useAppStore, type ActivityFeedItem } from '../state/useAppStore'

interface ActivityFeedProps {
  engagementId: string
}

interface TimelineEvent {
  id: string
  timestamp: string
  type: string
  summary: string
  phase?: string
  finding_id?: string
}

interface BatchGroup {
  batchId: string | null
  items: ActivityFeedItem[]
  minTs: number
}

function groupByBatch(items: ActivityFeedItem[]): BatchGroup[] {
  const groups = new Map<string, BatchGroup>()
  const order: string[] = []

  for (const item of items) {
    const key = item.batchId || `single-${item.id}`
    if (!groups.has(key)) {
      groups.set(key, { batchId: item.batchId, items: [], minTs: item.ts })
      order.push(key)
    }
    groups.get(key)!.items.push(item)
  }

  return order.map((k) => groups.get(k)!)
}

export function ActivityFeed({ engagementId }: ActivityFeedProps) {
  const [timeline, setTimeline] = useState<TimelineEvent[]>([])
  const [expandedTool, setExpandedTool] = useState<string | null>(null)
  const feedRef = useRef<HTMLDivElement>(null)
  const activityItems = useAppStore((s) => s.activityFeedItems)
  const loadTimeline = useCallback(async () => {
    try {
      const resp = await fetchWithAuth(
        `/api/pentest/engagements/${engagementId}/timeline?limit=50`
      )
      if (resp.ok) {
        const data = await resp.json()
        setTimeline(data.events || [])
      }
    } catch { /* non-critical */ }
  }, [engagementId])

  useEffect(() => {
    void loadTimeline()
    const interval = setInterval(loadTimeline, 10000)
    return () => clearInterval(interval)
  }, [loadTimeline])

  // Auto-scroll to bottom on new items
  useEffect(() => {
    if (feedRef.current) {
      const el = feedRef.current
      const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 200
      if (isNearBottom) {
        el.scrollTop = el.scrollHeight
      }
    }
  }, [activityItems, timeline])

  const batchGroups = groupByBatch(activityItems)

  const statusIcon = (status: string) => {
    switch (status) {
      case 'running': return <span className="feed-spinner" />
      case 'success': return <span style={{ color: '#4caf50', fontSize: 12 }}>✓</span>
      case 'error': return <span style={{ color: '#ef4444', fontSize: 12 }}>✗</span>
      default: return <span style={{ opacity: 0.3 }}>○</span>
    }
  }

  return (
    <div className="pd-panel" style={{ height: '100%' }}>
      <div className="pd-panel-header">
        <span>Activity</span>
        <span style={{ fontSize: 10, opacity: 0.4 }}>
          {batchGroups.length + timeline.length} events
        </span>
      </div>
      <div className="pd-panel-body" ref={feedRef}>
        {/* Live activity items (from WS events) */}
        {batchGroups.map((group) => (
          <div key={group.batchId || group.items[0].id} className="feed-batch">
            {group.items.length > 1 && (
              <div className="feed-batch-header">
                <span className="feed-spinner" style={{ width: 10, height: 10 }} />
                <span>{group.items.length} tools</span>
                <span style={{ opacity: 0.4, marginLeft: 'auto', fontSize: 10 }}>
                  {new Date(group.minTs).toLocaleTimeString()}
                </span>
              </div>
            )}
            {group.items.map((item) => (
              <div key={item.id}>
                {item.type === 'agent_message' ? (
                  <div className="feed-agent-item">
                    <div style={{ fontSize: 10, opacity: 0.4, marginBottom: 2 }}>
                      Agent · {new Date(item.ts).toLocaleTimeString()}
                    </div>
                    <div>{item.summary}</div>
                  </div>
                ) : (
                  <div className="feed-tool-item">
                    {statusIcon(item.type.replace('tool_', ''))}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                        <span style={{ fontWeight: 500 }}>{item.toolName || 'tool'}</span>
                        {item.duration != null && (
                          <span style={{ opacity: 0.3, fontSize: 10 }}>
                            {(item.duration / 1000).toFixed(1)}s
                          </span>
                        )}
                        <span style={{ opacity: 0.3, fontSize: 10, marginLeft: 'auto' }}>
                          {new Date(item.ts).toLocaleTimeString()}
                        </span>
                      </div>
                      {item.output && (
                        <div
                          className={`feed-tool-output ${expandedTool === item.id ? 'feed-tool-output-expanded' : ''}`}
                          onClick={() => setExpandedTool(expandedTool === item.id ? null : item.id)}
                          style={{ cursor: 'pointer' }}
                        >
                          {expandedTool === item.id
                            ? item.output
                            : item.output.slice(0, 200)}{item.output.length > 200 && expandedTool !== item.id ? '...' : ''}
                        </div>
                      )}
                      {item.error && (
                        <div className="feed-tool-output" style={{ color: '#ef4444' }}>
                          {item.error.slice(0, 300)}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        ))}

        {/* Historical timeline events (from REST API) */}
        {timeline.map((evt) => (
          <div key={evt.id} style={{
            padding: '4px 10px', fontSize: 11, opacity: 0.5,
            borderBottom: '1px solid rgba(255,255,255,0.03)',
          }}>
            <span style={{ opacity: 0.5, fontSize: 10, marginRight: 6 }}>
              {new Date(evt.timestamp).toLocaleTimeString()}
            </span>
            <span style={{ opacity: 0.4, fontSize: 10, marginRight: 6 }}>[{evt.type}]</span>
            {evt.summary}
          </div>
        ))}

        {batchGroups.length === 0 && timeline.length === 0 && (
          <div className="pd-empty">No activity yet</div>
        )}
      </div>
    </div>
  )
}
