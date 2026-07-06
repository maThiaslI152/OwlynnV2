import { useEffect, useRef, useState, useCallback, type ReactNode } from 'react'
import toast from 'react-hot-toast'
// @ts-expect-error - vitest requires the default import to resolve named exports correctly
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize'
import type { Options } from 'rehype-sanitize'
import { Composer } from './Composer'
import { ProjectKnowledgePanel } from './ProjectKnowledgePanel'
import { MacMenuBar } from './MacMenuBar'
import { HitlPromptCard, type HitlPromptViewModel } from './HitlPromptCard'
import { ToolActivityCard } from './ToolActivityCard'
import { ModeSwitcher } from './ModeSwitcher'
import { PentestToolsPanel } from './PentestToolsPanel'
import { StudyDashboard } from './StudyDashboard'
import { motion } from 'framer-motion'
import { ModeSwitchConfirmation, PentestLoadingOverlay } from './ModeSwitchModal'
import { StudyProgressPanel } from './StudyProgressPanel'
import { StudyNotesSearch } from './StudyNotesSearch'
import { PentestDashboard } from './PentestDashboard'
import { EngagementSelector } from './EngagementSelector'
import { PentestScopePanel } from './PentestScopePanel'
import { PhaseTracker } from './PhaseTracker'
import { QuickStats } from './QuickStats'
import type { InterruptChoice } from '../state/useAppStore'
import type { ConversationItem, ConversationToolActivity, ConversationHitlPrompt, ConversationChartEmbed } from '../appEventHandlers'
import { useAppStore } from '../state/useAppStore'
import { electronBridge as tauriBridge } from '../lib/electronBridge'
import type { ChatMessage } from '../types/protocol'
import type { AttachedFile } from '../lib/attachments'
import { isTauriRuntime } from '../lib/runtime'
import {
  isInteractiveChartUrl,
  isWorkspaceImageUrl,
  resolveWorkspaceFileUrl,
  rewriteWorkspaceImageMarkdown,
} from '../lib/workspaceImageUrl'
import { ChatImageViewer } from './ChatImageViewer'
import { ChatInteractiveChart } from './ChatInteractiveChart'
import {
  parseInteractiveBlocks,
  InteractiveBlockRenderer,
  renderMarkdownSegment,
} from '../lib/interactiveBlocks'
import { fetchWithAuth } from '../lib/localRunToken'

interface ProjectChat {
  id: string
  name: string
  created_at: number
  pinned?: boolean
  tags?: string[]
}

export interface WorkspaceProject {
  id: string
  name: string
  chats?: ProjectChat[]
  mode?: 'normal' | 'study' | 'pentest'
}

interface ExamCountdownItem {
  course_id: string
  name: string
  exam_date: string
  days_until: number
  pending_todos: number
  current_streak: number
  flashcard_decks: number
  total_cards: number
  due_cards: number
  project_id?: string
}

interface AppShellProps {
  onSend: (content: string, files?: AttachedFile[]) => void
  projects: WorkspaceProject[]
  activeProjectId: string
  activeChatId: string
  currentThreadId: string
  onSwitchProject: (projectId: string) => void
  onRefreshProjects: () => void
  onCreateProject: (name: string) => void
  onEditProject: (projectId: string, name: string) => void
  onDeleteProject: (projectId: string) => void
  onNewChat: () => void
  onSelectChat: (chatId: string) => void
  onDeleteChat: (chatId: string) => void
  onRenameChat: (chatId: string, newName: string) => void
  examCountdown?: ExamCountdownItem[]
  activeMode?: 'normal' | 'study' | 'pentest'
  onModeChange?: (mode: 'normal' | 'study' | 'pentest') => void
  /** Inline HITL card callbacks */
  onHitlApprove?: (hitlId: string, variant: string, answers?: Record<string, unknown>) => void
  onHitlDecline?: (hitlId: string) => void
  onHitlSelectChoice?: (choice: InterruptChoice, userInput?: string) => void
  onHitlSkip?: (hitlId: string) => void
  onStop?: () => void
}

function MessageAvatar({ role }: { role: ChatMessage['role'] }) {
  if (role === 'user') {
    return <div className="message-avatar">U</div>
  }
  return <div className="message-avatar">O</div>
}

// Extended sanitize schema: allows style attributes needed for Visual Comparison
// skill HTML output (side-by-side cards, styled containers) while blocking
// dangerous elements like <script> and event handlers.
const markdownSchema: Options = {
  ...defaultSchema,
  tagNames: [...(defaultSchema.tagNames || []), 'callout'],
  attributes: {
    ...defaultSchema.attributes,
    callout: ['variant'],
    div: [...(defaultSchema.attributes?.div || []), 'style', 'className'],
    span: [...(defaultSchema.attributes?.span || []), 'style'],
    strong: [...(defaultSchema.attributes?.strong || []), 'style'],
    th: [...(defaultSchema.attributes?.th || []), 'style', 'align'],
    td: [...(defaultSchema.attributes?.td || []), 'style', 'align'],
    table: [...(defaultSchema.attributes?.table || []), 'style'],
    img: [...(defaultSchema.attributes?.img || []), 'src', 'alt', 'title', 'loading'],
    code: ['className'],
    pre: ['className'],
    details: ['open', 'className'],
    summary: ['className'],
  },
}

