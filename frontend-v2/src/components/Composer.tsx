import { useEffect, useRef, useState, useCallback } from 'react'
import { useAppStore } from '../state/useAppStore'
import {
  type AttachedFile,
  WORKSPACE_REF_DRAG_TYPE,
  isWorkspaceRef,
  workspaceRefAttachment,
} from '../lib/attachments'
import { buildPageContextDraft } from '../lib/browserPageContext'
import { electronBridge } from '../lib/electronBridge'
import { fetchWithAuth } from '../lib/localRunToken'
import toast from 'react-hot-toast'

interface Persona {
  id: string
  name: string
  role: string
  tone: string
  instructions: string
  allowed_toolboxes: string[]
}

function inferMimeType(name: string, fileType?: string): string {
  if (fileType) return fileType
  const lower = name.toLowerCase()
  if (lower.endsWith('.png')) return 'image/png'
  if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) return 'image/jpeg'
  if (lower.endsWith('.webp')) return 'image/webp'
  if (lower.endsWith('.gif')) return 'image/gif'
  return 'application/octet-stream'
}

function isImageAttachment(file: AttachedFile): boolean {
  return file.type.startsWith('image/')
}

interface ComposerProps {
  onSend: (content: string, files?: AttachedFile[]) => void
  onStop?: () => void
  disabled?: boolean
  isGenerating?: boolean
  compact?: boolean
  hitlBlocked?: boolean
  onRegisterWorkspaceAttach?: (attach: (file: AttachedFile) => void) => void
}

const MAX_FILE_SIZE = 20 * 1024 * 1024 // 20 MB

