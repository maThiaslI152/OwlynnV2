import { motion } from 'framer-motion'
import { useAppStore } from '../state/useAppStore'
import { SubjectCard } from './SubjectCard'
import type { WorkspaceProject } from './AppShell'

interface StudyDashboardProps {
  projects: WorkspaceProject[]
  activeProjectId: string | null
  onSwitchProject: (id: string) => void
  onCreateProject: (name: string) => void
}

export function StudyDashboard({ projects, activeProjectId, onSwitchProject, onCreateProject }: StudyDashboardProps) {
  const setStudyView = useAppStore((s) => s.setStudyView)
  
  // Filter for study-specific projects if needed, or all projects since we're in study mode
  const studySubjects = projects
  
  return (
    <div className="study-dashboard-container" style={{ padding: '40px', height: '100%', overflowY: 'auto' }}>
      <motion.div 
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
      >
        <h1 style={{ fontSize: '32px', fontWeight: '700', marginBottom: '8px', color: 'var(--text-primary)' }}>
          Welcome back to Study Mode
        </h1>
        <p style={{ fontSize: '16px', color: 'var(--text-secondary)', marginBottom: '40px' }}>
          Select a subject notebook to continue learning, or create a new one.
        </p>
      </motion.div>

      <motion.div 
        className="study-subjects-grid"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
          gap: '24px',
        }}
        initial="hidden"
        animate="visible"
        variants={{
          hidden: { opacity: 0 },
          visible: {
            opacity: 1,
            transition: { staggerChildren: 0.1 }
          }
        }}
      >
        <motion.div
          className="glass-card new-subject-card"
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: '200px',
            cursor: 'pointer',
            border: '2px dashed var(--border-subtle)',
            background: 'var(--bg-surface)'
          }}
          onClick={() => {
            const name = prompt("Enter new subject name:")
            if (name) {
               onCreateProject(name)
            }
          }}
        >
          <div style={{ fontSize: '48px', color: 'var(--accent)', marginBottom: '16px' }}>+</div>
          <div style={{ fontSize: '16px', fontWeight: '500', color: 'var(--text-secondary)' }}>New Notebook</div>
        </motion.div>

        {studySubjects.map(subject => (
          <SubjectCard 
            key={subject.id} 
            subject={subject as any} 
            isActive={subject.id === activeProjectId}
            onClick={() => {
              onSwitchProject(subject.id)
              setStudyView('notebook')
            }}
          />
        ))}
      </motion.div>
    </div>
  )
}
