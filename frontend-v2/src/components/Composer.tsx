import { useEffect, useRef, useState } from 'react'
import { useAppStore } from '../state/useAppStore'

interface Persona {
  id: string
  name: string
  role: string
  tone: string
  instructions: string
  allowed_toolboxes: string[]
}

interface ComposerProps {
  onSend: (content: string) => void
  disabled?: boolean
  compact?: boolean
  hitlBlocked?: boolean
}

export function Composer({ onSend, disabled, compact, hitlBlocked }: ComposerProps) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  
  // Persona selection states
  const activePersonaId = useAppStore((s) => s.activePersonaId)
  const setActivePersonaId = useAppStore((s) => s.setActivePersonaId)
  const [personas, setPersonas] = useState<Persona[]>([])
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Fetch personas on mount
  useEffect(() => {
    let disposed = false
    const fetchPersonas = async () => {
      try {
        const res = await fetch('/api/personas')
        if (res.ok) {
          const data = await res.json()
          if (!disposed && Array.isArray(data)) {
            setPersonas(data)
          }
        }
      } catch (err) {
        console.error('Failed to fetch personas', err)
      }
    }
    void fetchPersonas()
    return () => {
      disposed = true
    }
  }, [])

  // Auto-close dropdown on click outside
  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleOutsideClick)
    return () => {
      document.removeEventListener('mousedown', handleOutsideClick)
    }
  }, [])

  // Auto-resize textarea dynamically based on viewport
  useEffect(() => {
    const el = textareaRef.current
    if (el) {
      el.style.height = 'auto'
      const maxH = compact ? 80 : Math.round(window.innerHeight * 0.4)
      el.style.height = Math.min(el.scrollHeight, maxH) + 'px'
    }
  }, [value, compact])

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (disabled) return
    const content = value.trim()
    if (!content) return
    onSend(content)
    setValue('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Shift+Enter inserts a newline; plain Enter sends
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      const form = (e.target as HTMLTextAreaElement).closest('form')
      if (form) form.requestSubmit()
    }
  }

  // Find active persona metadata or provide elegant default
  const activePersona = personas.find((p) => p.id === activePersonaId) || {
    id: 'default',
    name: 'Owlynn',
    role: 'General Workspace Assistant',
    instructions: 'Help the user with coding, research, and data analysis tasks.',
  }

  const getPersonaIcon = (id: string) => {
    switch (id) {
      case 'coder':
        return '💻'
      case 'writer':
        return '✍️'
      case 'researcher':
        return '🔍'
      default:
        return '🤖'
    }
  }

  return (
    <div className={`composer-wrapper${compact ? ' composer-wrapper-compact' : ''}`}>
      {/* Dynamic Persona Selection Pill & Dropdown */}
      <div className="persona-selector-container" ref={dropdownRef}>
        <button
          type="button"
          className={`persona-pill ${dropdownOpen ? 'persona-pill-open' : ''}`}
          onClick={() => setDropdownOpen(!dropdownOpen)}
          disabled={disabled || hitlBlocked}
        >
          <span className="persona-pill-icon">{getPersonaIcon(activePersona.id)}</span>
          <span className="persona-pill-name">{activePersona.name}</span>
          <span className="persona-pill-role">{activePersona.role}</span>
          <span className="persona-pill-arrow">{dropdownOpen ? '▲' : '▼'}</span>
        </button>

        {dropdownOpen && personas.length > 0 && (
          <div className="persona-dropdown">
            <div className="persona-dropdown-header">Choose Assistant Persona</div>
            <div className="persona-dropdown-list">
              {personas.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className={`persona-card ${p.id === activePersonaId ? 'persona-card-active' : ''}`}
                  onClick={() => {
                    setActivePersonaId(p.id)
                    setDropdownOpen(false)
                  }}
                >
                  <div className="persona-card-header">
                    <span className="persona-card-icon">{getPersonaIcon(p.id)}</span>
                    <span className="persona-card-name">{p.name}</span>
                  </div>
                  <div className="persona-card-role">{p.role}</div>
                  <div className="persona-card-desc">{p.instructions}</div>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <form className="composer" onSubmit={handleSubmit}>
        <div className="composer-input-wrap">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              hitlBlocked
                ? 'Approve or decline the action above to continue'
                : compact
                  ? 'Ask...'
                  : `Ask ${activePersona.name}...`
            }
            rows={1}
            disabled={disabled || hitlBlocked}
          />
        </div>
        <button
          type="submit"
          className="composer-send"
          disabled={disabled || !value.trim()}
          title="Send (Enter)"
        >
          ↑
        </button>
      </form>
    </div>
  )
}
