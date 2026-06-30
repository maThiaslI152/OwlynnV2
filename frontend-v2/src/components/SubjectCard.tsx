import { motion } from 'framer-motion'
import type { WorkspaceProject } from './AppShell'

interface SubjectCardProps {
  subject: WorkspaceProject
  isActive: boolean
  onClick: () => void
}

export function SubjectCard({ subject, isActive, onClick }: SubjectCardProps) {
  return (
    <motion.div
      className={`glass-card subject-card ${isActive ? 'active' : ''}`}
      onClick={onClick}
      whileHover={{ y: -4, scale: 1.01 }}
      whileTap={{ scale: 0.98 }}
      style={{
        padding: '24px',
        cursor: 'pointer',
        border: isActive ? '2px solid var(--accent)' : '1px solid var(--border-subtle)',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        minHeight: '200px',
        position: 'relative',
        overflow: 'hidden'
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
          background: 'var(--accent)',
          filter: 'blur(60px)',
          opacity: 0.2,
          borderRadius: '50%',
          pointerEvents: 'none'
        }}
      />

      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
          <h3 style={{ fontSize: '20px', fontWeight: '600', margin: 0, color: 'var(--text-primary)' }}>
            {subject.name}
          </h3>
          <div style={{ padding: '4px 8px', borderRadius: '12px', background: 'var(--bg-subtle)', fontSize: '12px', color: 'var(--text-secondary)' }}>
            {subject.chats?.length || 0} Chats
          </div>
        </div>
        <p style={{ fontSize: '14px', color: 'var(--text-secondary)', lineHeight: 1.5, display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
          {'No description available for this notebook.'}
        </p>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '24px' }}>
        <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
        </div>
        <button
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--accent)',
            cursor: 'pointer',
            fontSize: '14px',
            fontWeight: '500',
            padding: 0
          }}
        >
          Open &rarr;
        </button>
      </div>
    </motion.div>
  )
}