function formatTimeRelative(ts: number): string {
  const now = Date.now()
  const diff = now - ts
  const seconds = Math.floor(diff / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)

  if (seconds < 60) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  if (hours < 24) return `${hours}h ago`
  if (days < 7) return `${days}d ago`
  return new Date(ts).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function buildMarkdownComponents(projectId: string) {
  return {
    a: ({ href, children, ...props }: { href?: string; children?: ReactNode }) => {
      const resolved = href ? resolveWorkspaceFileUrl(href, projectId) : href
      if (resolved && isInteractiveChartUrl(resolved)) {
        return (
          <ChatInteractiveChart
            src={resolved}
            title={typeof children === 'string' ? children : 'Interactive chart'}
          />
        )
      }
      if (resolved && isWorkspaceImageUrl(resolved)) {
        return (
          <ChatImageViewer
            src={resolved}
            alt={typeof children === 'string' ? children : 'Chart'}
          />
        )
      }
      return (
        <a
          className="msg-link"
          href={resolved}
          target="_blank"
          rel="noopener noreferrer"
          {...props}
        >
          {children}
        </a>
      )
    },
    img: ({ src, alt }: { src?: string; alt?: string }) => {
      const resolved = src ? resolveWorkspaceFileUrl(src, projectId) : ''
      if (resolved && isInteractiveChartUrl(resolved)) {
        return <ChatInteractiveChart src={resolved} title={alt || 'Interactive chart'} />
      }
      return <ChatImageViewer src={resolved} alt={alt || 'Chart'} />
    },
    pre: ({ children, ...props }: { children?: ReactNode }) => (
      <pre className="msg-code-block" {...props}>
        {children}
      </pre>
    ),
    code: ({ className, children, ...props }: { className?: string; children?: ReactNode }) => {
      const isInline = !className
      if (isInline) {
        return <code className="msg-inline-code" {...props}>{children}</code>
      }
      const lang = className?.replace('language-', '')
      return (
        <code className={className} {...props}>
          {lang && <span className="msg-code-lang">{lang}</span>}
          {children}
        </code>
      )
    },
    table: ({ children, ...props }: { children?: ReactNode }) => (
      <div className="msg-table-wrap">
        <table className="msg-table" {...props}>{children}</table>
      </div>
    ),
    th: ({ children, ...props }: { children?: ReactNode }) => (
      <th {...props}>{children}</th>
    ),
    td: ({ children, ...props }: { children?: ReactNode }) => (
      <td {...props}>{children}</td>
    ),
    details: ({ children, ...props }: { children?: ReactNode }) => (
      <details className="owlynn-block-details" {...props}>{children}</details>
    ),
    summary: ({ children, ...props }: { children?: ReactNode }) => (
      <summary className="owlynn-block-summary" {...props}>{children}</summary>
    ),
    h1: ({ children, ...props }: { children?: ReactNode }) => (
      <h1 className="msg-heading h1" {...props}>{children}</h1>
    ),
    h2: ({ children, ...props }: { children?: ReactNode }) => (
      <h2 className="msg-heading h2" {...props}>{children}</h2>
    ),
    h3: ({ children, ...props }: { children?: ReactNode }) => (
      <h3 className="msg-heading h3" {...props}>{children}</h3>
    ),
    h4: ({ children, ...props }: { children?: ReactNode }) => (
      <h4 className="msg-heading h4" {...props}>{children}</h4>
    ),
    h5: ({ children, ...props }: { children?: ReactNode }) => (
      <h5 className="msg-heading h5" {...props}>{children}</h5>
    ),
    h6: ({ children, ...props }: { children?: ReactNode }) => (
      <h6 className="msg-heading h6" {...props}>{children}</h6>
    ),
    ul: ({ children, ...props }: { children?: ReactNode }) => (
      <ul className="msg-list" {...props}>{children}</ul>
    ),
    ol: ({ children, ...props }: { children?: ReactNode }) => (
      <ol className="msg-list" {...props}>{children}</ol>
    ),
    callout: ({ variant, children, ...props }: any) => {
      // Use existing interactive callout styling if possible
      return (
        <div className={`owlynn-block owlynn-block-callout`} data-variant={variant} {...props}>
          {variant && <div className="callout-header">{variant.toUpperCase()}</div>}
          <div className="callout-body">{children}</div>
        </div>
      )
    },
  }
}

function MessageContent({
  content,
  projectId,
  threadId,
}: {
  content: string
  projectId: string
  threadId: string
}) {
  const cleaned = rewriteWorkspaceImageMarkdown(
    content.replace(/\n{3,}/g, '\n\n'),
    projectId,
  )
  const segments = parseInteractiveBlocks(cleaned)
  const markdownComponents = buildMarkdownComponents(projectId)

  if (segments.length === 1 && segments[0].type === 'markdown') {
    return renderMarkdownSegment(cleaned, markdownSchema, markdownComponents)
  }

  return (
    <>
      {segments.map((segment, idx) => {
        if (segment.type === 'markdown') {
          if (!segment.content.trim()) return null
          return (
            <div key={`md-${idx}`}>
              {renderMarkdownSegment(segment.content, markdownSchema, markdownComponents)}
            </div>
          )
        }
        return (
          <InteractiveBlockRenderer
            key={`block-${idx}`}
            segment={segment}
            projectId={projectId}
            threadId={threadId}
          />
        )
      })}
    </>
  )
}

function MessageAttachments({ attachments }: { attachments: ChatMessage['attachments'] }) {
  if (!attachments?.length) return null
  return (
    <div className="message-attachments">
      {attachments.map((file, idx) => (
        <div key={`${file.name}-${idx}`} className="message-attachment-item">
          {file.type.startsWith('image/') ? (
            <img className="message-attachment-image" src={file.previewUrl} alt={file.name} title={file.name} />
          ) : (
            <span className="message-attachment-file" title={file.name}>{file.name}</span>
          )}
        </div>
      ))}
    </div>
  )
}

function MessageBubble({
  message,
  isStreaming,
  projectId,
  threadId,
}: {
  message: ChatMessage
  isStreaming: boolean
  projectId: string
  threadId: string
}) {
  return (
    <div className={`message message-${message.role}`}>
      <MessageAvatar role={message.role} />
      <div className="message-body">
        <div className="message-bubble">
          <MessageAttachments attachments={message.attachments} />
          {message.content ? (
            <MessageContent content={message.content} projectId={projectId} threadId={threadId} />
          ) : null}
          {isStreaming && <span className="streaming-cursor" />}
        </div>
        <span className="message-timestamp">{formatTimeRelative(message.ts)}</span>
      </div>
    </div>
  )
}








const SUGGESTIONS = [
  'What can you help me with?',
  'Explain how this workspace works',
  'Run a quick system check',
]

function RenameInput({
  initialName,
  onSave,
  onCancel,
}: {
  initialName: string
  onSave: (name: string) => void
  onCancel: () => void
}) {
  const [value, setValue] = useState(initialName)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
    inputRef.current?.select()
  }, [])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      const trimmed = value.trim()
      if (trimmed) onSave(trimmed)
    } else if (e.key === 'Escape') {
      onCancel()
    }
  }

  return (
    <input
      ref={inputRef}
      type="text"
      className="chat-rename-input"
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onKeyDown={handleKeyDown}
      onBlur={() => {
        const trimmed = value.trim()
        if (trimmed) onSave(trimmed)
        else onCancel()
      }}
    />
  )
}

