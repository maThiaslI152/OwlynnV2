import { create } from 'zustand'
import type { ChatMessage, ConnectionState } from '../types/protocol'

// crypto.randomUUID() polyfill for environments where it's not available
function uuid() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })
}

export type VoiceState =
  | 'idle'
  | 'recording'
  | 'transcribing'
  | 'speaking'
  | 'interrupted'
  | 'approval_pending'

export type SafeModeLevel = 'normal' | 'safe_readonly' | 'safe_confirmed_exec' | 'safe_isolated'
export type ExecutionPolicy = 'hitl' | 'auto_approve'
export type WindowMode = 'full' | 'compact'

interface ScreenAssistState {
  mode: 'off' | 'preview' | 'annotating'
  source: 'screen' | 'window' | 'region'
  previewPath: string | null
}

export interface ToolExecutionSnapshot {
  toolName: string
  ts: number
  input?: string | null
  toolCallId?: string | null
  status: 'running' | 'success' | 'error'
  duration?: number
  riskLabel?: string
  riskConfidence?: number
  riskRationale?: string
  remediationHint?: string
}

export interface ActionProposal {
  id: string
  summary: string
  source: 'screen_assist' | 'voice' | 'system'
  created_at: number
  status: 'pending' | 'approved' | 'rejected'
  backendInterrupt?: unknown
  toolContext?: ToolExecutionSnapshot
  riskHint?: string
  riskRationale?: string
  remediationHint?: string
}

export interface CompressionInfo {
  summary: string
  takeaways: string[]
  messagesCompressed: number
  tokensFreed: number
}

interface AppState {
  connectionState: ConnectionState
  messages: ChatMessage[]
  voiceState: VoiceState
  safeMode: SafeModeLevel
  executionPolicy: ExecutionPolicy
  windowMode: WindowMode
  screenAssist: ScreenAssistState
  actionProposals: ActionProposal[]
  latestToolExecution: ToolExecutionSnapshot | null
  toolExecutionHistory: ToolExecutionSnapshot[]
  operatorNote: string
  routerMetadata: Record<string, unknown> | null
  modelInfo: string | null
  contextCompression: CompressionInfo | null
  memoryUpdatedAt: number | null
  interimTranscript: string
  voiceError: string | null
  wakeWordListening: boolean
  ttsSpeaking: boolean
  wakeWordPhrase: string
  setConnectionState: (state: ConnectionState) => void
  addMessage: (message: ChatMessage) => void
  appendStreamChunk: (chunk: string) => void
  setVoiceState: (state: VoiceState) => void
  setSafeMode: (mode: SafeModeLevel) => void
  setExecutionPolicy: (policy: ExecutionPolicy) => void
  setWindowMode: (mode: WindowMode) => void
  setScreenAssistMode: (mode: ScreenAssistState['mode']) => void
  setScreenAssistSource: (source: ScreenAssistState['source']) => void
  setScreenAssistPreviewPath: (previewPath: string | null) => void
  upsertActionProposal: (proposal: ActionProposal) => void
  updateActionProposalStatus: (id: string, status: ActionProposal['status']) => void
  setLatestToolExecution: (tool: ToolExecutionSnapshot | null) => void
  pushToolExecution: (tool: ToolExecutionSnapshot) => void
  setOperatorNote: (note: string) => void
  setRouterMetadata: (meta: Record<string, unknown>) => void
  setModelInfo: (model: string | null) => void
  setContextCompression: (info: CompressionInfo | null) => void
  setMemoryUpdatedAt: (ts: number) => void
  setInterimTranscript: (text: string) => void
  setVoiceError: (message: string | null) => void
  setWakeWordListening: (active: boolean) => void
  setTtsSpeaking: (speaking: boolean) => void
  setWakeWordPhrase: (phrase: string) => void
  clearSession: () => void
}

