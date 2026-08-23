import { useEffect, useRef, useState, useCallback, useMemo, type ReactNode } from 'react'
import {
  MessageSquare,
  Settings,
  Info,
  Network,
  LayoutGrid,
  Sparkles,
  GraduationCap,
  Shield,
} from 'lucide-react'
import toast from 'react-hot-toast'
// @ts-expect-error - vitest requires the default import to resolve named exports correctly
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize'
import type { Options } from 'rehype-sanitize'
import { Composer } from '../chat/Composer'
import { MindmapCanvas, type GraphNode } from '../mindmap/MindmapCanvas'
import { MacMenuBar } from './MacMenuBar'
import { StatusBar } from './StatusBar'
import { HitlPromptCard, type HitlPromptViewModel } from '../chat/HitlPromptCard'
import { ToolActivityCard } from '../chat/ToolActivityCard'
import { StudyDashboard } from '../study/StudyDashboard'
import { motion } from 'framer-motion'
import { ModeSwitchConfirmation, PentestLoadingOverlay } from '../shared/ModeSwitchModal'
import { PentestDashboard } from '../pentest/PentestDashboard'
import type { InterruptChoice } from '../../state/useAppStore'

import type { ConversationItem, ConversationToolActivity, ConversationHitlPrompt, ConversationChartEmbed } from '../../appEventHandlers'
import { useAppStore } from '../../state/useAppStore'
import { electronBridge as tauriBridge } from '../../lib/electronBridge'
import type { ChatMessage } from '../../types/protocol'
import type { AttachedFile } from '../../lib/attachments'
import { isTauriRuntime } from '../../lib/runtime'
import {
  isInteractiveChartUrl,
  isWorkspaceImageUrl,
  resolveWorkspaceFileUrl,
  rewriteWorkspaceImageMarkdown,
} from '../../lib/workspaceImageUrl'
import { ChatImageViewer } from '../chat/ChatImageViewer'
import { ChatInteractiveChart } from '../chat/ChatInteractiveChart'
import {
  parseInteractiveBlocks,
  InteractiveBlockRenderer,
  renderMarkdownSegment,
} from '../../lib/interactiveBlocks'
import { fetchWithAuth } from '../../lib/localRunToken'

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

