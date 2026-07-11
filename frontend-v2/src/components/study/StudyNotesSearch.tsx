import { useState, useEffect, useCallback } from 'react'
import toast from 'react-hot-toast'
import { NotebookPen } from 'lucide-react'
import { StudyAPI } from '../../sdk'

interface Note {
  id: string
  course_id: string
  chapter: string
  content: string
  tags: string[]
  created_at: string
}

export function StudyNotesSearch() {
  const [query, setQuery] = useState('')
  const [notes, setNotes] = useState<Note[]>([])
  const [loading, setLoading] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const searchNotes = useCallback(async (q: string) => {
    setLoading(true)
    try {
      const d = await StudyAPI.searchNotes(q)
      if (d?.status === 'ok') setNotes(d.notes || [])
    } catch (err) {
      toast.error('Failed to search notes')
      console.error('[StudyNotesSearch]', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    searchNotes(query)
  }, [query, searchNotes])

  return (
    <div style={{ padding: '8px 10px', fontSize: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600, fontSize: 13, marginBottom: 8 }}><NotebookPen size={16} /> Study Notes</div>

      {/* Search input */}
      <input
        type="text"
        placeholder="Search notes..."
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        style={{
          width: '100%',
          padding: '6px 8px',
          fontSize: 12,
          border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: 6,
          background: 'rgba(255,255,255,0.05)',
          color: 'inherit',
          marginBottom: 8,
        }}
      />

      {loading && <div style={{ opacity: 0.5 }}>Searching...</div>}

      {/* Notes list */}
      {notes.length === 0 && !loading && (
        <div style={{ opacity: 0.5, fontSize: 11 }}>
          {query ? 'No matching notes' : 'No notes yet'}
        </div>
      )}

      {notes.map((note) => (
        <div
          key={note.id}
          style={{
            padding: '6px 8px',
            marginBottom: 4,
            borderRadius: 6,
            background: 'rgba(255,255,255,0.03)',
            border: '1px solid rgba(255,255,255,0.05)',
            cursor: 'pointer',
          }}
          onClick={() => setExpandedId(expandedId === note.id ? null : note.id)}
        >
          <div style={{ fontWeight: 600, fontSize: 11 }}>
            {note.course_id} / {note.chapter}
          </div>
          <div style={{ opacity: 0.6, fontSize: 11, marginTop: 2 }}>
            {expandedId === note.id
              ? note.content
              : note.content.slice(0, 80) + (note.content.length > 80 ? '...' : '')}
          </div>
          {note.tags.length > 0 && (
            <div style={{ opacity: 0.4, fontSize: 10, marginTop: 4 }}>
              {note.tags.join(', ')}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
