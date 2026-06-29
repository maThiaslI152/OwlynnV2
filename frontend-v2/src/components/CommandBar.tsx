import { useState, useRef } from 'react'

interface CommandBarProps {
  onSend?: (content: string) => void
}

export function CommandBar({ onSend }: CommandBarProps) {
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
      <button
        type="button"
        className="pd-command-send"
        onClick={handleSend}
        disabled={!input.trim()}
      >
        Send
      </button>
    </div>
  )
}