export function Composer({ onSend, onStop, disabled, isGenerating, compact, hitlBlocked, onRegisterWorkspaceAttach }: ComposerProps) {
  const [value, setValue] = useState('')
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([])
  const [isDragging, setIsDragging] = useState(false)
  const [isCapturing, setIsCapturing] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  
  // Persona selection states
  const activePersonaId = useAppStore((s) => s.activePersonaId)
  const setActivePersonaId = useAppStore((s) => s.setActivePersonaId)
  const browserPageContext = useAppStore((s) => s.browserPageContext)
  const browserPageContextNonce = useAppStore((s) => s.browserPageContextNonce)
  const screenAssistEnabled = useAppStore((s) => s.screenAssistEnabled)
  const setScreenAssistEnabled = useAppStore((s) => s.setScreenAssistEnabled)
  const [personas, setPersonas] = useState<Persona[]>([])
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Fetch personas on mount
  useEffect(() => {
    let disposed = false
    const fetchPersonas = async () => {
      try {
        const res = await fetchWithAuth('/api/personas')
        if (res.ok) {
          const data = await res.json()
          if (!disposed && Array.isArray(data)) {
            setPersonas(data)
          }
        }
      } catch (err) {
        console.error('Failed to fetch personas', err)
        toast.error('Failed to fetch personas')
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
      el.style.height = `${Math.min(el.scrollHeight, maxH)}px`
    }
  }, [value, compact])

  const attachWorkspaceFile = useCallback((file: AttachedFile) => {
    setAttachedFiles((prev) => {
      if (prev.some((f) => isWorkspaceRef(f) && f.name === file.name)) {
        return prev
      }
      return [...prev, file]
    })
  }, [])

  useEffect(() => {
    onRegisterWorkspaceAttach?.(attachWorkspaceFile)
  }, [onRegisterWorkspaceAttach, attachWorkspaceFile])

  useEffect(() => {
    if (!browserPageContextNonce || !browserPageContext) return
    const content = buildPageContextDraft(browserPageContext)
    onSend(content)
  }, [browserPageContextNonce, browserPageContext, onSend])

  const handleSubmit = async (event?: React.FormEvent<HTMLFormElement>) => {
    if (event) event.preventDefault()
    if (disabled || isCapturing) return
    const content = value.trim()
    
    // Allow sending just files without text, but if screenAssist is on, we'll have a file soon
    if (!content && attachedFiles.length === 0 && !screenAssistEnabled) return

    const finalFiles = [...attachedFiles]

    if (screenAssistEnabled) {
      setIsCapturing(true)
      try {
        const result = await electronBridge.startScreenPreview('screen')
        if (result.ok && result.data) {
          // Parse the path from the result string: "screen preview started: screen (/tmp/owlynn-preview-screen-xxxx.jpg)"
          const match = result.data.match(/\((.*?)\)/)
          if (match) {
            const previewPath = match[1]
            const response = await fetch(electronBridge.convertFileSrc(previewPath))
            const blob = await response.blob()
            const dataUrl = await new Promise<string>((res, rej) => {
              const reader = new FileReader()
              reader.onload = () => res(reader.result as string)
              reader.onerror = rej
              reader.readAsDataURL(blob)
            })
            
            finalFiles.push({
              name: `Screen Capture - ${new Date().toLocaleTimeString()}.jpg`,
              type: 'image/jpeg',
              data: dataUrl,
            })
          }
        } else {
          toast.error(`Screen capture failed: ${result.error}`)
        }
      } catch (err) {
        toast.error(`Failed to capture screen: ${err}`)
      } finally {
        setIsCapturing(false)
      }
    }

    if (!content && finalFiles.length === 0) {
      return // If capture failed and no text, don't send
    }

    onSend(content, finalFiles.length > 0 ? finalFiles : undefined)
    setValue('')
    setAttachedFiles([])
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Shift+Enter inserts a newline; plain Enter sends
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    if (!disabled && !hitlBlocked) {
      setIsDragging(true)
    }
  }, [disabled, hitlBlocked])

  const handleDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleDrop = useCallback(async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)
    if (disabled || hitlBlocked) return

    const wsRefRaw = e.dataTransfer.getData(WORKSPACE_REF_DRAG_TYPE)
    if (wsRefRaw) {
      try {
        const parsed = JSON.parse(wsRefRaw) as { name?: string }
        const refName = parsed.name
        if (refName) {
          setAttachedFiles((prev) => {
            const next = workspaceRefAttachment(refName)
            if (prev.some((f) => isWorkspaceRef(f) && f.name === next.name)) {
              return prev
            }
            return [...prev, next]
          })
        }
      } catch {
        // ignore malformed drag payload
      }
      return
    }

    const files = Array.from(e.dataTransfer.files)
    const validFiles: AttachedFile[] = []

    for (const file of files) {
      if (file.size > MAX_FILE_SIZE) {
        alert(`File ${file.name} exceeds the 20MB size limit.`)
        continue
      }
      // Block common executable extensions just in case
      if (file.name.match(/\.(exe|dmg|zip|tar|gz|dll|so|dylib)$/i)) {
        alert(`File type not allowed: ${file.name}`)
        continue
      }

      const reader = new FileReader()
      const dataUrl = await new Promise<string>((resolve, reject) => {
        reader.onload = () => resolve(reader.result as string)
        reader.onerror = reject
        reader.readAsDataURL(file)
      })

      validFiles.push({
        name: file.name,
        type: inferMimeType(file.name, file.type),
        data: dataUrl,
      })
    }

    if (validFiles.length > 0) {
      setAttachedFiles((prev) => [...prev, ...validFiles])
    }
  }, [disabled, hitlBlocked])

  const removeFile = (index: number) => {
    setAttachedFiles((prev) => {
      const copy = [...prev]
      copy.splice(index, 1)
      return copy
    })
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
    <div 
      className={`composer-wrapper${compact ? ' composer-wrapper-compact' : ''} ${isDragging ? 'drag-over' : ''}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
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
        {attachedFiles.length > 0 && (
          <div className="composer-attachments">
            {attachedFiles.map((file, idx) => (
              <div
                key={`${file.type}-${file.name}-${idx}`}
                className={`attachment-chip${
                  isImageAttachment(file) ? ' attachment-chip-image' : ''
                }${isWorkspaceRef(file) ? ' attachment-chip-workspace' : ''}`}
              >
                {isWorkspaceRef(file) ? (
                  <span className="attachment-workspace-icon" title="Workspace reference">
                    📎
                  </span>
                ) : isImageAttachment(file) ? (
                  <img
                    className="attachment-thumb"
                    src={file.data}
                    alt={file.name}
                    title={file.name}
                  />
                ) : null}
                <span className="attachment-name" title={file.name}>{file.name}</span>
                <button 
                  type="button" 
                  className="attachment-remove" 
                  onClick={() => removeFile(idx)}
                  title="Remove file"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="composer-input-row">
          <button
            type="button"
            className={`composer-screen-assist ${screenAssistEnabled ? 'active' : ''}`}
            onClick={() => setScreenAssistEnabled(!screenAssistEnabled)}
            title={screenAssistEnabled ? "Screen Assist: ON (Auto-capture on send)" : "Turn on Screen Assist"}
            disabled={disabled || hitlBlocked}
          >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
              <circle cx="12" cy="12" r="3" />
            </svg>
          </button>
          <div className="composer-input-wrap">
            <textarea
              ref={textareaRef}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                hitlBlocked
                  ? 'Approve or decline the action above to continue'
                  : isDragging
                    ? 'Drop files or workspace references here...'
                    : isCapturing
                      ? 'Capturing screen...'
                      : compact
                        ? 'Ask...'
                        : `Ask ${activePersona.name}...`
              }
              rows={1}
              disabled={disabled || hitlBlocked || isCapturing}
            />
          </div>
          {isGenerating ? (
            <button
              type="button"
              className="composer-send composer-stop"
              onClick={onStop}
              title="Stop generation"
              style={{ backgroundColor: 'var(--red-500)', color: 'white', opacity: 1, cursor: 'pointer' }}
            >
              ■
            </button>
          ) : (
            <button
              type="submit"
              className="composer-send"
              disabled={disabled || (!value.trim() && attachedFiles.length === 0)}
              title="Send (Enter)"
            >
              ↑
            </button>
          )}
        </div>
      </form>
    </div>
  )
}
