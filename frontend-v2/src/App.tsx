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
} from './appEventHandlers'
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
  const setInterruptPrompt = useAppStore((s) => s.setInterruptPrompt)
  const clearInterruptPrompt = useAppStore((s) => s.clearInterruptPrompt)
  const inlineSecurityPrompt = useAppStore((s) => s.inlineSecurityPrompt)
  const setInlineSecurityPrompt = useAppStore((s) => s.setInlineSecurityPrompt)
  const clearInlineSecurityPrompt = useAppStore((s) => s.clearInlineSecurityPrompt)
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
    } catch {
      setProjects([{ id: 'default', name: 'General Workspace', chats: [] }])
    }
  }, [])

  const handleInterrupt = useCallback((interrupts: unknown[] | undefined) => {
    if (executionPolicy === 'auto_approve') {
      const autoApprove = buildAutoApproveInterruptResponse()
      wsClientRef.current?.send(autoApprove.clientEvent)
      setOperatorNote(autoApprove.operatorNote)
      return
    }

    const askUser = parseInterruptChoices(interrupts)
    if (askUser) {
      setInterruptPrompt(askUser.question, askUser.choices)
      setOperatorNote('Clarification needed: choose an option to continue.')
      return
    }

    const proposal = buildInterruptProposal(interrupts, latestToolExecution, Date.now())
    // Also keep in sidebar as historical log
    upsertActionProposal(proposal)
    // Show inline prompt in chat area
    setInlineSecurityPrompt({
      id: proposal.id,
      summary: proposal.summary,
      toolName: proposal.toolContext?.toolName,
      riskHint: proposal.riskHint,
      riskRationale: proposal.riskRationale,
      backendInterrupt: proposal.backendInterrupt,
    })
    setOperatorNote('Security approval required — see prompt below.')
  }, [executionPolicy, latestToolExecution, wsClientRef, setInterruptPrompt, setInlineSecurityPrompt, setOperatorNote, upsertActionProposal])

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
      } catch {
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
      } catch {
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
      onClose: () => setConnection('disconnected'),
      onError: () => setConnection('error'),
      onEvent: (event: ServerEvent) => {
        if (event.type === 'assistant.message') {
          const msg = 'message' in event ? (event as any).message : event
          const finalContent: string = msg.content || ''
          loadProjectsRef.current()
          const msgs = useAppStore.getState().messages
          const last = msgs[msgs.length - 1]
          if (last && last.role === 'assistant' && last.id?.startsWith('stream-')) {
            const currentContent = useAppStore.getState().messages[msgs.length - 1]?.content || ''
            const hasNewerStreamContent = currentContent.length > (last.content?.length || 0)
            useAppStore.setState({
              messages: msgs.map((m, idx) =>
                idx === msgs.length - 1
                  ? {
                      id: msg.id || crypto.randomUUID(),
                      role: 'assistant',
                      content: hasNewerStreamContent ? currentContent : finalContent,
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
        } else if (event.type === 'interrupt') {
          handleInterruptRef.current(event.interrupts)
        } else if (event.type === 'router_info') {
          setRouterMetadata(event.metadata as Record<string, unknown>)
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
    })
  }, [addMessage, activeProjectId])

  const handleApproveProposal = async (id: string) => {
    wsClientRef.current?.send({
      type: 'security_approval',
      approved: true,
    })
    updateActionProposalStatus(id, 'approved')
    clearInlineSecurityPrompt()
    setOperatorNote(`Proposal ${id} approved and sent to backend`)
  }

  const handleRejectProposal = async (id: string) => {
    wsClientRef.current?.send({
      type: 'security_approval',
      approved: false,
    })
    updateActionProposalStatus(id, 'rejected')
    clearInlineSecurityPrompt()
    setOperatorNote(`Proposal ${id} rejected and sent to backend`)
  }

  const handleAutoApprove = async (proposalId: string) => {
    wsClientRef.current?.send({
      type: 'security_approval',
      approved: true,
    })
    try {
      await fetch(apiUrl('/api/unified-settings'), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ execution_policy: 'auto_approve' }),
      })
    } catch {
      // Non-critical — policy update failed but approval was sent
    }
    updateActionProposalStatus(proposalId, 'approved')
    setExecutionPolicy('auto_approve')
    clearInlineSecurityPrompt()
    setOperatorNote('Auto-approve enabled. Future sensitive tools will run without prompts.')
  }

  const handleSelectChoice = useCallback((choice: import('./state/useAppStore').InterruptChoice, userInput?: string) => {
    const answer: Record<string, unknown> = { ...choice }
    if (userInput !== undefined) {
      answer.user_input = userInput
    }
    wsClientRef.current?.send({
      type: 'ask_user_response',
      answer: answer,
    })
    clearInterruptPrompt()
    setOperatorNote('Choice sent — resuming conversation.')
  }, [clearInterruptPrompt, setOperatorNote])

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
        setOperatorNote(`Chat ${chatId} deleted.`)
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
    } catch {
      // non-critical
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
    } catch {
      // non-critical
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
      if (projectId === activeProjectId) {
        const fallbackThreadId = projectThreadsRef.current.default ?? makeThreadId()
        projectThreadsRef.current = { ...projectThreadsRef.current, default: fallbackThreadId }
        clearSession()
        setActiveProjectId('default')
        setCurrentThreadId(fallbackThreadId)
        setActiveChatId(fallbackThreadId)
        setOperatorNote('Workspace deleted. Switched to default workspace.')
      }
      await loadProjects()
    } catch (e: any) {
      setOperatorNote('Failed to delete workspace.')
    }
  }, [activeProjectId, clearSession, loadProjects])

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
      onApproveProposal={handleApproveProposal}
      onRejectProposal={handleRejectProposal}
      onAutoApprove={handleAutoApprove}
      onSelectChoice={handleSelectChoice}
      onNewChat={handleNewChat}
      onSelectChat={handleSelectChat}
      onDeleteChat={handleDeleteChat}
      onRenameChat={handleRenameChat}
      inlineSecurityPrompt={inlineSecurityPrompt}
    />
  )
}

export default App
