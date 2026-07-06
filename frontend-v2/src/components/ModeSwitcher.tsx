import { MessageSquare, BookOpen, ShieldAlert } from 'lucide-react'

interface ModeSwitcherProps {
  activeMode: 'normal' | 'study' | 'pentest'
  onModeChange: (mode: 'normal' | 'study' | 'pentest') => void
}

const modes = [
  { id: 'normal' as const, label: 'Normal', icon: <MessageSquare size={14} /> },
  { id: 'study' as const, label: 'Study', icon: <BookOpen size={14} /> },
  { id: 'pentest' as const, label: 'Pentest', icon: <ShieldAlert size={14} /> },
]

export function ModeSwitcher({ activeMode, onModeChange }: ModeSwitcherProps) {
  return (
    <div
      style={{
        display: 'flex',
        gap: 2,
        background: 'rgba(255,255,255,0.04)',
        borderRadius: 8,
        padding: 3,
        border: '1px solid rgba(255,255,255,0.06)',
        width: '100%',
        boxSizing: 'border-box',
      }}
    >
      {modes.map((m) => (
        <button
          key={m.id}
          type="button"
          onClick={() => onModeChange(m.id)}
          style={{
            flex: 1,
            display: 'flex',
            justifyContent: 'center',
            padding: '4px 0',
            borderRadius: 6,
            fontSize: 12,
            fontWeight: 500,
            border: 'none',
            cursor: 'pointer',
            transition: 'all 0.15s',
            background: activeMode === m.id ? 'rgba(233,69,96,0.2)' : 'transparent',
            color: activeMode === m.id ? '#e94560' : 'rgba(255,255,255,0.5)',
          }}
        >
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            {m.icon} <span style={{ paddingBottom: 1 }}>{m.label}</span>
          </span>
        </button>
      ))}
    </div>
  )
}