export const useAppStore = create<AppState>((set) => ({
  connectionState: 'disconnected',
  messages: [],
  voiceState: 'idle',
  safeMode: 'normal',
  executionPolicy: 'auto_approve',
  windowMode: 'full',
  screenAssist: {
    mode: 'off',
    source: 'screen',
    previewPath: null,
  },
  actionProposals: [],
  latestToolExecution: null,
  toolExecutionHistory: [],
  operatorNote: '',
  routerMetadata: null,
  modelInfo: null,
  contextCompression: null,
  memoryUpdatedAt: null,
  interimTranscript: '',
  voiceError: null,
  wakeWordListening: false,
  ttsSpeaking: false,
  wakeWordPhrase: 'Athena',
  setConnectionState: (connectionState) => set({ connectionState }),
  addMessage: (message) =>
    set((state) => ({
      messages: [...state.messages, message],
    })),
  appendStreamChunk: (chunk) =>
    set((state) => {
      const messages = [...state.messages]
      const last = messages[messages.length - 1]
      if (last && last.role === 'assistant') {
        messages[messages.length - 1] = { ...last, content: last.content + chunk }
      } else {
        messages.push({
          id: `stream-${uuid()}`,
          role: 'assistant',
          content: chunk,
          ts: Date.now(),
        })
      }
      return { messages }
    }),
  setVoiceState: (voiceState) => set({ voiceState }),
  setSafeMode: (safeMode) => set({ safeMode }),
  setExecutionPolicy: (executionPolicy) => set({ executionPolicy }),
  setWindowMode: (windowMode) => set({ windowMode }),
  setScreenAssistMode: (mode) =>
    set((state) => ({
      screenAssist: {
        ...state.screenAssist,
        mode,
      },
    })),
  setScreenAssistSource: (source) =>
    set((state) => ({
      screenAssist: {
        ...state.screenAssist,
        source,
      },
    })),
  setScreenAssistPreviewPath: (previewPath) =>
    set((state) => ({
      screenAssist: {
        ...state.screenAssist,
        previewPath,
      },
    })),
  upsertActionProposal: (proposal) =>
    set((state) => {
      const existing = state.actionProposals.find((p) => p.id === proposal.id)
      if (!existing) {
        return { actionProposals: [proposal, ...state.actionProposals] }
      }
      return {
        actionProposals: state.actionProposals.map((p) => (p.id === proposal.id ? proposal : p)),
      }
    }),
  updateActionProposalStatus: (id, status) =>
    set((state) => ({
      actionProposals: state.actionProposals.map((p) =>
        p.id === id ? { ...p, status } : p
      ),
    })),
  setLatestToolExecution: (latestToolExecution) => set({ latestToolExecution }),
  pushToolExecution: (tool) =>
    set((state) => {
      const history = [...state.toolExecutionHistory]
      const key = tool.toolCallId || `${tool.toolName}-${tool.status}`
      const idx = history.findIndex(
        (entry) => (entry.toolCallId || `${entry.toolName}-${entry.status}`) === key
      )
      if (idx >= 0) {
        history[idx] = tool
      } else {
        history.unshift(tool)
      }
      return {
        latestToolExecution: tool,
        toolExecutionHistory: history.slice(0, 25),
      }
    }),
  setOperatorNote: (operatorNote) => set({ operatorNote }),
  setRouterMetadata: (routerMetadata) => set({ routerMetadata }),
  setModelInfo: (modelInfo) => set({ modelInfo }),
  setContextCompression: (contextCompression) => set({ contextCompression }),
  setMemoryUpdatedAt: (memoryUpdatedAt) => set({ memoryUpdatedAt }),
  setInterimTranscript: (interimTranscript) => set({ interimTranscript }),
  setVoiceError: (voiceError) => set({ voiceError }),
  setWakeWordListening: (wakeWordListening) => set({ wakeWordListening }),
  setTtsSpeaking: (ttsSpeaking) => set({ ttsSpeaking }),
  setWakeWordPhrase: (wakeWordPhrase) => set({ wakeWordPhrase }),
  clearSession: () =>
    set({
      messages: [],
      toolExecutionHistory: [],
      latestToolExecution: null,
      actionProposals: [],
      routerMetadata: null,
      modelInfo: null,
      contextCompression: null,
      operatorNote: '',
      interimTranscript: '',
      voiceError: null,
      ttsSpeaking: false,
    }),
}))
