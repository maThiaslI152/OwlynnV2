import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Composer } from './Composer'
import { LiveTalkControls } from './LiveTalkControls'
import { SafeModePanel } from './SafeModePanel'
import { ScreenAssistPanel } from './ScreenAssistPanel'
import { ActionProposalQueue } from './ActionProposalQueue'
import { ToolExecutionPanel } from './ToolExecutionPanel'
import { ProjectKnowledgePanel } from './ProjectKnowledgePanel'
import { OrchestrationPanel } from './OrchestrationPanel'
import { useAppStore } from '../state/useAppStore'
import type { ChatMessage } from '../types/protocol'

interface WorkspaceProject {
  id: string
  name: string
}

interface AppShellProps {
  onSend: (content: string) => void
  projects: WorkspaceProject[]
  activeProjectId: string
  currentThreadId: string
  onSwitchProject: (projectId: string) => void
  onRefreshProjects: () => void
  onApproveProposal?: (id: string) => Promise<void>
  onRejectProposal?: (id: string) => Promise<void>
}

function MessageAvatar({ role }: { role: ChatMessage['role'] }) {
  if (role === 'user') {
    return <div className="message-avatar">U</div>
  }
  return <div className="message-avatar">O</div>
}

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function MessageBubble({ message, isStreaming }: { message: ChatMessage; isStreaming: boolean }) {
  return (
    <div className={`message message-${message.role}`}>
      <MessageAvatar role={message.role} />
      <div className="message-body">
        <div className="message-bubble">
          {message.content.split('\n').map((line, i) => (
            <span key={i}>
              {line}
              {i < message.content.split('\n').length - 1 && <br />}
            </span>
          ))}
          {isStreaming && <span className="streaming-cursor" />}
        </div>
        <span className="message-timestamp">{formatTime(message.ts)}</span>
      </div>
    </div>
  )
}

function CollapsibleSection({
  title,
  defaultOpen = false,
  children,
}: {
  title: string
  defaultOpen?: boolean
  children: ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="inspector-section">
      <div className="inspector-section-header" onClick={() => setOpen(!open)}>
        <h3>{title}</h3>
        <span className={`inspector-toggle ${open ? 'inspector-toggle-open' : ''}`}>▶</span>
      </div>
      {open && <div className="inspector-section-body">{children}</div>}
    </div>
  )
}

