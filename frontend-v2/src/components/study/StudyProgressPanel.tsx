import { useState, useEffect } from 'react'
import toast from 'react-hot-toast'
import { Flame, Layers, BarChart2, Circle, Calendar } from 'lucide-react'

interface StudyDashboard {
  study_streak?: { current: number; longest: number; last_active: string | null }
  course_progress?: Array<{
    course_id: string
    current_streak: number
    total_cards: number
    due_cards: number
    avg_score: number
    last_studied: string | null
  }>
  upcoming_exams?: Array<{ course_id: string; name: string; days_until: number }>
}

export function StudyProgressPanel() {
  const [data, setData] = useState<StudyDashboard | null>(null)

  useEffect(() => {
    fetch('/api/study/dashboard')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d?.status === 'ok') setData(d)
      })
      .catch((err) => {
        toast.error('Failed to load study progress')
        console.error('[StudyProgressPanel]', err)
      })
  }, [])

  if (!data) return null

  const streak = data.study_streak

  return (
    <div style={{ padding: '8px 10px', fontSize: 12 }}>
      {/* Global streak */}
      {streak && streak.current > 0 && (
        <div
          style={{
            background: 'rgba(255,165,0,0.08)',
            borderRadius: 8,
            padding: 10,
            marginBottom: 10,
            border: '1px solid rgba(255,165,0,0.15)',
          }}
        >
          <div style={{ fontSize: 18, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Flame size={20} color="#fb923c" /> {streak.current} day streak
          </div>
          <div style={{ fontSize: 11, opacity: 0.5, marginTop: 2 }}>Best: {streak.longest} days</div>
        </div>
      )}

      {/* Per-course progress */}
      {(data.course_progress || []).map((cp) => (
        <div
          key={cp.course_id}
          style={{
            padding: '6px 8px',
            marginBottom: 6,
            borderRadius: 6,
            background: 'rgba(255,255,255,0.03)',
            border: '1px solid rgba(255,255,255,0.05)',
          }}
        >
          <div style={{ fontWeight: 600, fontSize: 11 }}>{cp.course_id}</div>
          <div
            style={{
              display: 'flex',
              gap: 8,
              flexWrap: 'wrap',
              marginTop: 3,
              opacity: 0.6,
              fontSize: 11,
            }}
          >
            {cp.current_streak > 0 && <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}><Flame size={12} color="#fb923c" /> {cp.current_streak}d</span>}
            {cp.total_cards > 0 && (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                <Layers size={12} /> {cp.due_cards}/{cp.total_cards}
              </span>
            )}
            {cp.avg_score > 0 && <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}><BarChart2 size={12} /> {Math.round(cp.avg_score * 100)}%</span>}
          </div>
        </div>
      ))}

      {/* Upcoming exams */}
      {(data.upcoming_exams || []).length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div
            style={{
              fontWeight: 600,
              fontSize: 11,
              textTransform: 'uppercase',
              opacity: 0.5,
              marginBottom: 6,
            }}
          >
            Upcoming Exams
          </div>
          {data.upcoming_exams!.map((e) => (
            <div key={e.course_id} style={{ fontSize: 11, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
              {e.days_until <= 0 ? <Circle fill="currentColor" size={12} color="#ef4444" /> : <Calendar size={12} />} {e.name} — {e.days_until}d
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
