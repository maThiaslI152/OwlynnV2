import { useCallback, useEffect, useState } from 'react'
import toast from 'react-hot-toast'

interface Course {
  course_id: string
  name: string
  exam_date?: string | null
  linked_files?: string[]
}

interface ExamRow {
  course_id: string
  name: string
  exam_date: string
  days_until: number
}

interface CourseTodo {
  id: number
  task: string
  course_id?: string | null
  due_date?: string | null
  priority?: string
}

interface DeckRow {
  deck_id: string
  name: string
  course_id?: string | null
  card_count: number
}

interface Dashboard {
  courses: Course[]
  upcoming_exams: ExamRow[]
  course_todos: CourseTodo[]
  flashcard_decks: DeckRow[]
}

export function StudyPanel() {
  const [data, setData] = useState<Dashboard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await fetch('/api/study/dashboard')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json = await res.json()
      if (json.status === 'ok') {
        setData(json)
      } else {
        setError(json.message || 'Failed to load study dashboard')
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to load'
      setError(msg)
      toast.error(`Study Panel: ${msg}`)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  if (loading) return <p className="panel-muted">Loading study dashboard…</p>
  if (error) return <p className="panel-error">{error}</p>
  if (!data) return null

  return (
    <div className="study-panel">
      <div className="study-panel-header">
        <strong>Study</strong>
        <button type="button" className="topbar-btn" onClick={() => void load()} title="Refresh">
          ↻
        </button>
      </div>

      <section className="study-section">
        <h4>Courses</h4>
        {data.courses.length === 0 ? (
          <p className="panel-muted">No courses yet — ask Owlynn to register one.</p>
        ) : (
          <ul className="study-list">
            {data.courses.map((c) => (
              <li key={c.course_id}>
                <span className="study-course-id">{c.course_id}</span> {c.name}
                {c.exam_date ? ` · exam ${c.exam_date}` : ''}
              </li>
            ))}
          </ul>
        )}
      </section>

      {data.upcoming_exams.length > 0 && (
        <section className="study-section">
          <h4>Upcoming exams</h4>
          <ul className="study-list">
            {data.upcoming_exams.map((e) => (
              <li key={e.course_id}>
                {e.name} — {e.days_until}d ({e.exam_date})
              </li>
            ))}
          </ul>
        </section>
      )}

      {data.course_todos.length > 0 && (
        <section className="study-section">
          <h4>Course tasks</h4>
          <ul className="study-list">
            {data.course_todos.map((t) => (
              <li key={t.id}>
                #{t.id} {t.task}
                {t.due_date ? ` · due ${t.due_date}` : ''}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="study-section">
        <h4>Flashcard decks</h4>
        {data.flashcard_decks.length === 0 ? (
          <p className="panel-muted">No decks — ask to build flashcards from a chapter.</p>
        ) : (
          <ul className="study-list">
            {data.flashcard_decks.map((d) => (
              <li key={d.deck_id}>
                {d.name} ({d.card_count} cards)
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
