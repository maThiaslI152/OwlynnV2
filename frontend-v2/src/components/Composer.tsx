import { useEffect, useRef, useState } from 'react'

interface ComposerProps {
  onSend: (content: string) => void
  disabled?: boolean
  compact?: boolean
}

export function Composer({ onSend, disabled, compact }: ComposerProps) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

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

  return (
    <div className={`composer-wrapper${compact ? ' composer-wrapper-compact' : ''}`}>
      <form className="composer" onSubmit={handleSubmit}>
        <div className="composer-input-wrap">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={compact ? "Ask..." : "Ask Owlynn..."}
            rows={1}
            disabled={disabled}
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