export function AppShell({
  onSend,
  projects,
  activeProjectId,
  activeChatId,
  currentThreadId,
  onSwitchProject,
  onRefreshProjects,
  onCreateProject,
  onEditProject,
  onDeleteProject,
  onHitlApprove,
  onHitlDecline,
  onHitlSelectChoice,
  onHitlSkip,
  onNewChat,
  onSelectChat,
  onDeleteChat,
  onRenameChat,
  onStop,
  examCountdown,
  activeMode = 'normal',
  onModeChange,
}: AppShellProps) {
  const connectionState = useAppStore((s) => s.connectionState)
  const pendingCorrelationId = useAppStore((s) => s.pendingCorrelationId)
  const messages = useAppStore((s) => s.messages)
  const conversationItems = useAppStore((s) => s.conversationItems)
  const operatorNote = useAppStore((s) => s.operatorNote)
  const setCloudStatus = useAppStore((s) => s.setCloudStatus)
  const windowMode = useAppStore((s) => s.windowMode)
  const setWindowMode = useAppStore((s) => s.setWindowMode)
  const studyView = useAppStore((s) => s.studyView)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const [streamActive, setStreamActive] = useState(false)
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const isStreamingRef = useRef(false)
  const [renamingChatId, setRenamingChatId] = useState<string | null>(null)
  const [renamingProjectId, setRenamingProjectId] = useState<string | null>(null)
  const [creatingProject, setCreatingProject] = useState(false)
  const [safeModePopoverOpen, setSafeModePopoverOpen] = useState(false)
  const attachWorkspaceFileRef = useRef<(file: AttachedFile) => void>(() => {})
  const [modeSwitchPending, setModeSwitchPending] = useState<'normal' | 'study' | 'pentest' | null>(null)
  const [pentestLoading, setPentestLoading] = useState(false)
  const [pentestLoadingStatus, setPentestLoadingStatus] = useState('')

  const [searchQuery, setSearchQuery] = useState('')
  const [isSearching, setIsSearching] = useState(false)
  const [searchResults, setSearchResults] = useState<ProjectChat[] | null>(null)

  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults(null)
      setIsSearching(false)
      return
    }
    
    setIsSearching(true)
    const timeout = setTimeout(async () => {
      try {
        const resp = await fetchWithAuth(`/api/projects/${activeProjectId}/chats/search?q=${encodeURIComponent(searchQuery)}`)
        if (resp.ok) {
          const data = await resp.json()
          if (data.status === 'ok') setSearchResults(data.results)
        }
      } finally {
        setIsSearching(false)
      }
    }, 400)
    return () => clearTimeout(timeout)
  }, [searchQuery, activeProjectId])

  const handlePinToggle = async (chatId: string, pinned: boolean) => {
    try {
      await fetchWithAuth(`/api/projects/${activeProjectId}/chats/${chatId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pinned: !pinned })
      })
      onRefreshProjects()
    } catch (e) {
      toast.error('Failed to update chat pin status')
    }
  }

  // Mode switch with confirmation modal (only for pentest transitions)
  const handleModeSwitchRequest = useCallback((mode: 'normal' | 'study' | 'pentest') => {
    if (mode === activeMode) return
    // Only show modal when switching to or from pentest mode
    if (mode === 'pentest' || activeMode === 'pentest') {
      setModeSwitchPending(mode)
    } else {
      // Normal <-> Study: switch directly
      onModeChange?.(mode)
    }
  }, [activeMode, onModeChange])

  const handleModeSwitchConfirm = useCallback(async () => {
    if (!modeSwitchPending || !onModeChange) return
    const target = modeSwitchPending
    setModeSwitchPending(null)

    if (target === 'pentest') {
      setPentestLoading(true)
      try {
        // Step 1: Stop StirlingPDF to free RAM
        setPentestLoadingStatus('Freeing RAM (stopping StirlingPDF)...')
        await fetchWithAuth('/api/pentest/services/stop-stirling', { method: 'POST' }).catch(() => {})

        // Step 2: Swap models (unload Qwen3, load Gemma 4 12B)
        setPentestLoadingStatus('Swapping to pentest model (Gemma 4 12B)...')
        const swapResp = await fetchWithAuth('/api/pentest/model/swap-to-pentest', { method: 'POST' })
        const swapData = await swapResp.json()
        if (swapData.status === 'ok') {
          setPentestLoadingStatus('Pentest model loaded.')
        } else {
          setPentestLoadingStatus(`Model swap: ${swapData.message || 'using current model'}`)
        }

        // Step 3: Start Kali VM
        setPentestLoadingStatus('Starting Kali VM...')
        const vmResp = await fetchWithAuth('/api/pentest/vm/start', { method: 'POST' })
        const vmData = await vmResp.json()
        if (vmData.status === 'ok') {
          setPentestLoadingStatus('Kali VM ready.')
        } else {
          setPentestLoadingStatus(`Kali VM: ${vmData.error || 'startup failed'}`)
        }
      } catch {
        setPentestLoadingStatus('Setup encountered an error.')
      }
      await new Promise((r) => setTimeout(r, 800))
      setPentestLoading(false)
    }

    if (target !== 'pentest' && activeMode === 'pentest') {
      // Exiting pentest: swap model back to default
      fetchWithAuth('/api/pentest/model/swap-to-default', { method: 'POST' }).catch(() => {})
    }

    onModeChange(target)
  }, [modeSwitchPending, onModeChange, activeMode])

  const handleModeSwitchCancel = useCallback(() => {
    setModeSwitchPending(null)
  }, [])

  const handleToggleMode = useCallback(async (targetMode: 'compact' | 'full') => {
    if (targetMode === 'compact') {
      void tauriBridge.setWindowSize(400, 600)
    } else {
      void tauriBridge.setWindowSize(1200, 800)
    }
    setWindowMode(targetMode)
    if (targetMode === 'compact') {
      setInspectorOpen(false)
    }
  }, [setWindowMode])

  // Detect streaming
  useEffect(() => {
    const last = messages[messages.length - 1]
    if (last && last.role === 'assistant' && last.id?.startsWith('stream-')) {
      isStreamingRef.current = true
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setStreamActive(true)
    } else {
      isStreamingRef.current = false
      setStreamActive(false)
    }
  }, [messages])

  // Auto-scroll (messages + conversation items)
  useEffect(() => {
    if (messagesContainerRef.current) {
      messagesContainerRef.current.scrollTop = messagesContainerRef.current.scrollHeight
    }
  }, [messages, conversationItems, streamActive])

  // Check if any HITL prompt is pending (for composer blocking)
  const hasPendingHitl = conversationItems.some(
    (item) => item.kind === 'hitl_prompt' && item.status === 'pending'
  )

  // Fetch cloud LLM status on mount and when connection changes
  useEffect(() => {
    let disposed = false
    const fetchCloudStatus = async () => {
      try {
        const response = await fetch('/api/cloud-status')
        if (!response.ok) return
        const status = await response.json()
        if (!disposed) setCloudStatus(status)
      } catch {
        if (!disposed) setCloudStatus(null)
        toast.error('Failed to fetch cloud status')
      }
    }
    if (connectionState === 'connected') {
      void fetchCloudStatus()
    } else {
      setCloudStatus(null)
    }
    return () => { disposed = true }
  }, [connectionState, setCloudStatus])

  // ESC key closes inspector overlay in compact mode
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape' && windowMode === 'compact' && inspectorOpen) {
      setInspectorOpen(false)
    }
  }, [windowMode, inspectorOpen])

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  // Click outside to close safe mode popover
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (safeModePopoverOpen) {
        const target = e.target as HTMLElement
        if (!target.closest('.safe-mode-popover-container')) {
          setSafeModePopoverOpen(false)
        }
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [safeModePopoverOpen])

  const activeProject = projects.find((p) => p.id === activeProjectId)
  const searchParams = new URLSearchParams(window.location.search)
  const isSidebarMode = searchParams.get('mode') === 'sidebar'
  const isCompact = (windowMode === 'compact' || isSidebarMode) && activeMode === 'normal'
  const projectChats = activeProject?.chats ?? []
  const showDragStrip = isTauriRuntime()

  return (
    <div className={`app-shell-wrapper theme-${activeMode}`} data-connection-state={connectionState}>
      <MacMenuBar 
        isCompact={isCompact} 
        onToggleMode={() => handleToggleMode(isCompact ? 'full' : 'compact')} 
      />
      <div className={`app-shell ${isCompact ? 'app-shell-compact' : ''}`}>
        {/* ── Left Panel (hidden in compact) ── */}
      {!isCompact && (
        <motion.aside 
          className="panel left-panel glass-panel"
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.3 }}
        >
          {showDragStrip && <div className="window-drag-strip" data-tauri-drag-region />}

          {/* ── Mode Switcher ── */}
          {onModeChange && (
            <div style={{ padding: '8px 10px 4px' }}>
              <ModeSwitcher activeMode={activeMode} onModeChange={handleModeSwitchRequest} />
            </div>
          )}



          {activeMode !== 'pentest' && (
          <details className="sidebar-accordion" open>
            <summary>
              Workspace
              <div className="workspace-header-actions" onClick={e => e.stopPropagation()}>
                <button
                  type="button"
                  className="workspace-refresh"
                  onClick={() => setCreatingProject(true)}
                  title="New workspace"
                >
                  + New
                </button>
                <button type="button" className="workspace-refresh" onClick={onRefreshProjects}>
                  Refresh
                </button>
              </div>
            </summary>
            <div className="sidebar-accordion-content">
              <p className="workspace-meta">
                Active: <strong>{activeProject?.name || activeProjectId}</strong>
              </p>
              <p className="workspace-meta">
                Thread: <code>{currentThreadId.length > 16 ? currentThreadId.slice(0, 16) + '…' : currentThreadId}</code>
              </p>
              <div className="workspace-project-list">
                {creatingProject && (
                  <div className="workspace-project-item workspace-project-item-active">
                    <span className="project-icon">+</span>
                    <RenameInput
                      initialName="New Workspace"
                      onSave={(newName) => {
                        onCreateProject(newName)
                        setCreatingProject(false)
                      }}
                      onCancel={() => setCreatingProject(false)}
                    />
                  </div>
                )}
                {projects.map((project) => (
                  <div
                    key={project.id}
                    className={`workspace-project-item${
                      project.id === activeProjectId ? ' workspace-project-item-active' : ''
                    }`}
                    onClick={() => {
                      if (renamingProjectId !== project.id) {
                        onSwitchProject(project.id)
                      }
                    }}
                  >
                    <span className="project-icon">{project.name?.charAt(0)?.toUpperCase() || '?'}</span>
                    {renamingProjectId === project.id ? (
                      <RenameInput
                        initialName={project.name}
                        onSave={(newName) => {
                          onEditProject(project.id, newName)
                          setRenamingProjectId(null)
                        }}
                        onCancel={() => setRenamingProjectId(null)}
                      />
                    ) : (
                      <>
                        <span className="project-name" title={project.name}>
                          {project.name}
                        </span>
                        {project.id !== 'default' && (
                          <span className="chat-list-item-actions">
                            <button
                              type="button"
                              className="chat-list-action"
                              title="Rename workspace"
                              onClick={(e) => {
                                e.stopPropagation()
                                setRenamingProjectId(project.id)
                              }}
                            >
                              ✎
                            </button>
                            <button
                              type="button"
                              className="chat-list-action chat-list-action-delete"
                              title="Delete workspace"
                              onClick={(e) => {
                                e.stopPropagation()
                                if (confirm('Delete this workspace? This cannot be undone.')) {
                                  onDeleteProject(project.id)
                                }
                              }}
                            >
                              ✕
                            </button>
                          </span>
                        )}
                      </>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </details>
          )}

          {activeMode !== 'pentest' && (
          <>
          {/* ── Chat List ── */}
          <details className="sidebar-accordion" open>
            <summary>
              Chats
              <div className="workspace-header-actions" onClick={e => e.stopPropagation()}>
                <button type="button" className="workspace-refresh" onClick={onNewChat} title="New chat">
                  + New
                </button>
              </div>
            </summary>
            <div className="sidebar-accordion-content">
              <div className="chat-search-container">
                <input
                  type="text"
                  placeholder="Search chats..."
                  className="chat-search-input"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
                {isSearching && <span className="chat-search-spinner" />}
              </div>
              <div className="chat-list">
                {(() => {
                  const chatsToRender = searchResults !== null ? searchResults : projectChats;
                  if (chatsToRender.length === 0) {
                    return <p className="chat-list-empty">{searchQuery ? 'No chats found.' : 'No chats yet. Start a new conversation.'}</p>
                  }

                  const now = new Date()
                  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
                  const startOfYesterday = startOfToday - 86400000
                  const startOfWeek = startOfToday - 86400000 * 7

                  const groups = {
                    Pinned: [] as ProjectChat[],
                    Today: [] as ProjectChat[],
                    Yesterday: [] as ProjectChat[],
                    'This Week': [] as ProjectChat[],
                    Older: [] as ProjectChat[]
                  }

                  chatsToRender.forEach((chat: any) => {
                    if (chat.pinned) {
                      groups.Pinned.push(chat)
                      return
                    }
                    const ts = chat.created_at * 1000
                    if (ts >= startOfToday) {
                      groups.Today.push(chat)
                    } else if (ts >= startOfYesterday) {
                      groups.Yesterday.push(chat)
                    } else if (ts >= startOfWeek) {
                      groups['This Week'].push(chat)
                    } else {
                      groups.Older.push(chat)
                    }
                  })

                  const renderGroup = (title: string, list: ProjectChat[]) => {
                    if (list.length === 0) return null
                    return (
                      <div key={title} className="chat-list-group">
                        <div className="chat-list-group-title">{title}</div>
                        {list.sort((a, b) => (b.created_at ?? 0) - (a.created_at ?? 0)).map((chat: any) => (
                          <div
                            key={chat.id}
                            className={`chat-list-item${chat.id === activeChatId ? ' chat-list-item-active' : ''}`}
                            onClick={() => {
                              if (renamingChatId !== chat.id) {
                                onSelectChat(chat.id)
                              }
                            }}
                          >
                            {renamingChatId === chat.id ? (
                              <RenameInput
                                initialName={chat.name}
                                onSave={(newName) => {
                                  onRenameChat(chat.id, newName)
                                  setRenamingChatId(null)
                                }}
                                onCancel={() => setRenamingChatId(null)}
                              />
                            ) : (
                              <>
                                <span className="chat-list-item-name" title={chat.name}>
                                  {chat.name}
                                </span>
                                <span className="chat-list-item-actions">
                                  <button
                                    type="button"
                                    className={`chat-list-action ${chat.pinned ? 'pinned-active' : ''}`}
                                    title={chat.pinned ? "Unpin chat" : "Pin chat"}
                                    onClick={(e) => {
                                      e.stopPropagation()
                                      handlePinToggle(chat.id, !!chat.pinned)
                                    }}
                                  >
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill={chat.pinned ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="17" x2="12" y2="22"></line><path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.68V6a3 3 0 0 0-3-3 3 3 0 0 0-3 3v4.68a2 2 0 0 1-1.11 1.87l-1.78.89A2 2 0 0 0 5 15.24Z"></path></svg>
                                  </button>
                                  <button
                                    type="button"
                                    className="chat-list-action"
                                    title="Rename"
                                    onClick={(e) => {
                                      e.stopPropagation()
                                      setRenamingChatId(chat.id)
                                    }}
                                  >
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"></path></svg>
                                  </button>
                                  <button
                                    type="button"
                                    className="chat-list-action chat-list-action-delete"
                                    title="Delete"
                                    onClick={(e) => {
                                      e.stopPropagation()
                                      if (confirm('Delete this chat? This cannot be undone.')) {
                                        onDeleteChat(chat.id)
                                      }
                                    }}
                                  >
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
                                  </button>
                                </span>
                              </>
                            )}
                          </div>
                        ))}
                      </div>
                    )
                  }

                  return (
                    <>
                      {renderGroup('Pinned', groups.Pinned)}
                      {renderGroup('Today', groups.Today)}
                      {renderGroup('Yesterday', groups.Yesterday)}
                      {renderGroup('This Week', groups['This Week'])}
                      {renderGroup('Older', groups.Older)}
                    </>
                  )
                })()}
              </div>
            </div>
          </details>

          {/* ── Knowledge ── */}
          <details className="sidebar-accordion" open>
            <summary>Knowledge</summary>
            <div className="sidebar-accordion-content">
              <ProjectKnowledgePanel
                activeProjectId={activeProjectId}
                onAttachToComposer={(file) => attachWorkspaceFileRef.current(file)}
              />
            </div>
          </details>
          </>
          )}

          {/* ── Exam Countdown ── */}
          {activeMode !== 'pentest' && examCountdown && examCountdown.length > 0 && (
            <details className="sidebar-accordion" open>
              <summary>Upcoming Exams</summary>
              <div className="sidebar-accordion-content">
                {examCountdown.map((exam) => (
                  <div key={exam.course_id} style={{
                    padding: '8px 10px',
                    marginBottom: 6,
                    borderRadius: 8,
                    background: 'rgba(255,255,255,0.03)',
                    border: '1px solid rgba(255,255,255,0.06)',
                  }}>
                    <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
                      {exam.name}
                    </div>
                    <div style={{ fontSize: 12, opacity: 0.7, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      <span>{exam.days_until <= 0 ? '🔴 Today!' : `📅 ${exam.days_until} day${exam.days_until !== 1 ? 's' : ''}`}</span>
                      {exam.pending_todos > 0 && <span>📝 {exam.pending_todos} todo{exam.pending_todos !== 1 ? 's' : ''}</span>}
                      {exam.current_streak > 0 && <span>🔥 {exam.current_streak}d streak</span>}
                    </div>
                    {exam.total_cards > 0 && (
                      <div style={{ fontSize: 11, opacity: 0.5, marginTop: 3 }}>
                        📇 {exam.due_cards}/{exam.total_cards} cards due
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </details>
          )}

          {/* ── Mode-Specific Sidebar Sections ── */}
          {activeMode === 'study' && (
            <button 
              className="glass-card" 
              style={{ width: '100%', marginBottom: '16px', padding: '12px', background: 'var(--accent)', color: 'black', border: 'none', cursor: 'pointer', fontWeight: '600', borderRadius: '8px' }}
              onClick={() => useAppStore.getState().setStudyView('dashboard')}
            >
              ← Subjects Dashboard
            </button>
          )}

          {activeMode === 'study' && (
            <details className="sidebar-accordion" open>
              <summary>Study Progress</summary>
              <div className="sidebar-accordion-content">
                <StudyProgressPanel />
              </div>
            </details>
          )}

          {activeMode === 'study' && (
            <details className="sidebar-accordion" open>
              <summary>Study Notes</summary>
              <div className="sidebar-accordion-content">
                <StudyNotesSearch />
              </div>
            </details>
          )}

          {activeMode === 'pentest' && (
            <>
              <EngagementSelector />
              <PhaseTracker />
              <QuickStats />
              <PentestScopePanel />
              <details className="sidebar-accordion" open>
                <summary>Infrastructure</summary>
                <div className="sidebar-accordion-content">
                  <PentestToolsPanel />
                </div>
              </details>
            </>
          )}
        </motion.aside>
      )}

      {activeMode === 'pentest' ? (
        <motion.main 
          className="panel pentest-dashboard glass-panel"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
        >
          <PentestDashboard 
            onSend={onSend} 
            onStop={onStop} 
            isGenerating={!!pendingCorrelationId} 
          />
        </motion.main>
      ) : activeMode === 'study' && studyView === 'dashboard' ? (
        <motion.main 
          className="panel center-panel glass-panel"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
        >
          <StudyDashboard 
            projects={projects}
            activeProjectId={activeProjectId}
            onSwitchProject={onSwitchProject}
            onCreateProject={onCreateProject}
          />
        </motion.main>
      ) : (
      <motion.main 
        className={`panel center-panel glass-panel${isCompact ? ' center-panel-compact' : ''}`}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
      >
        {showDragStrip && <div className="window-drag-strip" data-tauri-drag-region />}

        {operatorNote ? <p className="operator-note">ⓘ {operatorNote}</p> : null}
        <div className="messages-container" ref={messagesContainerRef}>
          <div className="messages">
            {/* Build unified timeline: messages + conversation items interleaved by time */}
            {(() => {
              const displayMessages = messages.filter((m) => {
                const content = (m.content || '').trim()
                if (!content) return false
                if (content.startsWith('[Internal reminder')) return false
                return true
              })

              // Convert display messages to timeline entries
              type TimelineEntry =
                | { kind: 'message'; message: ChatMessage; ts: number; idx: number }
                | { kind: 'conversation_item'; item: ConversationItem; ts: number }

              const entries: TimelineEntry[] = [
                ...displayMessages.map((msg, idx) => ({
                  kind: 'message' as const,
                  message: msg,
                  ts: msg.ts || 0,
                  idx,
                })),
                ...conversationItems.map((item) => ({
                  kind: 'conversation_item' as const,
                  item,
                  ts: item.ts || 0,
                })),
              ].sort((a, b) => a.ts - b.ts)

              if (entries.length === 0) {
                return (
                  <div className="messages-empty">
                    <div className="messages-empty-icon">💬</div>
                    <p className="messages-empty-text">
                      {isCompact ? 'Quick ask, quick answer' : 'Start a conversation with Owlynn'}
                    </p>
                    {!isCompact && (
                      <div className="messages-suggestions">
                        {SUGGESTIONS.map((suggestion) => (
                          <button
                            key={suggestion}
                            type="button"
                            className="messages-suggestion-btn"
                            onClick={() => onSend(suggestion)}
                            disabled={connectionState !== 'connected'}
                          >
                            {suggestion}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )
              }

              // First, group sequential tool_activity items
              const groupedEntries = []
              let currentToolGroup = null
              
              for (const entry of entries) {
                if (entry.kind === 'conversation_item' && entry.item.kind === 'tool_activity') {
                  if (!currentToolGroup) {
                    currentToolGroup = { kind: 'tool_group', items: [entry.item], ts: entry.ts }
                  } else {
                    currentToolGroup.items.push(entry.item)
                  }
                } else {
                  if (currentToolGroup) {
                    groupedEntries.push(currentToolGroup)
                    currentToolGroup = null
                  }
                  groupedEntries.push(entry)
                }
              }
              if (currentToolGroup) {
                groupedEntries.push(currentToolGroup)
              }

              return groupedEntries.map((entryRaw, groupIdx) => {
                const entry = entryRaw as any
                if (entry.kind === 'message') {
                  const { message, idx } = entry
                  const isStreaming =
                    isStreamingRef.current &&
                    idx === displayMessages.length - 1 &&
                    message.id?.startsWith('stream-')
                  return (
                    <MessageBubble
                      key={`msg-${message.id || idx}`}
                      message={message}
                      isStreaming={isStreaming}
                      projectId={activeProjectId}
                      threadId={currentThreadId}
                    />
                  )
                }

                if (entry.kind === 'tool_group') {
                  return (
                    <details key={`tool-group-${groupIdx}`} className="tool-group-pill">
                      <summary>
                        <span className="tool-group-icon">⚙️</span>
                        <span>Working... ({entry.items.length} tools used)</span>
                      </summary>
                      <div className="tool-group-content">
                        {entry.items.map((item: any) => {
                          const ta = item as ConversationToolActivity
                          return (
                            <ToolActivityCard
                              key={`tool-${ta.id}`}
                              activity={{
                                id: ta.id,
                                toolName: ta.toolName,
                                toolCallId: ta.toolCallId,
                                status: ta.status,
                                input: ta.input,
                                duration: ta.duration,
                                riskLabel: ta.riskLabel,
                                riskConfidence: ta.riskConfidence,
                                riskRationale: ta.riskRationale,
                                remediationHint: ta.remediationHint,
                              }}
                            />
                          )
                        })}
                      </div>
                    </details>
                  )
                }

                // conversation_item (hitl_prompt, etc)
                const item = entry.item

                if (item.kind === 'hitl_prompt') {
                  const hp = item as ConversationHitlPrompt
                  return (
                    <HitlPromptCard
                      key={`hitl-${hp.id}`}
                      model={hp.viewModel as unknown as HitlPromptViewModel}
                      status={hp.status}
                      onApprove={(answers) => onHitlApprove?.(hp.id, hp.variant as string, answers)}
                      onDecline={() => onHitlDecline?.(hp.id)}
                      onSelectChoice={(choice, userInput) => onHitlSelectChoice?.(choice, userInput)}
                      onSkip={() => onHitlSkip?.(hp.id)}
                    />
                  )
                }

                if (item.kind === 'chart_embed') {
                  const ce = item as ConversationChartEmbed
                  const resolved = resolveWorkspaceFileUrl(ce.url, activeProjectId)
                  if (ce.chartKind === 'interactive' || isInteractiveChartUrl(resolved)) {
                    return (
                      <ChatInteractiveChart
                        key={`chart-${ce.id}`}
                        src={resolved}
                        title={ce.filename}
                      />
                    )
                  }
                  return (
                    <ChatImageViewer
                      key={`chart-${ce.id}`}
                      src={resolved}
                      alt={ce.filename}
                    />
                  )
                }

                // Fallback for message-kind conversation items
                if (item.kind === 'message') {
                  const msgItem = item as { role: string; content: string; id: string; ts: number }
                  return (
                    <MessageBubble
                      key={`ci-msg-${msgItem.id}`}
                      message={{
                        id: msgItem.id,
                        role: msgItem.role as ChatMessage['role'],
                        content: msgItem.content,
                        ts: msgItem.ts,
                      }}
                      isStreaming={false}
                      projectId={activeProjectId}
                      threadId={currentThreadId}
                    />
                  )
                }

                return null
              })
            })()}
            <div ref={messagesEndRef} />
          </div>
        </div>
        {streamActive && (
          <div className="streaming-indicator">
            <span className="streaming-badge">
              <span className="streaming-dots">
                <span className="streaming-dot" />
                <span className="streaming-dot" />
                <span className="streaming-dot" />
              </span>
              Thinking
            </span>
          </div>
        )}
        <Composer
          onSend={onSend}
          disabled={connectionState !== 'connected'}
          isGenerating={!!pendingCorrelationId}
          hitlBlocked={hasPendingHitl}
          compact={isCompact}
          onStop={onStop}
          onRegisterWorkspaceAttach={(attach) => {
            attachWorkspaceFileRef.current = attach
          }}
        />
      </motion.main>
      )}
    </div>

      {/* ── Mode Switch Confirmation Modal ── */}
      {modeSwitchPending && (
        <ModeSwitchConfirmation
          targetMode={modeSwitchPending}
          currentMode={activeMode}
          onConfirm={handleModeSwitchConfirm}
          onCancel={handleModeSwitchCancel}
        />
      )}

      {/* ── Pentest Loading Overlay ── */}
      {pentestLoading && (
        <PentestLoadingOverlay status={pentestLoadingStatus} />
      )}
    </div>
  )
}
