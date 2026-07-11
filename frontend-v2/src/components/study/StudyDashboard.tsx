import { motion } from 'framer-motion'
import { useState, useEffect } from 'react'
import { useAppStore } from '../../state/useAppStore'
import { SubjectCard } from './SubjectCard'
import type { WorkspaceProject } from '../layout/AppShell'
import { Flame, Calendar, BookOpen, Clock, AlertCircle, Layers } from 'lucide-react'
import { DeckBrowserModal } from './DeckBrowserModal'
import toast from 'react-hot-toast'
import { StudyAPI } from '../../sdk'

interface StudyDashboardProps {
  projects: WorkspaceProject[]
  activeProjectId: string | null
  onSwitchProject: (id: string) => void
  onCreateProject: (name: string) => void
}

export function StudyDashboard({ projects, activeProjectId, onSwitchProject, onCreateProject }: StudyDashboardProps) {
  const setStudyView = useAppStore((s) => s.setStudyView)
  const [data, setData] = useState<any>(null)
  const [selectedDeck, setSelectedDeck] = useState<string | null>(null)
  
  useEffect(() => {
    StudyAPI.getDashboard()
      .then(json => {
         if (json.status === 'ok') setData(json)
      })
      .catch(err => console.error(err))
  }, [])
  
  // Filter for study-specific projects
  const studySubjects = projects.filter(p => p.mode === 'study')
  
  return (
    <div className="study-dashboard-container" style={{ padding: '40px', height: '100%', overflowY: 'auto' }}>
      {/* Hero Section */}
      <motion.div 
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        style={{
           background: 'linear-gradient(135deg, rgba(251, 146, 60, 0.1), rgba(16, 185, 129, 0.05))',
           borderRadius: '24px',
           padding: '32px',
           marginBottom: '40px',
           display: 'flex',
           justifyContent: 'space-between',
           alignItems: 'center',
           border: '1px solid rgba(255,255,255,0.05)',
           position: 'relative',
           overflow: 'hidden'
        }}
      >
        <div style={{ zIndex: 1 }}>
           <h1 style={{ fontSize: '32px', fontWeight: '700', marginBottom: '8px', color: 'var(--text-primary)' }}>
             Welcome back, Student
           </h1>
           <p style={{ fontSize: '16px', color: 'var(--text-secondary)' }}>
             You're on a roll! Keep up the great work.
           </p>
        </div>
        
        {data && data.study_streak && (
           <div style={{ display: 'flex', gap: '24px', zIndex: 1 }}>
              {data.upcoming_exams?.length > 0 && (
                 <div style={{ background: 'rgba(0,0,0,0.2)', padding: '16px 24px', borderRadius: '16px', border: '1px solid rgba(255,255,255,0.05)' }}>
                    <div style={{ color: 'var(--text-secondary)', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '4px' }}>Next Exam</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '20px', fontWeight: '600', color: 'var(--text-primary)' }}>
                       <Calendar size={20} color="#3b82f6" /> {data.upcoming_exams[0].days_until} Days
                    </div>
                    <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '4px' }}>{data.upcoming_exams[0].name}</div>
                 </div>
              )}
              <div style={{ background: 'rgba(251, 146, 60, 0.1)', padding: '16px 24px', borderRadius: '16px', border: '1px solid rgba(251, 146, 60, 0.2)' }}>
                 <div style={{ color: '#fb923c', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '4px' }}>Global Streak</div>
                 <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '24px', fontWeight: '700', color: '#fb923c' }}>
                    <Flame size={24} /> {data.study_streak.current}
                 </div>
                 <div style={{ fontSize: '13px', opacity: 0.8, color: '#fb923c', marginTop: '4px' }}>Best: {data.study_streak.longest}</div>
              </div>
           </div>
        )}
      </motion.div>

      {/* Main Content Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: '40px' }}>
         <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <h2 style={{ fontSize: '20px', fontWeight: '600', color: 'var(--text-primary)' }}>Your Subjects</h2>
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
                  } else {
                     toast("Tip: You can also ask Owlynn in chat to register a course!")
                  }
                }}
              >
                <div style={{ fontSize: '48px', color: 'var(--text-muted)', marginBottom: '16px' }}>+</div>
                <div style={{ fontSize: '16px', fontWeight: '500', color: 'var(--text-secondary)' }}>New Notebook / Course</div>
              </motion.div>

              {studySubjects.map(subject => {
                const progress = data?.course_progress?.find((p: any) => p.course_id === subject.name || p.project_id === subject.id)
                return (
                  <SubjectCard 
                    key={subject.id} 
                    subject={subject} 
                    progress={progress}
                    isActive={subject.id === activeProjectId}
                    onClick={() => {
                      onSwitchProject(subject.id)
                      setStudyView('notebook')
                    }}
                  />
                )
              })}
            </motion.div>
         </div>
         
         {/* Sidebar Tools / Tasks */}
         <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
            {data?.course_todos?.length > 0 && (
               <div>
                  <h2 style={{ fontSize: '18px', fontWeight: '600', color: 'var(--text-primary)', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                     <AlertCircle size={18} /> Needs Attention
                  </h2>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                     {data.course_todos.map((todo: any) => (
                        <div key={todo.id} style={{ background: 'var(--bg-surface)', padding: '16px', borderRadius: '12px', border: '1px solid var(--border-subtle)' }}>
                           <div style={{ fontSize: '14px', fontWeight: '500', color: 'var(--text-primary)' }}>{todo.task}</div>
                           <div style={{ display: 'flex', gap: '12px', marginTop: '12px', fontSize: '12px', color: 'var(--text-secondary)' }}>
                              {todo.due_date && <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><Clock size={12} /> {todo.due_date}</span>}
                              {todo.course_id && <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><BookOpen size={12} /> {todo.course_id}</span>}
                           </div>
                        </div>
                     ))}
                  </div>
               </div>
            )}
            
            {data?.flashcard_decks?.length > 0 && (
               <div>
                  <h2 style={{ fontSize: '18px', fontWeight: '600', color: 'var(--text-primary)', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                     <Layers size={18} /> Flashcard Decks
                  </h2>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                     {data.flashcard_decks.map((deck: any) => (
                        <div 
                           key={deck.deck_id} 
                           onClick={() => setSelectedDeck(deck.deck_id)}
                           style={{ 
                              background: 'var(--bg-surface)', 
                              padding: '16px', 
                              borderRadius: '12px', 
                              border: deck.due_cards > 0 ? '1px solid rgba(251, 146, 60, 0.3)' : '1px solid var(--border-subtle)',
                              cursor: 'pointer',
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center',
                              transition: 'all 0.2s'
                           }}
                           className="hover-brighten"
                        >
                           <div>
                              <div style={{ fontSize: '14px', fontWeight: '500', color: 'var(--text-primary)' }}>{deck.name}</div>
                              <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>{deck.card_count} total cards</div>
                           </div>
                           {deck.due_cards > 0 && (
                              <div style={{ background: 'rgba(251, 146, 60, 0.1)', color: '#fb923c', padding: '4px 8px', borderRadius: '12px', fontSize: '12px', fontWeight: '600' }}>
                                 {deck.due_cards} Due
                              </div>
                           )}
                        </div>
                     ))}
                  </div>
               </div>
            )}
         </div>
      </div>
      
      {selectedDeck && (
         <DeckBrowserModal deckId={selectedDeck} onClose={() => setSelectedDeck(null)} />
      )}
    </div>
  )
}
