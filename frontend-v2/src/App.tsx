import { useEffect, useRef, useState, useCallback } from 'react'
import { listen } from '@tauri-apps/api/event'
import { AppShell } from './components/AppShell'
import { WsClient } from './lib/wsClient'
import { useAppStore } from './state/useAppStore'
import { tauriBridge } from './lib/tauriBridge'
import {
  buildAutoApproveInterruptResponse,
  buildInterruptProposal,
  parseInterruptChoices,
  resolveProjectSwitch,
  toToolExecutionSnapshot,
  type ConversationToolActivity,
} from './appEventHandlers'
import { parseHitlPrompt } from './components/HitlPromptCard'
import type { ChatMessage, ServerEvent } from './types/protocol'

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
  const setRouterMetadata = useAppStore((s) => s.setRouterMetadata)
  const setModelInfo = useAppStore((s) => s.setModelInfo)
  const setContextCompression = useAppStore((s) => s.setContextCompression)
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
  const isTauriRuntime = typeof window !== 'undefined' && Boolean((window as any).__TAURI_INTERNALS__)
  const apiBase = isTauriRuntime ? 'http://127.0.0.1:8000' : ''
  const apiUrl = (path: string) => apiBase + path

  const loadProjects = useCallback(async () => {
    try {
      const response = await fetch('/api/projects' + '?_t=' + Date.now())
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
    } catch (e) {
      console.warn('[loadProjects]', e)
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
    const loadHistory = async () => {
      try {
        const response = await fetch(`/api/history/${encodeURIComponent(currentThreadId)}`)
        if (!response.ok) return
        const history = (await response.json()) as Array<{ type: string; content: string; tool_calls?: unknown[] }>
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
      } catch (e) {
        console.warn('[loadHistory]', e)
        // History unavailable — non-critical
      }
    }

    const wsUrl = `${wsBaseUrl}/${encodeURIComponent(currentThreadId)}`
    const wsClient = new WsClient(wsUrl)
    wsClientRef.current = wsClient
    const disconnect = wsClient.connect({
      onOpen: () => {
        setConnection('connected')
        void loadHistory()
      },
      onClose: () => {
        setConnection('disconnected')
        setLatestToolExecution(null)
      },
      onError: () => setConnection('error'),
      onEvent: (event: ServerEvent) => {
        if (event.type === 'assistant.message') {
          const msg = 'message' in event ? (event as any).message : event
          const finalContent: string = msg.content || ''
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
              toolCallId: snapshot.toolCallId,
              status: snapshot.status,
              input: snapshot.input,
              riskLabel: snapshot.riskLabel,
              riskConfidence: snapshot.riskConfidence,
              riskRationale: snapshot.riskRationale,
              remediationHint: snapshot.remediationHint,
              ts: Date.now(),
              duration: snapshot.duration,
            })
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
        } else if (event.type === 'chunk') {
          const chunkContent = (event as any).content || ''
          if (chunkContent) {
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
        }
      },
    })

    setConnection('connecting')
    return () => {
      disconnect()
      wsClientRef.current = null
    }
  }, [activeProjectId, addMessage, appendStreamChunk, currentThreadId, executionPolicy, pushToolExecution, setConnection, setLatestToolExecution, setMemoryUpdatedAt, setModelInfo, setContextCompression, setOperatorNote, setRouterMetadata, setSafeMode, setScreenAssistMode, setScreenAssistPreviewPath, setScreenAssistSource, setTtsSpeaking, upsertActionProposal, updateActionProposalStatus, isTauriRuntime, wsBaseUrl])

  // Listen for Tauri runtime events (TTS state, screen assist, etc.)
  useEffect(() => {
    let unlisten: (() => void) | undefined
    void listen<TauriEventPayload>('owlynn://runtime-event', (event) => {
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
            toolCallId: snapshot.toolCallId,
            status: snapshot.status,
            input: snapshot.input,
            riskLabel: snapshot.riskLabel,
            riskConfidence: snapshot.riskConfidence,
            riskRationale: snapshot.riskRationale,
            remediationHint: snapshot.remediationHint,
            ts: Date.now(),
            duration: snapshot.duration,
          })
        }
      } else if (payload.type === 'interrupt') {
        handleInterrupt(payload.interrupts)
      }
    }).then((fn) => {
      unlisten = fn
    }).catch(() => {
      // Non-Tauri browser preview mode
    })

    return () => {
      if (unlisten) unlisten()
    }
  }, [addMessage, executionPolicy, handleInterrupt, latestToolExecution, pushToolExecution, setLatestToolExecution, setOperatorNote, setSafeMode, setScreenAssistMode, setScreenAssistPreviewPath, setScreenAssistSource, setTtsSpeaking, upsertActionProposal, updateActionProposalStatus])

  const handleSend = useCallback((content: string) => {
    const activePersonaId = useAppStore.getState().activePersonaId
    const message: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      ts: Date.now(),
    }
    addMessage(message)
    wsClientRef.current?.send({
      type: 'user.message',
      id: message.id,
      content: message.content,
      message: message.content,
      project_id: activeProjectId,
      persona_id: activePersonaId,
    })
  }, [addMessage, activeProjectId])

  // ── Inline HITL card callbacks ────────────────────────────────────
  const handleHitlApprove = useCallback((hitlId: string, variant: string, answers?: Record<string, unknown>) => {
    const store = useAppStore.getState()
    if (variant === 'security_approval') {
      wsClientRef.current?.send({ type: 'security_approval', approved: true })
      store.updateConversationItemStatus(hitlId, 'approved')
    } else if (variant === 'plan_review') {
      wsClientRef.current?.send({ type: 'plan_review_response', approved: true })
      store.updateConversationItemStatus(hitlId, 'approved')
    } else if (variant === 'scope_clarification') {
      wsClientRef.current?.send({
        type: 'ask_user_response',
        answer: answers || { skipped: false },
      })
      store.updateConversationItemStatus(hitlId, 'approved')
    } else if (variant === 'ask_user') {
      store.updateConversationItemStatus(hitlId, 'approved')
    }
    setOperatorNote('Action approved.')
  }, [])

  const handleHitlDecline = useCallback((hitlId: string) => {
    wsClientRef.current?.send({ type: 'security_approval', approved: false })
    useAppStore.getState().updateConversationItemStatus(hitlId, 'rejected')
    setOperatorNote('Action declined.')
  }, [])

  const handleHitlSelectChoice = useCallback((choice: import('./state/useAppStore').InterruptChoice, userInput?: string) => {
    const answer: Record<string, unknown> = { ...choice }
    if (userInput !== undefined) {
      answer.user_input = userInput
    }
    wsClientRef.current?.send({
      type: 'ask_user_response',
      answer: answer,
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
    wsClientRef.current?.send({
      type: 'ask_user_response',
      answer: { skipped: true },
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
  }, [activeProjectId, currentThreadId, clearSession])

  const handleNewChat = useCallback(() => {
    const newThreadId = makeThreadId()
    const updatedThreads = { ...projectThreadsRef.current, [activeProjectId]: newThreadId }
    projectThreadsRef.current = updatedThreads
    clearSession()
    setCurrentThreadId(newThreadId)
    setActiveChatId(newThreadId)
    setOperatorNote('New conversation started.')
  }, [activeProjectId, clearSession])

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
  }, [activeProjectId, activeChatId, clearSession])

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
      setOperatorNote('Failed to delete workspace.')
    }
  }, [clearSession, loadProjects])  // activeProjectId removed — uses ref for latest value

  return (
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
    />
  )
}

export default App
