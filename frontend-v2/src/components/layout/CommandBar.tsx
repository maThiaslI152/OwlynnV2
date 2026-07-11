import { useState, useRef } from 'react'

interface CommandBarProps {
  onSend?: (content: string) => void
  onStop?: () => void
  isGenerating?: boolean
}

export function CommandBar({ onSend, onStop, isGenerating }: CommandBarProps) {
  const [input, setInput] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const handleSend = () => {
    const text = input.trim()
    if (!text || !onSend) return
    onSend(text)
    setInput('')
    inputRef.current?.focus()
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="pd-command-bar">
      <input
        ref={inputRef}
        className="pd-command-input"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Command the agent... (e.g., 'run nmap -sV 10.0.0.1' or 'create a finding for SQL injection')"
      />
      {isGenerating && onStop ? (
        <button
          type="button"
          onClick={onStop}
          className="pd-command-stop"
          style={{
            background: 'rgba(233,69,96,0.2)',
            color: '#e94560',
            border: '1px solid rgba(233,69,96,0.3)',
            borderRadius: 6,
            padding: '0 16px',
            fontSize: 13,
            fontWeight: 500,
            cursor: 'pointer',
            marginLeft: 8,
          }}
        >
          ■ Stop
        </button>
      ) : null}
      <button
        type="button"
        className="pd-command-send"
        onClick={handleSend}
        disabled={!input.trim() || isGenerating}
        style={isGenerating ? { marginLeft: 8 } : {}}
      >
        Send
      </button>
    </div>
  )
}