export function AppShell({
  onSend,
  projects,
  activeProjectId,
  currentThreadId,
  onSwitchProject,
  onRefreshProjects,
  onCreateProject,
  onHitlApprove,
  onHitlDecline,
  onHitlSelectChoice,
  onHitlSkip,
  onSelectChat,
  onStop,
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
  const isStreamingRef = useRef(false)
  const [safeModePopoverOpen, setSafeModePopoverOpen] = useState(false)
  const attachWorkspaceFileRef = useRef<(file: AttachedFile) => void>(() => {})
  const [modeSwitchPending, setModeSwitchPending] = useState<'normal' | 'study' | 'pentest' | null>(null)
  const [pentestLoading, setPentestLoading] = useState(false)
  const [pentestLoadingStatus, setPentestLoadingStatus] = useState('')
  const [viewLayout, setViewLayout] = useState<'chat' | 'mindmap' | 'split'>('split')
  const [activeBranchTitle, setActiveBranchTitle] = useState<string>('')

  const activeBranchDisplayTitle = useMemo(() => {
    if (activeBranchTitle) return activeBranchTitle
    const project = projects.find((p) => p.id === activeProjectId)
    const chat = project?.chats?.find((c) => c.id === currentThreadId)
    return chat?.name || 'Active Branch'
  }, [activeBranchTitle, projects, activeProjectId, currentThreadId])

  useEffect(() => {
    const project = projects.find((p) => p.id === activeProjectId)
    const chat = project?.chats?.find((c) => c.id === currentThreadId)
    if (chat?.name) {
      setActiveBranchTitle(chat.name)
    }
  }, [currentThreadId, projects, activeProjectId])

  const ensureGraphChatRegistered = useCallback(
    async (node: GraphNode) => {
      if (activeMode === 'pentest') return
      const project = projects.find((p) => p.id === activeProjectId)
      const exists = project?.chats?.some((c) => c.id === node.id)
      if (exists) return
      try {
        const res = await fetchWithAuth(
          `/api/projects/${encodeURIComponent(activeProjectId)}/chats`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: node.id, name: node.title || 'New Chat' }),
          },
        )
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        onRefreshProjects?.()
      } catch {
        toast.error('Failed to register branch in workspace')
      }
    },
    [activeMode, activeProjectId, projects, onRefreshProjects],
  )

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

  const handleSelectGraphNode = useCallback(
    (node: GraphNode) => {
      if (node.id === currentThreadId) return

      const nodeMode = (node.mode || 'normal') as 'normal' | 'study' | 'pentest'
      if (nodeMode !== activeMode) {
        handleModeSwitchRequest(nodeMode)
      }

      void ensureGraphChatRegistered(node)
      setActiveBranchTitle(node.title || 'Thought')
      onSelectChat(node.id)
      toast.success(`Switched to "${node.title || 'Thought'}"`)
    },
    [activeMode, currentThreadId, handleModeSwitchRequest, ensureGraphChatRegistered, onSelectChat],
  )

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

  // Scroll tracking: only auto-scroll if user is near the bottom
  const autoScrollRef = useRef(true)
  const handleScroll = useCallback(() => {
    if (messagesContainerRef.current) {
      const el = messagesContainerRef.current
      autoScrollRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 150
    }
  }, [])

  // Auto-scroll (messages + conversation items)
  useEffect(() => {
    if (messagesContainerRef.current && autoScrollRef.current) {
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

  const searchParams = new URLSearchParams(window.location.search)
  const isSidebarMode = searchParams.get('mode') === 'sidebar'
  const isCompact = (windowMode === 'compact' || isSidebarMode) && activeMode === 'normal'
  const showDragStrip = isTauriRuntime()

  return (
    <div className={`app-shell-wrapper theme-${activeMode}`} data-connection-state={connectionState}>
      <MacMenuBar 
        isCompact={isCompact} 
        onToggleMode={() => handleToggleMode(isCompact ? 'full' : 'compact')} 
        activeMode={activeMode}
        onModeChange={handleModeSwitchRequest}
      />
      <div className={`app-shell ${isCompact ? 'app-shell-compact' : ''}`} style={{ flex: 1, display: 'flex', width: '100%', height: '100%', overflow: 'hidden' }}>

      {activeMode === 'pentest' ? (
        <motion.main 
          className="panel pentest-dashboard glass-panel"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          style={{ flex: 1, width: '100%', height: '100%' }}
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
          style={{ flex: 1, width: '100%', height: '100%' }}
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
        className={`panel center-panel glass-panel${isCompact ? ' center-panel-compact' : ''} flex flex-col`}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        style={{ padding: 0, overflow: 'hidden', flex: 1, width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}
      >
        {showDragStrip && <div className="window-drag-strip" data-tauri-drag-region />}

        {/* ── View Layout Switcher Bar ── */}
        {!isCompact && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '6px 14px',
              borderBottom: '1px solid rgba(255, 255, 255, 0.06)',
              background: 'rgba(13, 26, 45, 0.6)',
              backdropFilter: 'blur(8px)',
              flexShrink: 0,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 4, background: 'rgba(0, 0, 0, 0.3)', padding: 3, borderRadius: 8 }}>
              <button
                type="button"
                onClick={() => setViewLayout('chat')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 5,
                  padding: '3px 9px',
                  fontSize: 11,
                  fontWeight: viewLayout === 'chat' ? 600 : 400,
                  borderRadius: 6,
                  background: viewLayout === 'chat' ? 'rgba(56, 189, 248, 0.25)' : 'transparent',
                  color: viewLayout === 'chat' ? '#38bdf8' : '#94a3b8',
                  border: viewLayout === 'chat' ? '1px solid rgba(56, 189, 248, 0.4)' : 'none',
                  cursor: 'pointer',
                }}
              >
                <MessageSquare size={12} /> Chat
              </button>
              <button
                type="button"
                onClick={() => setViewLayout('split')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 5,
                  padding: '3px 9px',
                  fontSize: 11,
                  fontWeight: viewLayout === 'split' ? 600 : 400,
                  borderRadius: 6,
                  background: viewLayout === 'split' ? 'rgba(56, 189, 248, 0.25)' : 'transparent',
                  color: viewLayout === 'split' ? '#38bdf8' : '#94a3b8',
                  border: viewLayout === 'split' ? '1px solid rgba(56, 189, 248, 0.4)' : 'none',
                  cursor: 'pointer',
                }}
              >
                <LayoutGrid size={12} /> Split Graph
              </button>
              <button
                type="button"
                onClick={() => setViewLayout('mindmap')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 5,
                  padding: '3px 9px',
                  fontSize: 11,
                  fontWeight: viewLayout === 'mindmap' ? 600 : 400,
                  borderRadius: 6,
                  background: viewLayout === 'mindmap' ? 'rgba(56, 189, 248, 0.25)' : 'transparent',
                  color: viewLayout === 'mindmap' ? '#38bdf8' : '#94a3b8',
                  border: viewLayout === 'mindmap' ? '1px solid rgba(56, 189, 248, 0.4)' : 'none',
                  cursor: 'pointer',
                }}
              >
                <Network size={12} /> Mindmap
              </button>
            </div>
            <div style={{ fontSize: 11, color: '#94a3b8', display: 'flex', alignItems: 'center', gap: 6 }}>
              {(activeMode as string) === 'pentest' ? (
                <><Shield size={12} style={{ color: '#f43f5e' }} /> Attack Graph Canvas</>
              ) : activeMode === 'study' ? (
                <><GraduationCap size={12} style={{ color: '#c084fc' }} /> Mastery Knowledge Tree</>
              ) : (
                <><Sparkles size={12} style={{ color: '#38bdf8' }} /> Thought Constellation</>
              )}
            </div>
          </div>
        )}

        {viewLayout === 'mindmap' ? (
          <div style={{ flex: 1, position: 'relative', width: '100%', height: '100%' }}>
            <MindmapCanvas
              activeNodeId={currentThreadId}
              activeMode={activeMode}
              onSelectNode={handleSelectGraphNode}
            />
            {currentThreadId && (
              <div
                data-testid="active-branch"
                data-node-id={currentThreadId}
                style={{
                  position: 'absolute',
                  bottom: 48,
                  left: 216,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '4px 10px',
                  background: 'rgba(13, 26, 45, 0.9)',
                  border: '1px solid rgba(56, 189, 248, 0.25)',
                  borderRadius: 8,
                  fontSize: 11,
                  color: '#94a3b8',
                  backdropFilter: 'blur(8px)',
                  zIndex: 10,
                  pointerEvents: 'none',
                }}
              >
                <Network size={11} style={{ color: '#38bdf8' }} />
                <span>
                  Active Branch:{' '}
                  <strong style={{ color: '#f1f5f9' }}>{activeBranchDisplayTitle}</strong>
                </span>
              </div>
            )}
          </div>
        ) : (
          <div style={{ flex: 1, display: 'flex', width: '100%', height: '100%', overflow: 'hidden' }}>
            {viewLayout === 'split' && !isCompact && (
              <div style={{ width: '48%', height: '100%', borderRight: '1px solid rgba(255, 255, 255, 0.06)', position: 'relative' }}>
                <MindmapCanvas
                  activeNodeId={currentThreadId}
                  activeMode={activeMode}
                  onSelectNode={handleSelectGraphNode}
                />
              </div>
            )}
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
              {operatorNote ? <p className="operator-note" style={{ display: 'flex', alignItems: 'center', gap: 6, margin: '8px 16px 0' }}><Info size={14} /> {operatorNote}</p> : null}
              <div className="messages-container" ref={messagesContainerRef} onScroll={handleScroll}>
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
                    <div className="messages-empty-icon"><MessageSquare size={48} color="#888" /></div>
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
                  const isWorking = entry.items.some((ta: any) => ta.status === 'running' || ta.status === 'pending')
                  const requiresApproval = entry.items.some((ta: any) => ta.status === 'requires_approval')
                  const statusText = isWorking ? 'Working...' : requiresApproval ? 'Waiting for Approval...' : 'Finished'
                  
                  return (
                    <details key={`tool-group-${groupIdx}`} className="tool-group-pill">
                      <summary>
                        <span className={`tool-group-icon ${isWorking ? 'spinning' : ''}`} style={{ display: 'inline-flex', alignItems: 'center' }}><Settings size={14} /></span>
                        <span>{statusText} ({entry.items.length} tools used)</span>
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
        {(streamActive || !!pendingCorrelationId) && (
          <div className="streaming-indicator">
            <span className="streaming-badge">
              <span className="streaming-dots">
                <span className="streaming-dot" />
                <span className="streaming-dot" />
                <span className="streaming-dot" />
              </span>
              Thinking...
            </span>
          </div>
        )}
        {/* Active Thought Topic Pill in Split mode */}
        {viewLayout === 'split' && currentThreadId && (
          <div
            data-testid="active-branch"
            data-node-id={currentThreadId}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '3px 10px',
              margin: '0 16px 4px',
              background: 'rgba(13, 26, 45, 0.65)',
              border: '1px solid rgba(56, 189, 248, 0.2)',
              borderRadius: 6,
              fontSize: 11,
              color: '#94a3b8',
            }}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Network size={11} style={{ color: '#38bdf8' }} />
              <span>
                Active Branch:{' '}
                <strong style={{ color: '#f1f5f9' }}>{activeBranchDisplayTitle}</strong>
              </span>
            </span>
            <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>Mindmap Linked</span>
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
            </div>
          </div>
        )}
      </motion.main>
      )}
    </div>

      {/* ── Minimal Bottom Status Bar ── */}
      <StatusBar />

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
