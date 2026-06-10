import { useEffect, useRef, useState, useCallback, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize'
import type { Options } from 'rehype-sanitize'
import { Composer } from './Composer'
import { SafeModePanel } from './SafeModePanel'
import { CloudSettingsPanel } from './CloudSettingsPanel'
import { CloudUsagePanel } from './CloudUsagePanel'
import { CloudUsageChip } from './CloudUsageChip'
import { ScreenAssistPanel } from './ScreenAssistPanel'
import { ProjectKnowledgePanel } from './ProjectKnowledgePanel'
import { OrchestrationPanel } from './OrchestrationPanel'
import { MemoryPanel } from './MemoryPanel'
import { HitlPromptCard, type HitlPromptViewModel } from './HitlPromptCard'
import { ToolActivityCard } from './ToolActivityCard'
import type { InterruptChoice } from '../state/useAppStore'
import type { ConversationItem, ConversationToolActivity, ConversationHitlPrompt } from '../appEventHandlers'
import { useAppStore } from '../state/useAppStore'
import { electronBridge as tauriBridge } from '../lib/electronBridge'
import type { ChatMessage } from '../types/protocol'
import type { AttachedFile } from '../lib/attachments'
import { isTauriRuntime } from '../lib/runtime'

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
    code: ['className'],
    pre: ['className'],
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

function MessageContent({ content }: { content: string }) {
  // Collapse 3+ consecutive newlines into a single blank line (2 newlines)
  // to prevent large visual gaps caused by excessive blank lines in markdown.
  const cleaned = content.replace(/\n{3,}/g, '\n\n')
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeRaw, [rehypeSanitize, markdownSchema]]}
      components={{
        a: ({ href, children, ...props }) => (
          <a className="msg-link" href={href} target="_blank" rel="noopener noreferrer" {...props}>
            {children}
          </a>
        ),
        pre: ({ children, ...props }) => (
          <pre className="msg-code-block" {...props}>
            {children}
          </pre>
        ),
        code: ({ className, children, ...props }) => {
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
        table: ({ children, ...props }) => (
          <div className="msg-table-wrap">
            <table className="msg-table" {...props}>{children}</table>
          </div>
        ),
        th: ({ children, ...props }) => (
          <th {...props}>{children}</th>
        ),
        td: ({ children, ...props }) => (
          <td {...props}>{children}</td>
        ),
        h1: ({ children, ...props }) => (
          <h1 className="msg-heading h1" {...props}>{children}</h1>
        ),
        h2: ({ children, ...props }) => (
          <h2 className="msg-heading h2" {...props}>{children}</h2>
        ),
        h3: ({ children, ...props }) => (
          <h3 className="msg-heading h3" {...props}>{children}</h3>
        ),
        h4: ({ children, ...props }) => (
          <h4 className="msg-heading h4" {...props}>{children}</h4>
        ),
        h5: ({ children, ...props }) => (
          <h5 className="msg-heading h5" {...props}>{children}</h5>
        ),
        h6: ({ children, ...props }) => (
          <h6 className="msg-heading h6" {...props}>{children}</h6>
        ),
        ul: ({ children, ...props }) => (
          <ul className="msg-list" {...props}>{children}</ul>
        ),
        ol: ({ children, ...props }) => (
          <ol className="msg-list" {...props}>{children}</ol>
        ),
      }}
    >
      {cleaned}
    </ReactMarkdown>
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

function MessageBubble({ message, isStreaming }: { message: ChatMessage; isStreaming: boolean }) {
  return (
    <div className={`message message-${message.role}`}>
      <MessageAvatar role={message.role} />
      <div className="message-body">
        <div className="message-bubble">
          <MessageAttachments attachments={message.attachments} />
          {message.content ? <MessageContent content={message.content} /> : null}
          {isStreaming && <span className="streaming-cursor" />}
        </div>
        <span className="message-timestamp">{formatTimeRelative(message.ts)}</span>
      </div>
    </div>
  )
}

function CollapsibleSection({
  title,
  icon,
  defaultOpen = false,
  children,
  rightAction,
  testId,
}: {
  title: string
  icon?: string
  defaultOpen?: boolean
  children: ReactNode
  rightAction?: ReactNode
  testId?: string
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="inspector-section" data-testid={testId}>
      <div className="inspector-section-header" onClick={() => setOpen(!open)}>
        <h3>{icon ? `${icon} ${title}` : title}</h3>
        <div className="inspector-section-header-actions">
          {rightAction}
          <span className={`inspector-toggle ${open ? 'inspector-toggle-open' : ''}`}>▶</span>
        </div>
      </div>
      <div
        className={`inspector-section-body ${open ? 'inspector-section-body-open' : ''}`}
        data-testid={testId ? `${testId}-body` : undefined}
      >
        {children}
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
  const cloudStatus = useAppStore((s) => s.cloudStatus)
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
      void tauriBridge.setWindowSize(680, 620)
    } else {
      void tauriBridge.setWindowSize(2400, 1600)
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
  const isCompact = windowMode === 'compact'
  const showInspector = !isCompact || inspectorOpen
  const projectChats = activeProject?.chats ?? []
  const showDragStrip = isTauriRuntime()

  return (
    <div className={`app-shell${isCompact ? ' app-shell-compact' : ''}`}>
      {/* ── Left Panel (full mode only) ── */}
      {!isCompact && (
        <aside className="panel left-panel">
          {showDragStrip && <div className="window-drag-strip" data-tauri-drag-region />}
          <div className="workspace-section">
            <div className="workspace-header">
              <h2>Workspace</h2>
              <div className="workspace-header-actions">
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
            </div>
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
          {/* ── Chat List ── */}
          <div className="workspace-section">
            <div className="workspace-header">
              <h2>Chats</h2>
              <button type="button" className="workspace-refresh" onClick={onNewChat} title="New chat">
                + New
              </button>
            </div>
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
          <ProjectKnowledgePanel
            activeProjectId={activeProjectId}
            onAttachToComposer={(file) => attachWorkspaceFileRef.current(file)}
          />
        </aside>
      )}

      {/* ── Center Panel ── */}
      <main className={`panel center-panel${isCompact ? ' center-panel-compact' : ''}`}>
        {showDragStrip && <div className="window-drag-strip" data-tauri-drag-region />}
        <header className="topbar" data-tauri-drag-region>
          <h1>
            <span className="logo-dot" />
            Owlynn
          </h1>
          {isCompact && (
            <div className="topbar-actions">
              <div className="safe-mode-popover-container" style={{ position: 'relative' }}>
                <button
                  type="button"
                  className="topbar-btn"
                  onClick={() => setSafeModePopoverOpen(!safeModePopoverOpen)}
                  title="Security & Safe Mode"
                >
                  🛡
                </button>
                {safeModePopoverOpen && (
                  <div className="topbar-popover">
                    <SafeModePanel />
                    <CloudSettingsPanel />
                  </div>
                )}
              </div>
              <button
                type="button"
                className="topbar-btn"
                onClick={() => setInspectorOpen(!inspectorOpen)}
                title="Toggle inspector"
              >
                {inspectorOpen ? '✕' : '☰'}
              </button>
              <button
                type="button"
                className="topbar-btn"
                onClick={() => handleToggleMode('full')}
                title="Full workspace"
              >
                ⛶
              </button>
              <span className={`connection-status`}>
                <span className={`connection-dot connection-dot-${connectionState}`} />
                <span className="connection-label">{connectionState}</span>
              </span>
              <CloudUsageChip />
              {cloudStatus && (
                <span className="connection-status" title={
                  cloudStatus.available && cloudStatus.key_valid
                    ? `Cloud: ${cloudStatus.model} (connected)` 
                    : cloudStatus.error || 'Cloud unavailable'
                }>
                  <span className={`connection-dot ${
                    cloudStatus.available && cloudStatus.key_valid ? 'connection-dot-connected' : 'connection-dot-error'
                  }`} />
                  <span className="connection-label">cloud</span>
                </span>
              )}
            </div>
          )}
        </header>
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

              return entries.map((entry) => {
                if (entry.kind === 'message') {
                  const { message, idx } = entry
                  const isStreaming =
                    isStreamingRef.current &&
                    idx === displayMessages.length - 1 &&
                    message.id?.startsWith('stream-')
                  return <MessageBubble key={`msg-${message.id || idx}`} message={message} isStreaming={isStreaming} />
                }

                // conversation_item
                const item = entry.item
                if (item.kind === 'tool_activity') {
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
                }

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

      {/* ── Right Panel ── */}
      {showInspector && (
        <aside className={`panel right-panel${isCompact ? ' right-panel-overlay' : ''}`}>
          {showDragStrip && <div className="window-drag-strip" data-tauri-drag-region />}
          {isCompact ? (
            <div className="inspector-header" data-tauri-drag-region>
              <h2>Inspector</h2>
              <button type="button" className="topbar-btn" onClick={() => setInspectorOpen(false)}>✕</button>
            </div>
          ) : (
            <div className="inspector-header" data-tauri-drag-region>
              <h2>Inspector</h2>
              <div className="inspector-header-actions">
                <button
                  type="button"
                  className="topbar-btn"
                  onClick={() => handleToggleMode('compact')}
                  title="Compact mode"
                >
                  ⊟
                </button>
                <span className={`connection-status`}>
                  <span className={`connection-dot connection-dot-${connectionState}`} />
                  <span className="connection-label">{connectionState}</span>
                </span>
                <CloudUsageChip />
                <div className="safe-mode-popover-container" style={{ position: 'relative' }}>
                  <button
                    type="button"
                    className="topbar-btn"
                    onClick={() => setSafeModePopoverOpen(!safeModePopoverOpen)}
                    title="Security & Safe Mode"
                  >
                    🛡
                  </button>
                  {safeModePopoverOpen && (
                    <div className="topbar-popover">
                      <SafeModePanel />
                    <CloudSettingsPanel />
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
          <CollapsibleSection
            title="Cloud & Usage"
            icon="☁"
            defaultOpen={false}
            testId="inspector-cloud-usage-section"
          >
            <CloudSettingsPanel />
            <CloudUsagePanel />
          </CollapsibleSection>
          <CollapsibleSection title="Orchestration" icon="⚙" defaultOpen>
            <OrchestrationPanel />
          </CollapsibleSection>
          <CollapsibleSection title="Memory & Context" icon="🧠" defaultOpen={false}>
            <MemoryPanel />
          </CollapsibleSection>
          <CollapsibleSection title="Screen Assist" icon="🖥">
            <ScreenAssistPanel />
          </CollapsibleSection>
        </aside>
      )}
    </div>
  )
}
