import { useEffect, useRef, useState, useCallback } from 'react'
import { listen } from '@tauri-apps/api/event'
import { AppShell } from './components/AppShell'
import { WsClient } from './lib/wsClient'
import { useAppStore } from './state/useAppStore'
import { tauriBridge } from './lib/tauriBridge'
import {
  buildAutoApproveInterruptResponse,
  buildInterruptProposal,
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
  const setVoiceState = useAppStore((s) => s.setVoiceState)
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
  const setInterimTranscript = useAppStore((s) => s.setInterimTranscript)
  const setVoiceError = useAppStore((s) => s.setVoiceError)
  const setWakeWordListening = useAppStore((s) => s.setWakeWordListening)
  const setTtsSpeaking = useAppStore((s) => s.setTtsSpeaking)
  const wakeWordListening = useAppStore((s) => s.wakeWordListening)
  const appendStreamChunk = useAppStore((s) => s.appendStreamChunk)
  const clearSession = useAppStore((s) => s.clearSession)
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [activeProjectId, setActiveProjectId] = useState('default')
  const [activeChatId, setActiveChatId] = useState('default')
  const [currentThreadId, setCurrentThreadId] = useState('default')
  const projectThreadsRef = useRef<Record<string, string>>({ default: 'default' })
  const wsClientRef = useRef<WsClient | null>(null)

  const makeThreadId = () => `thread-${crypto.randomUUID()}`

  const loadProjects = useCallback(async () => {
    try {
      const response = await fetch('/api/projects')
      if (!response.ok) return
      const payload = (await response.json()) as ProjectSummary[]
      // Only keep the minimal shape: id, name, chats (with id, name, created_at)
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
      const activeExists = mapped.some((project) => project.id === activeProjectId)
      if (!activeExists) {
        const first = mapped[0]
        const existingThread = projectThreadsRef.current[first.id] ?? makeThreadId()
        projectThreadsRef.current[first.id] = existingThread
        setActiveProjectId(first.id)
        setCurrentThreadId(existingThread)
        setActiveChatId(existingThread)
      } else {
        // Sync thread IDs with the actual chat data from the API
        const activeProject = mapped.find((p) => p.id === activeProjectId)
        if (activeProject && activeProject.chats.length > 0) {
          // Use the most recent chat's ID as the current thread
          const sorted = [...activeProject.chats].sort((a, b) => (b.created_at ?? 0) - (a.created_at ?? 0))
          const latestChatId = sorted[0].id
          projectThreadsRef.current[activeProjectId] = latestChatId
          setCurrentThreadId(latestChatId)
          setActiveChatId(latestChatId)
        } else {
          setActiveChatId(currentThreadId)
        }
      }
    } catch {
      setProjects([{ id: 'default', name: 'General Workspace', chats: [] }])
    }
  }, [activeProjectId, currentThreadId])

  const handleInterrupt = useCallback((interrupts: unknown[] | undefined) => {
    if (executionPolicy === 'auto_approve') {
      const autoApprove = buildAutoApproveInterruptResponse()
      wsClientRef.current?.send(autoApprove.clientEvent)
      setOperatorNote(autoApprove.operatorNote)
      return
    }

    const proposal = buildInterruptProposal(interrupts, latestToolExecution, Date.now())
    upsertActionProposal(proposal)
    setOperatorNote('Approval required: sensitive action waiting for decision.')
  }, [executionPolicy, latestToolExecution, wsClientRef])

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
    // Fetch existing chat history for the current thread
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
          void loadProjects()
          // Check if the last message is a streaming placeholder; if so, replace it
          // to avoid duplicating content that was already streamed via chunk events.
          const msgs = useAppStore.getState().messages
          const last = msgs[msgs.length - 1]
          if (last && last.role === 'assistant' && last.id?.startsWith('stream-')) {
            // Grab any extra content streamed after assistant.message was sent
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
          if (wakeWordListening && finalContent.trim()) {
            void tauriBridge.speakText(finalContent.trim())
          }
        } else if (event.type === 'voice.state') {
          setVoiceState(event.state)
        } else if (event.type === 'voice.transcript') {
          setInterimTranscript(event.text)
          if (event.is_final && event.text.trim()) {
            const voiceMsg: ChatMessage = {
              id: crypto.randomUUID(),
              role: 'user',
              content: event.text.trim(),
              ts: Date.now(),
            }
            addMessage(voiceMsg)
            wsClientRef.current?.send({
              type: 'user.message',
              id: voiceMsg.id,
              content: voiceMsg.content,
              message: voiceMsg.content,
              project_id: activeProjectId,
              source: 'voice',
            })
          }
        } else if (event.type === 'voice.wake_word') {
          setVoiceState('recording')
          setOperatorNote(`Wake-word detected: ${event.phrase}`)
        } else if (event.type === 'voice.error') {
          setVoiceError(event.message)
          setOperatorNote(`Live Talk error: ${event.message}`)
        } else if (event.type === 'voice.tts_state') {
          setTtsSpeaking(event.speaking)
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
          handleInterrupt(event.interrupts)
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
  }, [activeProjectId, addMessage, appendStreamChunk, currentThreadId, executionPolicy, handleInterrupt, latestToolExecution, loadProjects, pushToolExecution, setConnection, setLatestToolExecution, setMemoryUpdatedAt, setModelInfo, setContextCompression, setInterimTranscript, setOperatorNote, setRouterMetadata, setSafeMode, setScreenAssistMode, setScreenAssistPreviewPath, setScreenAssistSource, setTtsSpeaking, setVoiceError, setVoiceState, upsertActionProposal, updateActionProposalStatus, wakeWordListening, wsBaseUrl])

  useEffect(() => {
    let unlisten: (() => void) | undefined
    void listen<TauriEventPayload>('owlynn://runtime-event', (event) => {
      const payload = event.payload
      if (payload.type === 'voice.state') {
        setVoiceState(payload.state)
      } else if (payload.type === 'voice.transcript') {
        setInterimTranscript(payload.text)
        if (payload.is_final && payload.text.trim()) {
          const voiceMsg: ChatMessage = {
            id: crypto.randomUUID(),
            role: 'user',
            content: payload.text.trim(),
            ts: Date.now(),
          }
          addMessage(voiceMsg)
          wsClientRef.current?.send({
            type: 'user.message',
            id: voiceMsg.id,
            content: voiceMsg.content,
            message: voiceMsg.content,
            project_id: activeProjectId,
            source: 'voice',
          })
        }
      } else if (payload.type === 'voice.wake_word') {
        setVoiceState('recording')
        setOperatorNote(`Wake-word detected: ${payload.phrase}`)
      } else if (payload.type === 'voice.error') {
        setVoiceError(payload.message)
        setOperatorNote(`Live Talk error: ${payload.message}`)
      } else if (payload.type === 'voice.tts_state') {
        setTtsSpeaking(payload.speaking)
      } else if (payload.type === 'voice.started') {
        setWakeWordListening(payload.mode === 'wake_word')
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
  }, [activeProjectId, addMessage, executionPolicy, handleInterrupt, latestToolExecution, pushToolExecution, setInterimTranscript, setLatestToolExecution, setOperatorNote, setSafeMode, setScreenAssistMode, setScreenAssistPreviewPath, setScreenAssistSource, setTtsSpeaking, setVoiceError, setVoiceState, setWakeWordListening, upsertActionProposal, updateActionProposalStatus])

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
    void loadProjects()
  }, [addMessage, activeProjectId, currentThreadId, loadProjects])

  const handleApproveProposal = async (id: string) => {
    wsClientRef.current?.send({
      type: 'security_approval',
      approved: true,
    })
    updateActionProposalStatus(id, 'approved')
    setOperatorNote(`Proposal ${id} approved and sent to backend`)
  }

  const handleRejectProposal = async (id: string) => {
    wsClientRef.current?.send({
      type: 'security_approval',
      approved: false,
    })
    updateActionProposalStatus(id, 'rejected')
    setOperatorNote(`Proposal ${id} rejected and sent to backend`)
  }

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

  // New chat: create a fresh thread within the current project
  const handleNewChat = useCallback(() => {
    const newThreadId = makeThreadId()
    const updatedThreads = { ...projectThreadsRef.current, [activeProjectId]: newThreadId }
    projectThreadsRef.current = updatedThreads
    clearSession()
    // Don't update activeChatId yet — the backend will register this thread on first message
    setCurrentThreadId(newThreadId)
    setActiveChatId(newThreadId)
    setOperatorNote('New conversation started.')
  }, [activeProjectId, clearSession])

  // Delete a chat: remove from project and switch if needed
  const handleDeleteChat = useCallback(async (chatId: string) => {
    try {
      await fetch(`/api/projects/${encodeURIComponent(activeProjectId)}/chats/${encodeURIComponent(chatId)}`, {
        method: 'DELETE',
      })
      // Refresh projects to get updated chat list
      await loadProjects()
      // If we deleted the active chat, create a new one
      if (chatId === activeChatId) {
        handleNewChat()
      } else {
        setOperatorNote(`Chat ${chatId} deleted.`)
      }
    } catch {
      setOperatorNote('Failed to delete chat.')
    }
  }, [activeProjectId, activeChatId, loadProjects, handleNewChat])

  // Rename a chat: update name via backend
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

  // Navigate to a specific chat
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
      const response = await fetch('/api/projects', {
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
    } catch {
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
      const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}`, {
        method: 'DELETE',
      })
      if (!response.ok) throw new Error('delete failed')
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
    } catch {
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
      onNewChat={handleNewChat}
      onSelectChat={handleSelectChat}
      onDeleteChat={handleDeleteChat}
      onRenameChat={handleRenameChat}
    />
  )
}

export default App
