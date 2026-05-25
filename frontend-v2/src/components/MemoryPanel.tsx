import { useEffect, useState, useCallback } from 'react'
import { useAppStore } from '../state/useAppStore'

interface TopicTuple {
  category: string
  topic: string
}

interface Mem0Item {
  id: string
  memory: string
  text: string
  created_at: string
  user_id: string
}

export function MemoryPanel() {
  const memoryUpdatedAt = useAppStore((s) => s.memoryUpdatedAt)
  const [topics, setTopics] = useState<TopicTuple[]>([])
  const [interestsStr, setInterestsStr] = useState<string>('')
  const [contextText, setContextText] = useState<string>('')
  const [contextLoading, setContextLoading] = useState(false)
  const [loading, setLoading] = useState(true)

  // Mem0 state
  const [mem0Memories, setMem0Memories] = useState<Mem0Item[]>([])
  const [mem0Loading, setMem0Loading] = useState(false)
  const [mem0SearchQuery, setMem0SearchQuery] = useState('')
  const [mem0Error, setMem0Error] = useState('')

  // Fetch topics and interests
  useEffect(() => {
    let disposed = false
    const fetchData = async () => {
      setLoading(true)
      try {
        const controller = new AbortController()
        const timeoutId = setTimeout(() => controller.abort(), 10_000)
        const [topicsRes, interestsRes] = await Promise.all([
          fetch('/api/topics', { signal: controller.signal }),
          fetch('/api/interests', { signal: controller.signal }),
        ])
        clearTimeout(timeoutId)
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

  // Fetch Mem0 memories
  const loadMem0Memories = useCallback(async (query = '') => {
    setMem0Loading(true)
    setMem0Error('')
    try {
      const params = new URLSearchParams()
      if (query) params.set('query', query)
      params.set('limit', '50')
      const res = await fetch(`/api/mem0/search?${params.toString()}`)
      if (res.ok) {
        const data = await res.json()
        if (data.status === 'ok') {
          setMem0Memories(data.memories ?? [])
        } else {
          setMem0Error(data.message ?? 'Failed to load memories')
        }
      } else {
        setMem0Error('Failed to fetch memories')
      }
    } catch {
      setMem0Error('Network error')
    } finally {
      setMem0Loading(false)
    }
  }, [])

  // Initial load of Mem0 memories
  useEffect(() => {
    void loadMem0Memories()
  }, [memoryUpdatedAt, loadMem0Memories])

  // Delete a Mem0 memory
  const handleDeleteMemory = async (e: React.MouseEvent, memoryId: string) => {
    e.stopPropagation()
    try {
      const res = await fetch('/api/mem0/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ memory_id: memoryId }),
      })
      if (res.ok) {
        // Refresh the list
        void loadMem0Memories(mem0SearchQuery)
      }
    } catch {
      // non-critical
    }
  }

  const hasTopicsOrInterests = topics.length > 0 || interestsStr || memoryUpdatedAt
  const [contextOpen, setContextOpen] = useState(false)
  const [mem0Open, setMem0Open] = useState(false)

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

      {/* Topics and Interests section */}
      {loading ? (
        <p className="orchestration-empty">Loading...</p>
      ) : hasTopicsOrInterests ? (
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
      ) : null}

      {/* Mem0 Long-Term Memories section */}
      <div className="memory-section">
        <div className="memory-context-header">
          <span className="orchestration-label">
            Long-Term Memories {mem0Memories.length > 0 && `(${mem0Memories.length})`}
          </span>
              <button
                type="button"
                className="memory-context-toggle"
                onClick={(e) => {
                  e.stopPropagation()
                  if (!mem0Open) {
                    setMem0Open(true)
                  } else {
                    setMem0Open(false)
                  }
                }}
              >
                {mem0Open ? 'Hide' : 'Show'}
              </button>
        </div>
        {mem0Open && (
          <div>
            {/* Search bar for memories */}
            <div style={{ display: 'flex', gap: 4, marginBottom: 6 }}>
              <input
                type="text"
                className="memory-search-input"
                placeholder="Search memories..."
                value={mem0SearchQuery}
                onChange={(e) => setMem0SearchQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    void loadMem0Memories(mem0SearchQuery)
                  }
                }}
              />
              <button
                type="button"
                className="memory-context-toggle"
                onClick={(e) => {
                  e.stopPropagation()
                  void loadMem0Memories(mem0SearchQuery)
                }}
                style={{ whiteSpace: 'nowrap' }}
              >
                Search
              </button>
              {mem0SearchQuery && (
                <button
                  type="button"
                  className="memory-context-toggle"
                  onClick={(e) => {
                    e.stopPropagation()
                    setMem0SearchQuery('')
                    void loadMem0Memories('')
                  }}
                >
                  Clear
                </button>
              )}
            </div>

            {mem0Error && (
              <p className="orchestration-empty" style={{ color: 'var(--red)' }}>{mem0Error}</p>
            )}

            {mem0Loading ? (
              <p className="orchestration-empty">Loading memories...</p>
            ) : mem0Memories.length > 0 ? (
              <div className="memory-list">
                {mem0Memories.map((mem) => (
                  <div key={mem.id} className="memory-list-item">
                    <div className="memory-list-item-text">{mem.memory || mem.text}</div>
                    <button
                      type="button"
                      className="memory-list-delete"
                      title="Delete this memory"
                      onClick={(e) => handleDeleteMemory(e, mem.id)}
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="orchestration-empty">No long-term memories yet. Chat with the assistant to build memories.</p>
            )}
          </div>
        )}
      </div>

      {/* Prompt Context section */}
      <div className="memory-section">
        <div className="memory-context-header">
          <span className="orchestration-label">Prompt Context</span>
          <button
            type="button"
            className="memory-context-toggle"
            onClick={(e) => {
              e.stopPropagation()
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
