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

interface ProjectChat {
  id: string
  name: string
  created_at: number
}

interface WorkspaceProject {
  id: string
  name: string
  chats?: ProjectChat[]
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
  attributes: {
    ...defaultSchema.attributes,
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
}: AppShellProps) {
  const connectionState = useAppStore((s) => s.connectionState)
  const pendingCorrelationId = useAppStore((s) => s.pendingCorrelationId)
  const messages = useAppStore((s) => s.messages)
  const conversationItems = useAppStore((s) => s.conversationItems)
  const operatorNote = useAppStore((s) => s.operatorNote)
  const setCloudStatus = useAppStore((s) => s.setCloudStatus)
  const windowMode = useAppStore((s) => s.windowMode)
  const setWindowMode = useAppStore((s) => s.setWindowMode)
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
  const isCompact = windowMode === 'compact' || isSidebarMode
  const projectChats = activeProject?.chats ?? []
  const showDragStrip = isTauriRuntime()

  return (
    <div className="app-shell-wrapper" data-connection-state={connectionState}>
      <MacMenuBar 
        isCompact={isCompact} 
        onToggleMode={() => handleToggleMode(isCompact ? 'full' : 'compact')} 
      />
      <div className={`app-shell ${isCompact ? 'app-shell-compact' : ''}`}>
        {/* ── Left Panel (hidden in compact) ── */}
      {!isCompact && (
        <aside className="panel left-panel">
          {showDragStrip && <div className="window-drag-strip" data-tauri-drag-region />}
          
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
              <div className="chat-list">
                {projectChats.length === 0 ? (
                  <p className="chat-list-empty">No chats yet. Start a new conversation.</p>
                ) : (
                  [...projectChats]
                    .sort((a, b) => (b.created_at ?? 0) - (a.created_at ?? 0))
                    .map((chat) => (
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
                                className="chat-list-action"
                                title="Rename"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  setRenamingChatId(chat.id)
                                }}
                              >
                                ✎
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
                                ✕
                              </button>
                            </span>
                          </>
                        )}
                      </div>
                    ))
                )}
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
        </aside>
      )}

      {/* ── Center Panel ── */}
      <main className={`panel center-panel${isCompact ? ' center-panel-compact' : ''}`}>
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
      </main>
      </div>
    </div>
  )
}
