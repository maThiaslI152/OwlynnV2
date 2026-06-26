/** App shell and WebSocket lifecycle. Event contract: docs/CHAT_PROTOCOL.md */
/** App shell — WebSocket lifecycle and HITL resume. See docs/CHAT_PROTOCOL.md */
import { useEffect, useRef, useState, useCallback } from 'react'
import { listen } from './lib/electronBridge'
import { AppShell } from './components/AppShell'
import { WsClient } from './lib/wsClient'
import { useAppStore } from './state/useAppStore'
import { electronBridge as tauriBridge } from './lib/electronBridge'
import {
  buildAutoApproveInterruptResponse,
  buildChartEmbedItem,
  buildInterruptProposal,
  parseInterruptChoices,
  resolveProjectSwitch,
  toToolExecutionSnapshot,
  type ConversationToolActivity,
} from './appEventHandlers'
import { parseHitlPrompt } from './components/HitlPromptCard'
import {
  fetchCloudUsage,
  parseCloudUsagePayload,
  parseContextBreakdown,
} from './lib/cloudUsage'
import { toWsFilePayload, type AttachedFile, isWorkspaceRef } from './lib/attachments'
import { isToolPreambleText } from './lib/toolPreamble'
import type { BrowserPageContext } from './lib/browserPageContext'
import type { ChatMessage, ServerEvent } from './types/protocol'
import toast from 'react-hot-toast'

interface ProjectChat {
  id: string
  name: string
  created_at: number
}

interface ProjectSummary {
  id: string
  name: string
  chats?: ProjectChat[]
}

interface ProjectCreateResponse {
  id: string
  name: string
}

type TauriEventPayload = ServerEvent

