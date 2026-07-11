import { motion } from 'framer-motion'
import { Flame, Layers, BarChart2, Clock } from 'lucide-react'
import type { WorkspaceProject } from '../layout/AppShell'

interface CourseProgress {
  course_id: string
  knowledge_files: number
  flashcard_decks: number
  total_cards: number
  due_cards: number
  quiz_sessions: number
  avg_score: number
  current_streak: number
  longest_streak: number
  last_studied: string | null
}

interface SubjectCardProps {
  subject: WorkspaceProject
  isActive: boolean
  progress?: CourseProgress
  onClick: () => void
}

export function SubjectCard({ subject, isActive, progress, onClick }: SubjectCardProps) {
  const hasDueCards = progress && progress.due_cards > 0
  const mastery = progress && progress.avg_score > 0 ? Math.round(progress.avg_score * 100) : null
  const streak = progress?.current_streak || 0
  
  // Format last studied
  let lastStudiedText = 'Never studied'
  if (progress?.last_studied) {
     const date = new Date(progress.last_studied)
     lastStudiedText = date.toLocaleDateString([], { month: 'short', day: 'numeric' })
  }

  return (
    <motion.div
      className={`glass-card subject-card ${isActive ? 'active' : ''}`}
      onClick={onClick}
      whileHover={{ y: -4, scale: 1.01 }}
      whileTap={{ scale: 0.98 }}
      style={{
        padding: '24px',
        cursor: 'pointer',
        border: isActive ? '2px solid var(--accent)' : hasDueCards ? '1px solid rgba(251, 146, 60, 0.5)' : '1px solid var(--border-subtle)',
        boxShadow: hasDueCards ? '0 0 15px rgba(251, 146, 60, 0.1)' : 'none',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        minHeight: '200px',
        position: 'relative',
        overflow: 'hidden',
        background: 'var(--bg-surface)'
      }}
    >
      {/* Decorative gradient blob in the background of the card */}
      <div 
        style={{
          position: 'absolute',
          top: '-50px',
          right: '-50px',
          width: '150px',
          height: '150px',
          background: hasDueCards ? '#fb923c' : 'var(--accent)',
          filter: 'blur(60px)',
          opacity: 0.15,
          borderRadius: '50%',
          pointerEvents: 'none'
        }}
      />

      <div style={{ position: 'relative', zIndex: 1 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
          <h3 style={{ fontSize: '20px', fontWeight: '600', margin: 0, color: 'var(--text-primary)' }}>
            {subject.name}
          </h3>
          <div style={{ display: 'flex', gap: '8px' }}>
            {streak > 0 && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px', padding: '4px 8px', borderRadius: '12px', background: 'rgba(251, 146, 60, 0.1)', color: '#fb923c', fontSize: '12px', fontWeight: '600' }}>
                <Flame size={14} /> {streak}
              </div>
            )}
            <div style={{ padding: '4px 8px', borderRadius: '12px', background: 'var(--bg-subtle)', fontSize: '12px', color: 'var(--text-secondary)' }}>
              {subject.chats?.length || 0} Chats
            </div>
          </div>
        </div>
        
        {progress ? (
           <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: hasDueCards ? '#fb923c' : 'var(--text-secondary)', fontSize: '14px', fontWeight: hasDueCards ? '500' : 'normal' }}>
                <Layers size={16} /> 
                {progress.due_cards > 0 ? `${progress.due_cards} cards due for review` : `${progress.total_cards} total flashcards`}
              </div>
              {mastery !== null && (
                 <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-secondary)', fontSize: '14px' }}>
                   <BarChart2 size={16} color="#10b981" /> 
                   <span>Mastery Score: <strong style={{ color: '#10b981' }}>{mastery}%</strong></span>
                 </div>
              )}
           </div>
        ) : (
           <p style={{ fontSize: '14px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
             Start studying to see progress metrics.
           </p>
        )}
      </div>

      <div style={{ position: 'relative', zIndex: 1, display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '24px' }}>
        <div style={{ fontSize: '12px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
           <Clock size={12} /> {lastStudiedText}
        </div>
        <button
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--accent)',
            cursor: 'pointer',
            fontSize: '14px',
            fontWeight: '500',
            padding: 0,
            display: 'flex',
            alignItems: 'center',
            gap: '4px'
          }}
        >
          Open &rarr;
        </button>
      </div>
    </motion.div>
  )
}