export function AppShell({
  onSend,
  projects,
  activeProjectId,
  currentThreadId,
  onSwitchProject,
  onRefreshProjects,
  onApproveProposal,
  onRejectProposal,
}: AppShellProps) {
  const connectionState = useAppStore((s) => s.connectionState)
  const messages = useAppStore((s) => s.messages)
  const operatorNote = useAppStore((s) => s.operatorNote)
  const windowMode = useAppStore((s) => s.windowMode)
  const setWindowMode = useAppStore((s) => s.setWindowMode)
  const voiceState = useAppStore((s) => s.voiceState)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const [streamActive, setStreamActive] = useState(false)
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const isStreamingRef = useRef(false)

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

  // Auto-scroll
  useEffect(() => {
    if (messagesContainerRef.current) {
      messagesContainerRef.current.scrollTop = messagesContainerRef.current.scrollHeight
    }
  }, [messages, streamActive])

  const activeProject = projects.find((p) => p.id === activeProjectId)
  const isCompact = windowMode === 'compact'
  const showInspector = !isCompact || inspectorOpen

  return (
    <div className={`app-shell${isCompact ? ' app-shell-compact' : ''}`}>
      {/* ── Left Panel (full mode only) ── */}
      {!isCompact && (
        <aside className="panel left-panel">
          <div className="window-drag-strip" data-tauri-drag-region />
          <div className="workspace-section">
            <div className="workspace-header">
              <h2>Workspace</h2>
              <button type="button" className="workspace-refresh" onClick={onRefreshProjects}>
                Refresh
              </button>
            </div>
            <p className="workspace-meta">
              Active: <strong>{activeProject?.name || activeProjectId}</strong>
            </p>
            <p className="workspace-meta">
              Thread: <code>{currentThreadId.length > 16 ? currentThreadId.slice(0, 16) + '…' : currentThreadId}</code>
            </p>
            <div className="workspace-project-list">
              {projects.map((project) => (
                <button
                  key={project.id}
                  type="button"
                  className={`workspace-project-item${
                    project.id === activeProjectId ? ' workspace-project-item-active' : ''
                  }`}
                  onClick={() => onSwitchProject(project.id)}
                >
                  <span className="project-icon">{project.name?.charAt(0)?.toUpperCase() || '?'}</span>
                  <span className="project-name">{project.name}</span>
                </button>
              ))}
            </div>
          </div>
          <ProjectKnowledgePanel activeProjectId={activeProjectId} />
        </aside>
      )}

      {/* ── Center Panel ── */}
      <main className={`panel center-panel${isCompact ? ' center-panel-compact' : ''}`}>
        <div className="window-drag-strip" data-tauri-drag-region />
        <header className="topbar" data-tauri-drag-region>
          <h1>
            <span className="logo-dot" />
            Owlynn
          </h1>
          <div className="topbar-actions">
            {isCompact && (
              <>
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
                  onClick={() => setWindowMode('full')}
                  title="Full workspace"
                >
                  ⛶
                </button>
              </>
            )}
            {!isCompact && (
              <button
                type="button"
                className="topbar-btn"
                onClick={() => setWindowMode('compact')}
                title="Compact mode"
              >
                ⊟
              </button>
            )}
            <span className={`connection-status`}>
              <span className={`connection-dot connection-dot-${connectionState}`} />
              <span className="connection-label">{connectionState}</span>
            </span>
          </div>
        </header>
        {operatorNote ? <p className="operator-note">ⓘ {operatorNote}</p> : null}
        <div className="messages-container">
          <div className="messages" ref={messagesContainerRef}>
            {messages.length === 0 ? (
              <div className="messages-empty">
                <div className="messages-empty-icon">💬</div>
                <p className="messages-empty-text">
                  {isCompact ? 'Quick ask, quick answer' : 'Start a conversation with Owlynn'}
                </p>
                {isCompact && voiceState !== 'idle' && (
                  <p className="messages-empty-hint">
                    {voiceState === 'recording' ? 'Listening...' : voiceState === 'transcribing' ? 'Transcribing...' : ''}
                  </p>
                )}
              </div>
            ) : (
              messages.map((message, idx) => {
                const isStreaming =
                  isStreamingRef.current && idx === messages.length - 1 && message.id?.startsWith('stream-')
                return <MessageBubble key={message.id || idx} message={message} isStreaming={isStreaming} />
              })
            )}
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
        <Composer onSend={onSend} disabled={connectionState !== 'connected'} compact={isCompact} />
      </main>

      {/* ── Right Panel ── */}
      {showInspector && (
        <aside className={`panel right-panel${isCompact ? ' right-panel-overlay' : ''}`}>
          <div className="window-drag-strip" data-tauri-drag-region />
          {isCompact && (
            <div className="inspector-header" data-tauri-drag-region>
              <h2>Inspector</h2>
              <button type="button" className="topbar-btn" onClick={() => setInspectorOpen(false)}>✕</button>
            </div>
          )}
          {!isCompact && (
            <div className="inspector-header" data-tauri-drag-region>
              <h2>Inspector</h2>
            </div>
          )}
          <CollapsibleSection title="Orchestration" defaultOpen>
            <OrchestrationPanel />
          </CollapsibleSection>
          <CollapsibleSection title="Safe Mode">
            <SafeModePanel />
          </CollapsibleSection>
          <CollapsibleSection title="Live Talk">
            <LiveTalkControls />
          </CollapsibleSection>
          <CollapsibleSection title="Screen Assist">
            <ScreenAssistPanel />
          </CollapsibleSection>
          <CollapsibleSection title="Tool Execution">
            <ToolExecutionPanel />
          </CollapsibleSection>
          <CollapsibleSection title="Action Proposals">
            <ActionProposalQueue onApprove={onApproveProposal} onReject={onRejectProposal} />
          </CollapsibleSection>
        </aside>
      )}
    </div>
  )
}
