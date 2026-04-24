import { useEffect, useState } from 'react'
import { useAppStore } from '../state/useAppStore'

interface TopicTuple {
  category: string
  topic: string
}

export function MemoryPanel() {
  const memoryUpdatedAt = useAppStore((s) => s.memoryUpdatedAt)
  const [topics, setTopics] = useState<TopicTuple[]>([])
  const [interestsStr, setInterestsStr] = useState<string>('')
  const [contextText, setContextText] = useState<string>('')
  const [contextLoading, setContextLoading] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let disposed = false
    const fetchData = async () => {
      setLoading(true)
      try {
        const [topicsRes, interestsRes] = await Promise.all([
          fetch('/api/topics'),
          fetch('/api/interests'),
        ])
        if (!disposed) {
          if (topicsRes.ok) {
            const data = await topicsRes.json()
            const rawTopics: unknown[] = data.topics ?? []
            setTopics(
              rawTopics
                .filter((t): t is [string, string] => Array.isArray(t) && t.length >= 2)
                .map(([category, topic]) => ({ category, topic }))
            )
          }
          if (interestsRes.ok) {
            const data = await interestsRes.json()
            setInterestsStr(data.interests ?? '')
          }
        }
      } catch {
        // Non-critical
      } finally {
        if (!disposed) setLoading(false)
      }
    }
    void fetchData()
    return () => { disposed = true }
  }, [memoryUpdatedAt])

  const loadContext = async () => {
    setContextLoading(true)
    try {
      const res = await fetch('/api/memory-context')
      if (res.ok) {
        const data = await res.json()
        setContextText(data.memory_context ?? '')
      }
    } catch {
      // Non-critical
    } finally {
      setContextLoading(false)
    }
  }

  const hasData = topics.length > 0 || interestsStr || memoryUpdatedAt
  const [contextOpen, setContextOpen] = useState(false)

  if (!hasData && !loading) {
    return <p className="orchestration-empty">No memory data yet. Send a message to build memory.</p>
  }

  return (
    <div>
      {memoryUpdatedAt && (
        <div className="orchestration-row">
          <span className="orchestration-label">Last Saved</span>
          <span className="orchestration-value orchestration-memory-ok">
            {new Date(memoryUpdatedAt).toLocaleTimeString()}
          </span>
        </div>
      )}

      {loading ? (
        <p className="orchestration-empty">Loading...</p>
      ) : (
        <>
          {topics.length > 0 && (
            <div className="memory-section">
              <span className="orchestration-label">Tracked Topics ({topics.length})</span>
              <div className="memory-tags">
                {topics.slice(0, 8).map((t) => (
                  <span
                    key={`${t.category}:${t.topic}`}
                    className="memory-tag"
                    title={t.category}
                  >
                    {t.topic}
                  </span>
                ))}
                {topics.length > 8 && (
                  <span className="memory-tag memory-tag-more">+{topics.length - 8}</span>
                )}
              </div>
            </div>
          )}

          {interestsStr && (
            <div className="memory-section">
              <span className="orchestration-label">Interests</span>
              <div className="memory-interests-text">{interestsStr}</div>
            </div>
          )}
        </>
      )}

      <div className="memory-section">
        <div className="memory-context-header">
          <span className="orchestration-label">Prompt Context</span>
          <button
            type="button"
            className="memory-context-toggle"
            onClick={() => {
              if (!contextOpen) {
                setContextOpen(true)
                if (!contextText) void loadContext()
              } else {
                setContextOpen(false)
              }
            }}
          >
            {contextOpen ? 'Hide' : 'Show'}
          </button>
        </div>
        {contextOpen && (
          <div className="memory-context-content">
            {contextLoading ? (
              <p className="orchestration-empty">Loading...</p>
            ) : contextText ? (
              <pre className="memory-context-pre">{contextText}</pre>
            ) : (
              <p className="orchestration-empty">No context available.</p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
