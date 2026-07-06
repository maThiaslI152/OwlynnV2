import { useState, useEffect } from 'react'
import toast from 'react-hot-toast'
import { BarChart2 } from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
} from 'recharts'

interface AnalyticsData {
  score_trend: Record<string, Array<{ date: string; score: number }>>
  topic_mastery: Array<{ topic: string; mastery: number; struggles: number }>
  study_time: { total_minutes: number; by_course: Record<string, number> }
  sessions_by_type: Record<string, number>
  total_sessions: number
}

export function StudyAnalytics() {
  const [data, setData] = useState<AnalyticsData | null>(null)

  useEffect(() => {
    fetch('/api/study/analytics')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d?.status === 'ok') setData(d)
      })
      .catch((err) => {
        toast.error('Failed to load study analytics')
        console.error('[StudyAnalytics]', err)
      })
  }, [])

  if (!data) return null

  // Prepare score trend data (merge all courses)
  const trendData = Object.entries(data.score_trend).flatMap(([course, scores]) =>
    scores.map((s) => ({ date: s.date, [course]: s.score }))
  )
  // Merge by date
  const mergedTrend = trendData.reduce((acc, item) => {
    const existing = acc.find((a) => a.date === item.date)
    if (existing) {
      Object.assign(existing, item)
    } else {
      acc.push(item)
    }
    return acc
  }, [] as Array<Record<string, string | number>>)

  // Prepare radar data
  const radarData = data.topic_mastery.map((t) => ({
    topic: t.topic.length > 15 ? t.topic.slice(0, 15) + '…' : t.topic,
    mastery: t.mastery,
  }))

  const courseColors = ['#8884d8', '#82ca9d', '#ffc658', '#ff7300', '#0088fe']

  return (
    <div style={{ padding: '8px 10px', fontSize: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600, fontSize: 13, marginBottom: 12 }}><BarChart2 size={16} /> Study Analytics</div>

      {/* Summary stats */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 700 }}>{data.total_sessions}</div>
          <div style={{ opacity: 0.6 }}>Sessions</div>
        </div>
        <div>
          <div style={{ fontSize: 18, fontWeight: 700 }}>
            {Math.round(data.study_time.total_minutes / 60)}h
          </div>
          <div style={{ opacity: 0.6 }}>Study Time</div>
        </div>
      </div>

      {/* Score Trend Chart */}
      {mergedTrend.length > 1 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 600, fontSize: 11, marginBottom: 8, opacity: 0.7 }}>
            SCORE TREND
          </div>
          <ResponsiveContainer width="100%" height={150}>
            <LineChart data={mergedTrend}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
              <XAxis dataKey="date" tick={{ fontSize: 10 }} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} />
              <Tooltip />
              {Object.keys(data.score_trend).map((course, i) => (
                <Line
                  key={course}
                  type="monotone"
                  dataKey={course}
                  stroke={courseColors[i % courseColors.length]}
                  strokeWidth={2}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Topic Mastery Radar */}
      {radarData.length > 2 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 600, fontSize: 11, marginBottom: 8, opacity: 0.7 }}>
            TOPIC MASTERY
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <RadarChart data={radarData}>
              <PolarGrid stroke="rgba(255,255,255,0.1)" />
              <PolarAngleAxis dataKey="topic" tick={{ fontSize: 10 }} />
              <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fontSize: 10 }} />
              <Radar
                name="Mastery"
                dataKey="mastery"
                stroke="#8884d8"
                fill="#8884d8"
                fillOpacity={0.3}
              />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Sessions by type */}
      {Object.keys(data.sessions_by_type).length > 0 && (
        <div>
          <div style={{ fontWeight: 600, fontSize: 11, marginBottom: 8, opacity: 0.7 }}>
            SESSION TYPES
          </div>
          {Object.entries(data.sessions_by_type).map(([type, count]) => (
            <div key={type} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <span style={{ opacity: 0.7 }}>{type}</span>
              <span>{count}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