function App() {
  const wsBaseUrl = import.meta.env.VITE_WS_BASE_URL ?? 'ws://127.0.0.1:8000/ws/chat'
  const setConnection = useAppStore((s) => s.setConnectionState)
  const addMessage = useAppStore((s) => s.addMessage)
  const setPendingCorrelationId = useAppStore((s) => s.setPendingCorrelationId)
  const setSafeMode = useAppStore((s) => s.setSafeMode)
  const setExecutionPolicy = useAppStore((s) => s.setExecutionPolicy)
  const setScreenAssistMode = useAppStore((s) => s.setScreenAssistMode)
  const setScreenAssistSource = useAppStore((s) => s.setScreenAssistSource)
  const setScreenAssistPreviewPath = useAppStore((s) => s.setScreenAssistPreviewPath)
  const upsertActionProposal = useAppStore((s) => s.upsertActionProposal)
  const updateActionProposalStatus = useAppStore((s) => s.updateActionProposalStatus)
  const executionPolicy = useAppStore((s) => s.executionPolicy)
  const latestToolExecution = useAppStore((s) => s.latestToolExecution)
  const setLatestToolExecution = useAppStore((s) => s.setLatestToolExecution)
  const pushToolExecution = useAppStore((s) => s.pushToolExecution)
  const setOperatorNote = useAppStore((s) => s.setOperatorNote)
  const applyBrowserPageContext = useAppStore((s) => s.applyBrowserPageContext)
  const setRouterMetadata = useAppStore((s) => s.setRouterMetadata)
  const setModelInfo = useAppStore((s) => s.setModelInfo)
  const setCoherenceRetryActive = useAppStore((s) => s.setCoherenceRetryActive)
  const setCloudFallback = useAppStore((s) => s.setCloudFallback)
  const setContextCompression = useAppStore((s) => s.setContextCompression)
  const setCloudUsage = useAppStore((s) => s.setCloudUsage)
  const setContextBreakdown = useAppStore((s) => s.setContextBreakdown)
  const refreshCloudUsage = useCallback(() => {
    void fetchCloudUsage().then((usage) => {
      if (usage) setCloudUsage(usage)
    })
  }, [setCloudUsage])
  const setMemoryUpdatedAt = useAppStore((s) => s.setMemoryUpdatedAt)
  const setTtsSpeaking = useAppStore((s) => s.setTtsSpeaking)
  const appendStreamChunk = useAppStore((s) => s.appendStreamChunk)
  const clearSession = useAppStore((s) => s.clearSession)
  const makeThreadId = () => `thread-${crypto.randomUUID()}`
  const initialThreadId = makeThreadId()
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [activeProjectId, setActiveProjectId] = useState('default')
  const [activeChatId, setActiveChatId] = useState(initialThreadId)
  const [currentThreadId, setCurrentThreadId] = useState(initialThreadId)
  const projectThreadsRef = useRef<Record<string, string>>({ default: initialThreadId })
  const activeProjectIdRef = useRef(activeProjectId)
  const currentThreadIdRef = useRef(currentThreadId)
  const wsClientRef = useRef<WsClient | null>(null)
  const pendingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isTauriRuntime = typeof window !== 'undefined' && Boolean((window as any).__TAURI_INTERNALS__)
  const apiBase = isTauriRuntime ? 'http://127.0.0.1:8000' : ''
  const apiUrl = (path: string) => apiBase + path

  const loadProjectsAbortRef = useRef<AbortController | null>(null)

  const loadProjects = useCallback(async () => {
    if (loadProjectsAbortRef.current) {
      loadProjectsAbortRef.current.abort()
    }
    const controller = new AbortController()
    loadProjectsAbortRef.current = controller

    try {
      const response = await fetch('/api/projects' + '?_t=' + Date.now(), {
        signal: controller.signal
      })
      if (!response.ok) return
      const payload = (await response.json()) as ProjectSummary[]
      const mapped = payload.map((project) => ({
        id: project.id,
        name: project.name ?? project.id,
        chats: (project.chats ?? []).map((c: any) => ({
          id: c.id,
          name: c.name ?? 'New Chat',
          created_at: c.created_at ?? 0,
        })),
      }))
      if (mapped.length === 0) {
        setProjects([{ id: 'default', name: 'General Workspace', chats: [] }])
        return
      }
      setProjects(mapped)
      const pid = activeProjectIdRef.current
      const tid = currentThreadIdRef.current
      const activeExists = mapped.some((project) => project.id === pid)
      if (!activeExists) {
        const first = mapped[0]
        const existingThread = projectThreadsRef.current[first.id] ?? makeThreadId()
        projectThreadsRef.current[first.id] = existingThread
        setActiveProjectId(first.id)
        setCurrentThreadId(existingThread)
        setActiveChatId(existingThread)
      } else {
        const activeProject = mapped.find((p) => p.id === pid)
        if (activeProject && activeProject.chats.length > 0) {
          const currentExists = tid && activeProject.chats.some((c) => c.id === tid)
          if (!currentExists) {
            projectThreadsRef.current[pid] = tid
          } else {
            projectThreadsRef.current[pid] = tid
          }
        } else {
          setActiveChatId(tid)
        }
      }
    } catch (e: any) {
      if (e.name === 'AbortError') return
      console.warn('[loadProjects]', e)
      toast.error('Failed to load workspaces')
      setProjects([{ id: 'default', name: 'General Workspace', chats: [] }])
    }
  }, [])

  const handleInterrupt = useCallback((interrupts: unknown[] | undefined) => {
    // ask_user interrupts always need UI interaction, regardless of execution policy
    const askUser = parseInterruptChoices(interrupts)
    if (askUser) {
      setOperatorNote('Clarification needed: choose an option to continue.')
      useAppStore.getState().appendConversationItem({
        kind: 'hitl_prompt',
        id: `hitl-${Date.now()}`,
        variant: 'ask_user',
        title: askUser.question,
        viewModel: { variant: 'ask_user', question: askUser.question, choices: askUser.choices },
        status: 'pending',
        ts: Date.now(),
      })
      return
    }

    // Try unified parse; covers scope_clarification, plan_review, security
    const hitlModel = parseHitlPrompt(interrupts)
    if (hitlModel) {
      useAppStore.getState().appendConversationItem({
        kind: 'hitl_prompt',
        id: `hitl-${Date.now()}`,
        variant: hitlModel.variant,
        title: hitlModel.title,
        viewModel: hitlModel as unknown as Record<string, unknown>,
        status: 'pending',
        ts: Date.now(),
      })
      return
    }

    // Fallback: auto-approve if policy allows
    if (executionPolicy === 'auto_approve') {
      const autoApprove = buildAutoApproveInterruptResponse()
      wsClientRef.current?.send(autoApprove.clientEvent)
      setOperatorNote(autoApprove.operatorNote)
      return
    }

    // Fallback: unknown interrupt format — build generic inline prompt
    const proposal = buildInterruptProposal(interrupts, latestToolExecution, Date.now())
    useAppStore.getState().appendConversationItem({
      kind: 'hitl_prompt',
      id: `hitl-${Date.now()}`,
      variant: 'security_approval',
      title: proposal.summary,
      viewModel: {
        variant: 'security_approval',
        title: proposal.summary,
        toolName: proposal.toolContext?.toolName || 'unknown',
        riskLabel: proposal.riskHint || 'sensitive',
        riskRationale: proposal.riskRationale || '',
        remediationHint: proposal.remediationHint || '',
      },
      status: 'pending',
      ts: Date.now(),
    })
    setOperatorNote('Security approval required — see prompt in chat.')
  }, [executionPolicy, latestToolExecution, wsClientRef, setOperatorNote])

  // Refs to keep latest callback references without triggering WS reconnects.
  const handleInterruptRef = useRef(handleInterrupt)
  handleInterruptRef.current = handleInterrupt
  const loadProjectsRef = useRef(loadProjects)
  loadProjectsRef.current = loadProjects

  useEffect(() => {
    activeProjectIdRef.current = activeProjectId
  }, [activeProjectId])

  useEffect(() => {
    currentThreadIdRef.current = currentThreadId
  }, [currentThreadId])

  useEffect(() => {
    let disposed = false
    const loadExecutionPolicy = async () => {
      try {
        const response = await fetch('/api/unified-settings')
        if (!response.ok) return
        const payload = (await response.json()) as { execution_policy?: string }
        if (disposed) return
        if (payload.execution_policy === 'hitl' || payload.execution_policy === 'auto_approve') {
          setExecutionPolicy(payload.execution_policy)
        }
      } catch (e) {
        console.warn('[execPolicy]', e)
        toast.error('Failed to load execution policy')
        // Keep local default if settings are unavailable.
      }
    }
    void loadExecutionPolicy()
    return () => {
      disposed = true
    }
  }, [setExecutionPolicy])

  useEffect(() => {
    void loadProjects()
  }, [loadProjects])

  useEffect(() => {
    let disposed = false
    const controller = new AbortController()
    const loadHistory = async () => {
      try {
        const response = await fetch(`/api/history/${encodeURIComponent(currentThreadId)}`, {
          signal: controller.signal
        })
        if (!response.ok) return
        const history = (await response.json()) as Array<{ type: string; content: string; tool_calls?: unknown[] }>
        if (disposed) return
        if (!Array.isArray(history)) return
        for (const msg of history) {
          if (msg.type === 'ai' || msg.type === 'AIMessage') {
            addMessage({
              id: `hist-${crypto.randomUUID()}`,
              role: 'assistant',
              content: msg.content || '',
              ts: Date.now(),
            })
          } else if (msg.type === 'human' || msg.type === 'HumanMessage') {
            addMessage({
              id: `hist-${crypto.randomUUID()}`,
              role: 'user',
              content: msg.content || '',
              ts: Date.now(),
            })
          }
        }
      } catch (e: any) {
        if (e.name === 'AbortError') return
        console.warn('[loadHistory]', e)
        toast.error('Failed to load chat history')
        // History unavailable — non-critical
      }
    }

    const wsUrl = `${wsBaseUrl}/${encodeURIComponent(currentThreadId)}`
    const wsClient = new WsClient(wsUrl)
    wsClientRef.current = wsClient
    const disconnect = wsClient.connect({
      onOpen: () => {
        if (disposed) return
        setConnection('connected')
        void loadHistory()
        void fetchCloudUsage().then((usage) => {
          if (usage) setCloudUsage(usage)
        })
      },
      onClose: () => {
        setConnection('disconnected')
        setLatestToolExecution(null)
        setPendingCorrelationId(null)
        if (pendingTimeoutRef.current) {
          clearTimeout(pendingTimeoutRef.current)
          pendingTimeoutRef.current = null
        }
        // Clear streaming state when connection drops
        // This handles cases where the agent finishes but WS events are lost
        const msgs = useAppStore.getState().messages
        const last = msgs[msgs.length - 1]
        if (last && last.role === 'assistant' && last.id?.startsWith('stream-')) {
          useAppStore.setState({
            messages: msgs.map((m, idx) =>
              idx === msgs.length - 1
                ? {
                    id: crypto.randomUUID(),
                    role: 'assistant',
                    content: m.content || '',
                    ts: Date.now(),
                  }
                : m
            ),
          })
        }
      },
      onError: () => setConnection('error'),
      onEvent: (event: ServerEvent) => {
        if (disposed) return
        const storeState = useAppStore.getState()
        const pendingId = storeState.pendingCorrelationId
        const eventId = (event as any).correlation_id
        const isIdleStatus =
          event.type === 'status' && (event as any).content === 'idle'

        if (eventId && pendingId && eventId !== pendingId) {
            console.debug("Ignoring mismatched correlation id", eventId)
            return
        }

        // Only reset timeout on meaningful events, not streaming chunks
        const isMeaningfulEvent = isIdleStatus ||
            event.type === 'assistant.message' ||
            event.type === 'tool_execution' ||
            event.type === 'hitl_prompt' ||
            event.type === 'router_decision' ||
            event.type === 'coherence_retry_started' ||
            event.type === 'coherence_retry_completed'

        if (isMeaningfulEvent && pendingTimeoutRef.current) {
            clearTimeout(pendingTimeoutRef.current)
            pendingTimeoutRef.current = null
        }

        if (isIdleStatus && pendingId) {
            useAppStore.setState({ pendingCorrelationId: null })
        } else if (!isIdleStatus && eventId && !pendingId) {
            useAppStore.setState({ pendingCorrelationId: eventId })
            // Fallback: clear pendingCorrelationId after 120s of no meaningful WS activity
            // This handles cases where status:idle or assistant.message is lost
            // Don't reset on chunk events — only meaningful events reset the timer
            pendingTimeoutRef.current = setTimeout(() => {
                const currentPending = useAppStore.getState().pendingCorrelationId
                if (currentPending) {
                    console.warn('[WS] Pending correlation timeout — clearing stale generating state')
                    useAppStore.setState({ pendingCorrelationId: null })
                }
                pendingTimeoutRef.current = null
            }, 120_000)
        }

        if (event.type === 'assistant.message') {
          const msg = 'message' in event ? (event as any).message : event
          const finalContent: string = msg.content || ''
          if (isToolPreambleText(finalContent)) {
            loadProjectsRef.current()
            return
          }
          loadProjectsRef.current()
          const msgs = useAppStore.getState().messages
          const last = msgs[msgs.length - 1]
          if (last && last.role === 'assistant' && last.id?.startsWith('stream-')) {
            useAppStore.setState({
              messages: msgs.map((m, idx) =>
                idx === msgs.length - 1
                  ? {
                      id: msg.id || crypto.randomUUID(),
                      role: 'assistant',
                      content: finalContent,
                      ts: Date.now(),
                    }
                  : m
              ),
            })
          } else {
            addMessage({
              id: msg.id || crypto.randomUUID(),
              role: 'assistant',
              content: finalContent,
              ts: Date.now(),
            })
          }
          if (finalContent.trim() && isTauriRuntime) {
            void tauriBridge.speakText(finalContent.trim())
          }
          if (pendingId) {
            useAppStore.setState({ pendingCorrelationId: null })
            if (pendingTimeoutRef.current) {
              clearTimeout(pendingTimeoutRef.current)
              pendingTimeoutRef.current = null
            }
          }
        } else if (event.type === 'safe_mode.changed') {
          setSafeMode(event.mode)
        } else if (event.type === 'screen_assist.state') {
          setScreenAssistMode(event.mode)
          setScreenAssistSource(event.source)
          setScreenAssistPreviewPath(event.preview_path ?? null)
        } else if (event.type === 'action.proposal') {
          upsertActionProposal(event.proposal)
        } else if (event.type === 'action.proposal.result') {
          updateActionProposalStatus(event.id, event.status)
        } else if (event.type === 'tool_execution') {
          const snapshot = toToolExecutionSnapshot(event, Date.now())
          setLatestToolExecution(snapshot)
          pushToolExecution(snapshot)
          if (snapshot.status === 'running') {
            const msgs = useAppStore.getState().messages
            const last = msgs[msgs.length - 1]
            if (
              last?.role === 'assistant' &&
              last.id?.startsWith('stream-') &&
              isToolPreambleText(last.content)
            ) {
              useAppStore.setState({ messages: msgs.slice(0, -1) })
            }
          }
          // Append inline tool activity card to conversation timeline
          const store = useAppStore.getState()
          const existingIdx = store.conversationItems.findIndex(
            (item) =>
              item.kind === 'tool_activity' &&
              (item.toolCallId === snapshot.toolCallId ||
                (item.toolName === snapshot.toolName && item.status === 'running' && snapshot.status !== 'running'))
          )
          if (existingIdx >= 0) {
            const updated = [...store.conversationItems]
            updated[existingIdx] = {
              ...updated[existingIdx],
              status: snapshot.status,
              duration: snapshot.duration,
            } as ConversationToolActivity
            useAppStore.setState({ conversationItems: updated })
          } else {
            store.appendConversationItem({
              kind: 'tool_activity',
              id: snapshot.toolCallId || `tool-${Date.now()}`,
              toolName: snapshot.toolName,
              toolCallId: snapshot.toolCallId ?? null,
              status: snapshot.status,
              input: snapshot.input ?? null,
              riskLabel: snapshot.riskLabel,
              riskConfidence: snapshot.riskConfidence,
              riskRationale: snapshot.riskRationale,
              remediationHint: snapshot.remediationHint,
              ts: Date.now(),
              duration: snapshot.duration,
            })
          }
          const chartEmbed = buildChartEmbedItem(event, Date.now())
          if (chartEmbed) {
            store.appendConversationItem(chartEmbed)
          }
        } else if (event.type === 'interrupt') {
          handleInterruptRef.current(event.interrupts)
        } else if (event.type === 'router_info') {
          setRouterMetadata(event.metadata as Record<string, unknown>)
          if ((event as any).model) {
            setModelInfo((event as any).model as string)
          }
        } else if (event.type === 'model_info') {
          setModelInfo(event.model as string)
          const tokenUsage = (event as { token_usage?: Record<string, unknown> }).token_usage
          const breakdown = parseContextBreakdown(tokenUsage?.context_breakdown)
          if (breakdown) setContextBreakdown(breakdown)
        } else if (event.type === 'cloud_usage') {
          setCloudUsage(parseCloudUsagePayload(event as unknown as Record<string, unknown>))
        } else if (event.type === 'cloud_budget_warning') {
          const threshold = Number((event as any).threshold ?? 0)
          const pct = Math.round(Number((event as any).used_pct ?? 0) * 100)
          setOperatorNote(
            `Cloud budget warning: ${pct}% of daily token limit used (threshold ${Math.round(threshold * 100)}%).`
          )
        } else if (event.type === 'chunk') {
          const chunkContent = (event as any).content || ''
          if (chunkContent && !isToolPreambleText(chunkContent)) {
            appendStreamChunk(chunkContent)
          }
        } else if (event.type === 'context_summarized') {
          setContextCompression({
            summary: event.summary,
            takeaways: event.takeaways,
            messagesCompressed: event.messages_compressed,
            tokensFreed: event.tokens_freed,
          })
        } else if (event.type === 'memory_updated') {
          setMemoryUpdatedAt(Date.now())
        } else if (event.type === 'file_status') {
          loadProjectsRef.current()
          window.dispatchEvent(new CustomEvent('owlynn:file_status', { detail: event }))
        } else if (event.type === 'browser.page_context') {
          const ctx: BrowserPageContext = {
            url: String((event as any).url || ''),
            title: String((event as any).title || ''),
            text: String((event as any).text || ''),
            selection: String((event as any).selection || ''),
            intent: String((event as any).intent || 'default'),
          }
          applyBrowserPageContext(ctx)
        } else if (event.type === 'coherence_retry_started') {
          setCoherenceRetryActive(
            true,
            Number((event as any).attempt ?? 1),
            Number((event as any).original_confidence ?? null) || null,
          )
        } else if (event.type === 'coherence_retry_completed') {
          setCoherenceRetryActive(false)
        } else if (event.type === 'cloud_fallback') {
          setCloudFallback({
            reason: (event as any).reason || 'cloud_unavailable',
            fallback_model: (event as any).fallback_model || 'local-fallback',
            can_retry: (event as any).can_retry !== false,
          })
        }
      },
    })

    setConnection('connecting')
    return () => {
      disposed = true
      controller.abort()
      disconnect()
      wsClientRef.current = null
      if (pendingTimeoutRef.current) {
        clearTimeout(pendingTimeoutRef.current)
        pendingTimeoutRef.current = null
      }
    }
  }, [activeProjectId, addMessage, appendStreamChunk, applyBrowserPageContext, currentThreadId, executionPolicy, pushToolExecution, setConnection, setLatestToolExecution, setPendingCorrelationId, setMemoryUpdatedAt, setModelInfo, setContextCompression, setContextBreakdown, setCloudUsage, setCoherenceRetryActive, setCloudFallback, setOperatorNote, setRouterMetadata, setSafeMode, setScreenAssistMode, setScreenAssistPreviewPath, setScreenAssistSource, setTtsSpeaking, upsertActionProposal, updateActionProposalStatus, isTauriRuntime, wsBaseUrl])

  // Listen for Tauri runtime events (TTS state, screen assist, etc.)
  useEffect(() => {
    let unlisten: (() => void) | undefined
    void listen<TauriEventPayload>('owlynn://runtime-event', (event: { payload: TauriEventPayload }) => {
      const payload = event.payload
      if (payload.type === 'voice.tts_state') {
        setTtsSpeaking(payload.speaking)
      } else if (payload.type === 'safe_mode.changed') {
        setSafeMode(payload.mode)
      } else if (payload.type === 'screen_assist.state') {
        setScreenAssistMode(payload.mode)
        setScreenAssistSource(payload.source)
        setScreenAssistPreviewPath(payload.preview_path ?? null)
      } else if (payload.type === 'action.proposal') {
        upsertActionProposal(payload.proposal)
      } else if (payload.type === 'action.proposal.result') {
        updateActionProposalStatus(payload.id, payload.status)
      } else if (payload.type === 'tool_execution') {
        const snapshot = toToolExecutionSnapshot(payload, Date.now())
        setLatestToolExecution(snapshot)
        pushToolExecution(snapshot)
        // Append inline tool activity card
        const store = useAppStore.getState()
        const existingIdx = store.conversationItems.findIndex(
          (item) =>
            item.kind === 'tool_activity' &&
            (item.toolCallId === snapshot.toolCallId ||
              (item.toolName === snapshot.toolName && item.status === 'running' && snapshot.status !== 'running'))
        )
        if (existingIdx >= 0) {
          const updated = [...store.conversationItems]
          updated[existingIdx] = {
            ...updated[existingIdx],
            status: snapshot.status,
            duration: snapshot.duration,
          } as ConversationToolActivity
          useAppStore.setState({ conversationItems: updated })
        } else {
          store.appendConversationItem({
            kind: 'tool_activity',
            id: snapshot.toolCallId || `tool-${Date.now()}`,
            toolName: snapshot.toolName,
            toolCallId: snapshot.toolCallId ?? null,
            status: snapshot.status,
            input: snapshot.input ?? null,
            riskLabel: snapshot.riskLabel,
            riskConfidence: snapshot.riskConfidence,
            riskRationale: snapshot.riskRationale,
            remediationHint: snapshot.remediationHint,
            ts: Date.now(),
            duration: snapshot.duration,
          })
        }
        const chartEmbed = buildChartEmbedItem(payload, Date.now())
        if (chartEmbed) {
          store.appendConversationItem(chartEmbed)
        }
      } else if (payload.type === 'interrupt') {
        handleInterrupt(payload.interrupts)
    }
  }).then((fn: (() => void) | undefined) => {
    unlisten = fn
    }).catch(() => {
      // Non-Tauri browser preview mode
    })

    return () => {
      if (unlisten) unlisten()
    }
  }, [addMessage, executionPolicy, handleInterrupt, latestToolExecution, pushToolExecution, setLatestToolExecution, setOperatorNote, setSafeMode, setScreenAssistMode, setScreenAssistPreviewPath, setScreenAssistSource, setTtsSpeaking, upsertActionProposal, updateActionProposalStatus])

  const handleSend = useCallback((content: string, files?: AttachedFile[]) => {
    const store = useAppStore.getState()
    const activePersonaId = store.activePersonaId
    const responseStyle = store.responseStyle || store.evalResponseStyle || undefined
    const message: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      ts: Date.now(),
    }

    if (files && files.length > 0) {
      message.attachments = files.map((f) => ({
        name: f.name,
        type: f.type,
        previewUrl: isWorkspaceRef(f) ? '' : f.data,
      }))
      const refNames = files.filter((f) => isWorkspaceRef(f)).map((f) => f.name)
      const uploadNames = files.filter((f) => !isWorkspaceRef(f) && !f.type.startsWith('image/')).map((f) => f.name)
      const suffixParts: string[] = []
      if (refNames.length > 0) {
        suffixParts.push(`[Referenced: ${refNames.join(', ')}]`)
      }
      if (uploadNames.length > 0) {
        suffixParts.push(`[Attached: ${uploadNames.join(', ')}]`)
      }
      if (suffixParts.length > 0) {
        const suffix = suffixParts.join('\n')
        message.content = content ? `${content}\n\n${suffix}` : suffix
      }
    }

    addMessage(message)
    setPendingCorrelationId(message.id)
    wsClientRef.current?.send({
      correlation_id: message.id,
      type: 'user.message',
      id: message.id,
      content: message.content,
      message: content,
      files: files && files.length > 0 ? files.map(toWsFilePayload) : undefined,
      project_id: activeProjectId,
      persona_id: activePersonaId,
      ...(responseStyle ? { response_style: responseStyle } : {}),
    })
  }, [addMessage, activeProjectId])

  useEffect(() => {
    const store = useAppStore.getState()
    const setEvalResponseStyle = store.setEvalResponseStyle
    const setPendingCorrelationId = store.setPendingCorrelationId
    ;(window as Window & {
      __owlynnEval?: {
        setResponseStyle: (s: string) => void
        clearPendingCorrelation: () => void
        clearStreamingState: () => void
      }
    }).__owlynnEval = {
      setResponseStyle: (style: string) => setEvalResponseStyle(style || null),
      clearPendingCorrelation: () => setPendingCorrelationId(null),
      clearStreamingState: () => {
        setPendingCorrelationId(null)
        const msgs = useAppStore.getState().messages
        const last = msgs[msgs.length - 1]
        if (last && last.role === 'assistant' && last.id?.startsWith('stream-')) {
          useAppStore.setState({
            messages: msgs.map((m, idx) =>
              idx === msgs.length - 1
                ? { ...m, id: crypto.randomUUID() }
                : m
            ),
          })
        }
      },
    }
    return () => {
      delete (window as Window & { __owlynnEval?: unknown }).__owlynnEval
    }
  }, [])

  const handleStop = useCallback(() => {
    wsClientRef.current?.send({ type: 'stop' })
    setPendingCorrelationId(null)
    setOperatorNote('Interrupted by user.')
  }, [setPendingCorrelationId, setOperatorNote])

  // ── Inline HITL card callbacks ────────────────────────────────────
  const handleHitlApprove = useCallback((hitlId: string, variant: string, answers?: Record<string, unknown>) => {
    const store = useAppStore.getState()
    if (variant === 'security_approval') {
      const corrId = crypto.randomUUID()
      setPendingCorrelationId(corrId)
      wsClientRef.current?.send({ type: 'security_approval', approved: true, correlation_id: corrId })
      store.updateConversationItemStatus(hitlId, 'approved')
    } else if (variant === 'plan_review') {
      const corrId = crypto.randomUUID()
      setPendingCorrelationId(corrId)
      wsClientRef.current?.send({ type: 'plan_review_response', approved: true, correlation_id: corrId })
      store.updateConversationItemStatus(hitlId, 'approved')
    } else if (variant === 'scope_clarification') {
      const corrId = crypto.randomUUID()
      setPendingCorrelationId(corrId)
      wsClientRef.current?.send({
        type: 'ask_user_response',
        answer: answers || { skipped: false },
        correlation_id: corrId,
      })
      store.updateConversationItemStatus(hitlId, 'approved')
    } else if (variant === 'ask_user') {
      store.updateConversationItemStatus(hitlId, 'approved')
    }
    setOperatorNote('Action approved.')
  }, [])

  const handleHitlDecline = useCallback((hitlId: string) => {
    const corrId = crypto.randomUUID()
    setPendingCorrelationId(corrId)
    wsClientRef.current?.send({ type: 'security_approval', approved: false, correlation_id: corrId })
    useAppStore.getState().updateConversationItemStatus(hitlId, 'rejected')
    setOperatorNote('Action declined.')
  }, [])

  const handleHitlSelectChoice = useCallback((choice: import('./state/useAppStore').InterruptChoice, userInput?: string) => {
    const answer: Record<string, unknown> = { ...choice }
    if (userInput !== undefined) {
      answer.user_input = userInput
    }
    const corrId = crypto.randomUUID()
    setPendingCorrelationId(corrId)
    wsClientRef.current?.send({
      type: 'ask_user_response',
      answer: answer,
      correlation_id: corrId,
    })
    const store = useAppStore.getState()
    const pendingHitl = store.conversationItems.find(
      (item) => item.kind === 'hitl_prompt' && item.status === 'pending'
    )
    if (pendingHitl) {
      store.updateConversationItemStatus(pendingHitl.id, 'approved')
    }
    setOperatorNote('Choice sent — resuming conversation.')
  }, [])

  const handleHitlSkip = useCallback((hitlId: string) => {
    useAppStore.getState().updateConversationItemStatus(hitlId, 'dismissed')
    const corrId = crypto.randomUUID()
    setPendingCorrelationId(corrId)
    wsClientRef.current?.send({
      type: 'ask_user_response',
      answer: { skipped: true },
      correlation_id: corrId,
    })
    setOperatorNote('Skipped clarification.')
  }, [])

  const handleSwitchProject = useCallback((projectId: string) => {
    const next = resolveProjectSwitch({
      activeProjectId,
      currentThreadId,
      targetProjectId: projectId,
      projectThreads: projectThreadsRef.current,
      makeThreadId,
    })
    if (!next) return
    projectThreadsRef.current = next.nextProjectThreads
    clearSession()
    setActiveProjectId(next.nextActiveProjectId)
    setCurrentThreadId(next.nextCurrentThreadId)
    setActiveChatId(next.nextCurrentThreadId)
    setOperatorNote(next.operatorNote)
    refreshCloudUsage()
  }, [activeProjectId, currentThreadId, clearSession, refreshCloudUsage])

  const handleNewChat = useCallback(() => {
    const newThreadId = makeThreadId()
    const updatedThreads = { ...projectThreadsRef.current, [activeProjectId]: newThreadId }
    projectThreadsRef.current = updatedThreads
    clearSession()
    setCurrentThreadId(newThreadId)
    setActiveChatId(newThreadId)
    setOperatorNote('New conversation started.')
    refreshCloudUsage()
  }, [activeProjectId, clearSession, refreshCloudUsage])

  const handleDeleteChat = useCallback(async (chatId: string) => {
    try {
      const url = `/api/projects/${encodeURIComponent(activeProjectId)}/chats/${encodeURIComponent(chatId)}`
      const response = await fetch(url, {
        method: 'DELETE',
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      await loadProjects()
      if (chatId === activeChatId) {
        handleNewChat()
      } else {
        setOperatorNote('Chat deleted.')
      }
    } catch (e: any) {
      toast.error('Failed to delete chat.')
      setOperatorNote('Failed to delete chat.')
    }
  }, [activeProjectId, activeChatId, loadProjects, handleNewChat])

  const handleRenameChat = useCallback(async (chatId: string, newName: string) => {
    try {
      await fetch(`/api/projects/${encodeURIComponent(activeProjectId)}/chats/${encodeURIComponent(chatId)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName }),
      })
      await loadProjects()
    } catch (e) {
      console.warn('[renameChat]', e)
      toast.error('Failed to rename chat.')
    }
  }, [activeProjectId, loadProjects])

  const handleSelectChat = useCallback((chatId: string) => {
    if (chatId === activeChatId) return
    const updatedThreads = { ...projectThreadsRef.current, [activeProjectId]: chatId }
    projectThreadsRef.current = updatedThreads
    clearSession()
    setCurrentThreadId(chatId)
    setActiveChatId(chatId)
    setOperatorNote(`Switched to chat.`)
    refreshCloudUsage()
  }, [activeProjectId, activeChatId, clearSession, refreshCloudUsage])

  const handleCreateProject = useCallback(async (projectName: string) => {
    const trimmedName = projectName.trim()
    if (!trimmedName) return
    try {
      const response = await fetch(apiUrl('/api/projects'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: trimmedName }),
      })
      if (!response.ok) throw new Error('create failed')
      const created = (await response.json()) as ProjectCreateResponse
      const newThreadId = makeThreadId()
      projectThreadsRef.current = { ...projectThreadsRef.current, [created.id]: newThreadId }
      clearSession()
      setActiveProjectId(created.id)
      setCurrentThreadId(newThreadId)
      setActiveChatId(newThreadId)
      setOperatorNote('Switched to new workspace.')
      await loadProjects()
    } catch (e) {
      console.error('[createWorkspace]', e)
      toast.error('Failed to create workspace.')
      setOperatorNote('Failed to create workspace.')
    }
  }, [clearSession, loadProjects])

  const handleEditProject = useCallback(async (projectId: string, name: string) => {
    try {
      await fetch(`/api/projects/${encodeURIComponent(projectId)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })
      await loadProjects()
    } catch (e) {
      console.warn('[editProject]', e)
      toast.error('Failed to rename workspace.')
    }
  }, [loadProjects])

  const handleDeleteProject = useCallback(async (projectId: string) => {
    try {
      const url = `/api/projects/${encodeURIComponent(projectId)}`
      const response = await fetch(url, {
        method: 'DELETE',
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const updatedThreads = { ...projectThreadsRef.current }
      delete updatedThreads[projectId]
      projectThreadsRef.current = updatedThreads
      if (projectId === activeProjectIdRef.current) {
        const fallbackThreadId = projectThreadsRef.current.default ?? makeThreadId()
        projectThreadsRef.current = { ...projectThreadsRef.current, default: fallbackThreadId }
        clearSession()
        setActiveProjectId('default')
        setCurrentThreadId(fallbackThreadId)
        setActiveChatId(fallbackThreadId)
        setOperatorNote('Workspace deleted. Viewing default workspace.')
      } else {
        setOperatorNote('Workspace deleted.')
      }
      await loadProjects()
    } catch (e: any) {
      toast.error('Failed to delete workspace.')
      setOperatorNote('Failed to delete workspace.')
    }
  }, [clearSession, loadProjects])  // activeProjectId removed — uses ref for latest value

  // ── Cloud fallback HITL handlers ─────────────────────────────────────
  const cloudFallback = useAppStore((s) => s.cloudFallback)
  const handleCloudFallbackRetry = useCallback(() => {
    setCloudFallback(null)
    const msgs = useAppStore.getState().messages
    const lastUser = [...msgs].reverse().find((m) => m.role === 'user')
    if (lastUser && wsClientRef.current) {
      const retryId = `retry-${crypto.randomUUID()}`
      wsClientRef.current.send({
        type: 'user_message',
        content: lastUser.content,
        correlation_id: retryId,
      } as any)
      setPendingCorrelationId(retryId)
    }
  }, [setCloudFallback, setPendingCorrelationId])

  const handleCloudFallbackAccept = useCallback(() => {
    setCloudFallback(null)
  }, [setCloudFallback])

  return (
    <>
    <AppShell
      onSend={handleSend}
      projects={projects}
      activeProjectId={activeProjectId}
      activeChatId={activeChatId}
      currentThreadId={currentThreadId}
      onSwitchProject={handleSwitchProject}
      onRefreshProjects={() => void loadProjects()}
      onCreateProject={handleCreateProject}
      onEditProject={handleEditProject}
      onDeleteProject={handleDeleteProject}
      onNewChat={handleNewChat}
      onSelectChat={handleSelectChat}
      onDeleteChat={handleDeleteChat}
      onRenameChat={handleRenameChat}
      onHitlApprove={handleHitlApprove}
      onHitlDecline={handleHitlDecline}
      onHitlSelectChoice={handleHitlSelectChoice}
      onHitlSkip={handleHitlSkip}
      onStop={handleStop}
    />
    {cloudFallback && (
      <div
        style={{
          position: 'fixed', inset: 0, zIndex: 9999,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
        }}
      >
        <div
          style={{
            background: '#1a1a2e', border: '1px solid #e94560', borderRadius: 12,
            padding: '28px 32px', maxWidth: 440, width: '90%', color: '#e0e0e0',
            boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
          }}
        >
          <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 12, color: '#e94560' }}>
            Cloud Unavailable
          </div>
          <div style={{ fontSize: 14, lineHeight: 1.6, marginBottom: 8 }}>
            The cloud model could not be reached. A local model generated this response instead.
          </div>
          <div style={{ fontSize: 12, color: '#888', marginBottom: 20, fontFamily: 'monospace' }}>
            Reason: {cloudFallback.reason} &middot; Model: {cloudFallback.fallback_model}
          </div>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
            <button
              onClick={handleCloudFallbackAccept}
              style={{
                padding: '8px 20px', borderRadius: 8, border: '1px solid #444',
                background: '#2a2a3e', color: '#e0e0e0', cursor: 'pointer', fontSize: 14,
              }}
            >
              Accept Local Response
            </button>
            {cloudFallback.can_retry && (
              <button
                onClick={handleCloudFallbackRetry}
                style={{
                  padding: '8px 20px', borderRadius: 8, border: 'none',
                  background: '#e94560', color: '#fff', cursor: 'pointer', fontSize: 14,
                  fontWeight: 600,
                }}
              >
                Retry Cloud
              </button>
            )}
          </div>
        </div>
      </div>
    )}
    </>
  )
}

export default App
