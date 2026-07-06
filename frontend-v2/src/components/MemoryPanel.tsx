import { useEffect, useState, useCallback, useRef } from 'react'
import { useAppStore } from '../state/useAppStore'
import toast from 'react-hot-toast'
import { fetchWithAuth } from '../lib/localRunToken'

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
  const [fetchError, setFetchError] = useState('')

  // Mem0 state
  const [mem0Memories, setMem0Memories] = useState<Mem0Item[]>([])
  const [mem0Loading, setMem0Loading] = useState(false)
  const [mem0SearchQuery, setMem0SearchQuery] = useState('')
  const [mem0Error, setMem0Error] = useState('')

  const [newMemory, setNewMemory] = useState('')
  const [addingMemory, setAddingMemory] = useState(false)

  // Fetch topics and interests
  useEffect(() => {
    let disposed = false
    let timeoutId: ReturnType<typeof setTimeout> | undefined
    const fetchData = async () => {
      setLoading(true)
      setFetchError('')
      try {
        const controller = new AbortController()
        timeoutId = setTimeout(() => controller.abort(), 5_000)
        const [topicsRes, interestsRes] = await Promise.all([
          fetchWithAuth('/api/topics', { signal: controller.signal }),
          fetchWithAuth('/api/interests', { signal: controller.signal }),
        ])
        clearTimeout(timeoutId)
        if (!disposed) {
          if (topicsRes.ok) {
            const data = await topicsRes.json()
            if (data.status === 'ok') {
              const rawTopics: unknown[] = data.topics ?? []
              setTopics(
                rawTopics
                  .filter((t): t is [string, string] => Array.isArray(t) && t.length >= 2)
                  .map(([category, topic]) => ({ category, topic }))
              )
            } else {
              console.warn('[MemoryPanel] /api/topics returned error:', data.message ?? 'unknown')
            }
          }
          if (interestsRes.ok) {
            const data = await interestsRes.json()
            if (data.status === 'ok') {
              setInterestsStr(data.interests ?? '')
            } else {
              console.warn('[MemoryPanel] /api/interests returned error:', data.message ?? 'unknown')
            }
          }
        }
      } catch (err) {
        if (!disposed) {
          console.warn('[MemoryPanel] fetch error:', err)
          setFetchError('Failed to load memory data. Is the backend running?')
          toast.error('Failed to load memory data')
        }
      } finally {
        if (!disposed) setLoading(false)
      }
    }
    void fetchData()
    return () => {
      disposed = true
      if (timeoutId !== undefined) clearTimeout(timeoutId)
    }
  }, [memoryUpdatedAt])

  const mem0AbortRef = useRef<AbortController | null>(null)

  // Fetch Mem0 memories
  const loadMem0Memories = useCallback(async (query = '') => {
    if (mem0AbortRef.current) mem0AbortRef.current.abort()
    const controller = new AbortController()
    mem0AbortRef.current = controller

    setMem0Loading(true)
    setMem0Error('')
    try {
      const params = new URLSearchParams()
      if (query) params.set('query', query)
      params.set('limit', '50')
      const res = await fetchWithAuth(`/api/mem0/search?${params.toString()}`, { signal: controller.signal })
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
    } catch (e: any) {
      if (e.name === 'AbortError') return
      console.warn('[loadMem0Memories]', e)
      toast.error('Network error loading memories')
      setMem0Error('Network error')
    } finally {
      setMem0Loading(false)
    }
  }, [])

  // Initial load of Mem0 memories
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadMem0Memories()
  }, [memoryUpdatedAt, loadMem0Memories])

  // Delete a Mem0 memory
  const handleDeleteMemory = async (e: React.MouseEvent, memoryId: string) => {
    e.stopPropagation()
    try {
      const res = await fetchWithAuth('/api/mem0/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ memory_id: memoryId }),
      })
      if (res.ok) {
        // Refresh the list
        void loadMem0Memories(mem0SearchQuery)
      }
    } catch (e) {
      console.warn('[deleteMemory]', e)
      toast.error('Failed to delete memory')
    }
  }

  const handleAddMemory = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newMemory.trim()) return
    setAddingMemory(true)
    try {
      const res = await fetchWithAuth('/api/mem0/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ memory: newMemory }),
      })
      if (res.ok) {
        setNewMemory('')
        toast.success('Memory added manually')
        void loadMem0Memories(mem0SearchQuery)
      } else {
        toast.error('Failed to add memory')
      }
    } catch (e) {
      console.warn('[addMemory]', e)
      toast.error('Network error')
    } finally {
      setAddingMemory(false)
    }
  }

  const handleClearAll = async () => {
    if (!window.confirm('Are you sure you want to clear ALL long-term memories? This cannot be undone.')) return
    try {
      const res = await fetchWithAuth('/api/mem0/clear', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: 'owner' }),
      })
      if (res.ok) {
        toast.success('All memories cleared')
        void loadMem0Memories(mem0SearchQuery)
      } else {
        toast.error('Failed to clear memories')
      }
    } catch (e) {
      console.warn('[clearMemories]', e)
      toast.error('Network error')
    }
  }

  const hasTopicsOrInterests = topics.length > 0 || interestsStr || memoryUpdatedAt
  const [contextOpen, setContextOpen] = useState(false)
  const [mem0Open, setMem0Open] = useState(true)

  const loadContext = async () => {
    setContextLoading(true)
    try {
      const res = await fetchWithAuth('/api/memory-context')
      if (res.ok) {
        const data = await res.json()
        setContextText(data.memory_context ?? '')
      }
    } catch (e) {
      console.warn('[loadContext]', e)
      toast.error('Failed to load memory context')
    } finally {
      setContextLoading(false)
    }
  }

  return (
    <div className="menu-dropdown-content">
      <h4>Memory Status</h4>
      {memoryUpdatedAt ? (
        <div className="menu-dropdown-item" style={{ cursor: 'default', display: 'flex', justifyContent: 'space-between' }}>
          <span>Last Saved</span>
          <span style={{ color: 'var(--green)' }}>{new Date(memoryUpdatedAt).toLocaleTimeString()}</span>
        </div>
      ) : (
        <div className="menu-dropdown-item" style={{ cursor: 'default', color: 'var(--text-muted)' }}>
          Not saved yet
        </div>
      )}

      <hr />

      {/* Topics and Interests section */}
      <h4>Tracked Topics</h4>
      {fetchError ? (
        <div 
          className="menu-dropdown-item" 
          onClick={() => {
            setFetchError('')
            void (async () => {
              setLoading(true)
              try {
                const controller = new AbortController()
                const timeoutId = setTimeout(() => controller.abort(), 5_000)
                const [topicsRes, interestsRes] = await Promise.all([
                  fetchWithAuth('/api/topics', { signal: controller.signal }),
                  fetchWithAuth('/api/interests', { signal: controller.signal }),
                ])
                clearTimeout(timeoutId)
                if (topicsRes.ok) {
                  const data = await topicsRes.json()
                  if (data.status === 'ok') {
                    const rawTopics: unknown[] = data.topics ?? []
                    setTopics(
                      rawTopics
                        .filter((t): t is [string, string] => Array.isArray(t) && t.length >= 2)
                        .map(([category, topic]) => ({ category, topic }))
                    )
                  }
                }
                if (interestsRes.ok) {
                  const data = await interestsRes.json()
                  if (data.status === 'ok') setInterestsStr(data.interests ?? '')
                }
              } catch {
                setFetchError('Retry failed. Is the backend running?')
                toast.error('Failed to refresh memory data')
              } finally {
                setLoading(false)
              }
            })()
          }}
        >
          <span style={{ color: 'var(--red)' }}>{fetchError}</span> (Click to retry)
        </div>
      ) : loading ? (
        <div className="menu-dropdown-item" style={{ cursor: 'default' }}>Loading...</div>
      ) : hasTopicsOrInterests ? (
        <>
          {topics.length > 0 && (
            <div style={{ padding: '4px 12px' }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                {topics.slice(0, 8).map((t) => (
                  <span
                    key={`${t.category}:${t.topic}`}
                    style={{ fontSize: '11px', padding: '2px 6px', background: 'var(--bg-elevated)', borderRadius: '4px', border: '1px solid var(--border-subtle)' }}
                    title={t.category}
                  >
                    {t.topic}
                  </span>
                ))}
                {topics.length > 8 && (
                  <span style={{ fontSize: '11px', padding: '2px 6px', background: 'transparent', color: 'var(--text-muted)' }}>+{topics.length - 8}</span>
                )}
              </div>
            </div>
          )}

          {interestsStr && (
            <>
              <h4 style={{ marginTop: '12px' }}>Interests</h4>
              <div className="menu-dropdown-item" style={{ cursor: 'default', fontSize: '12px', whiteSpace: 'pre-wrap' }}>
                {interestsStr}
              </div>
            </>
          )}
        </>
      ) : (
        <div className="menu-dropdown-item" style={{ cursor: 'default', color: 'var(--text-muted)' }}>No topics or interests tracked yet.</div>
      )}

      <hr />

      {/* Mem0 Long-Term Memories section */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h4>Long-Term Memories {mem0Memories.length > 0 && `(${mem0Memories.length})`}</h4>
      </div>

      {mem0Open && (
        <div style={{ padding: '4px 8px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <form onSubmit={handleAddMemory} style={{ display: 'flex', gap: '4px' }}>
            <input 
              type="text" 
              style={{ flex: 1, padding: '4px 8px', borderRadius: '4px', border: '1px solid var(--border-subtle)', background: 'var(--bg-elevated)', color: 'var(--text-primary)', fontSize: '12px', outline: 'none' }}
              placeholder="Add a new memory manually..." 
              value={newMemory}
              onChange={(e) => setNewMemory(e.target.value)}
              disabled={addingMemory}
            />
            <button 
              type="submit" 
              disabled={!newMemory.trim() || addingMemory} 
              style={{ padding: '4px 10px', borderRadius: '4px', background: 'var(--accent)', color: '#fff', border: 'none', cursor: 'pointer', opacity: (!newMemory.trim() || addingMemory) ? 0.5 : 1 }}
            >
              +
            </button>
          </form>

          <div style={{ display: 'flex', gap: '4px' }}>
            <input
              type="text"
              style={{ flex: 1, padding: '4px 8px', borderRadius: '4px', border: '1px solid var(--border-subtle)', background: 'rgba(0,0,0,0.2)', color: 'var(--text-primary)', fontSize: '12px', outline: 'none' }}
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
              onClick={(e) => {
                e.stopPropagation()
                void loadMem0Memories(mem0SearchQuery)
              }}
              style={{ padding: '4px 8px', borderRadius: '4px', background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-primary)', cursor: 'pointer', fontSize: '11px', outline: 'none' }}
            >
              Search
            </button>
          </div>

          {mem0Error && (
            <div style={{ color: 'var(--red)', fontSize: '12px', padding: '0 4px' }}>{mem0Error}</div>
          )}

          {mem0Loading ? (
            <div style={{ color: 'var(--text-muted)', fontSize: '12px', padding: '0 4px' }}>Loading memories...</div>
          ) : mem0Memories.length > 0 ? (
            <div style={{ maxHeight: '200px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {mem0Memories.map((mem) => (
                <div key={mem.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', padding: '6px 8px', background: 'var(--bg-elevated)', borderRadius: '4px', border: '1px solid var(--border-subtle)', fontSize: '12px' }}>
                  <div style={{ flex: 1, wordBreak: 'break-word', paddingRight: '8px', color: 'var(--text-secondary)' }}>
                    {mem.memory || mem.text}
                  </div>
                  <button
                    type="button"
                    title="Delete this memory"
                    onClick={(e) => handleDeleteMemory(e, mem.id)}
                    style={{ background: 'transparent', border: 'none', color: 'var(--red)', cursor: 'pointer', fontSize: '14px', lineHeight: 1, opacity: 0.8 }}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ color: 'var(--text-muted)', fontSize: '12px', padding: '0 4px' }}>No long-term memories found.</div>
          )}

          {mem0Memories.length > 0 && (
            <div 
              className="menu-dropdown-item" 
              style={{ color: 'var(--red)', textAlign: 'center', marginTop: '4px' }} 
              onClick={(e) => {
                e.stopPropagation()
                handleClearAll()
              }}
            >
              Clear All Memories
            </div>
          )}
        </div>
      )}

      <hr />

      {/* Prompt Context section */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h4>Prompt Context</h4>
        <button
          type="button"
          style={{ background: 'transparent', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: '11px', paddingRight: '12px' }}
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
        <div style={{ padding: '4px 12px' }}>
          {contextLoading ? (
            <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Loading...</div>
          ) : contextText ? (
            <pre style={{ margin: 0, padding: '8px', background: 'rgba(0,0,0,0.2)', borderRadius: '4px', fontSize: '11px', color: 'var(--text-secondary)', whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: '200px', overflowY: 'auto' }}>
              {contextText}
            </pre>
          ) : (
            <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>No context available.</div>
          )}
        </div>
      )}
    </div>
  )
}

