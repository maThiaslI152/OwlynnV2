import { create } from 'zustand'
import type { ChatMessage, ConnectionState } from '../types/protocol'
import type { ConversationItem, ConversationHitlPrompt, ConversationToolActivity } from '../appEventHandlers'

// crypto.randomUUID() polyfill for environments where it's not available
function uuid() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })
}

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

export interface InterruptChoice {
  label: string
  route?: string
  toolbox?: string[]
  skill_name?: string | null
  allows_user_input?: boolean
}

export interface InlineSecurityPrompt {
  id: string
  summary: string
  toolName?: string
  riskHint?: string
  riskRationale?: string
  backendInterrupt?: unknown
}

interface AppState {
  connectionState: ConnectionState
  messages: ChatMessage[]
  conversationItems: ConversationItem[]
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
  ttsSpeaking: boolean
  interruptQuestion: string | null
  interruptChoices: InterruptChoice[] | null
  inlineSecurityPrompt: InlineSecurityPrompt | null
  activePersonaId: string
  setConnectionState: (state: ConnectionState) => void
  addMessage: (message: ChatMessage) => void
  appendStreamChunk: (chunk: string) => void
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
  setTtsSpeaking: (speaking: boolean) => void
  setInterruptPrompt: (question: string | null, choices: InterruptChoice[] | null) => void
  clearInterruptPrompt: () => void
  setInlineSecurityPrompt: (prompt: InlineSecurityPrompt | null) => void
  clearInlineSecurityPrompt: () => void
  appendConversationItem: (item: ConversationItem) => void
  updateConversationItemStatus: (id: string, status: 'pending' | 'approved' | 'rejected' | 'dismissed' | 'running' | 'success' | 'error') => void
  clearSession: () => void
  setActivePersonaId: (id: string) => void
}

export const useAppStore = create<AppState>((set) => ({
  connectionState: 'disconnected',
  messages: [],
  conversationItems: [],
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
  ttsSpeaking: false,
  interruptQuestion: null,
  interruptChoices: null,
  inlineSecurityPrompt: null,
  activePersonaId: 'default',
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
  setTtsSpeaking: (ttsSpeaking) => set({ ttsSpeaking }),
  setInterruptPrompt: (interruptQuestion, interruptChoices) =>
    set({ interruptQuestion, interruptChoices }),
  clearInterruptPrompt: () =>
    set({ interruptQuestion: null, interruptChoices: null }),
  setInlineSecurityPrompt: (inlineSecurityPrompt) => set({ inlineSecurityPrompt }),
  clearInlineSecurityPrompt: () => set({ inlineSecurityPrompt: null }),
  appendConversationItem: (item) =>
    set((state) => ({
      conversationItems: [...state.conversationItems, item],
    })),
  updateConversationItemStatus: (id, status) =>
    set((state) => ({
      conversationItems: state.conversationItems.map((item) =>
        item.kind === 'hitl_prompt' && item.id === id
          ? { ...item, status: status as ConversationHitlPrompt['status'] }
          : item.kind === 'tool_activity' && item.id === id
            ? { ...item, status: status as ConversationToolActivity['status'] }
            : item
      ),
    })),
  clearSession: () =>
    set({
      messages: [],
      conversationItems: [],
      toolExecutionHistory: [],
      latestToolExecution: null,
      actionProposals: [],
      routerMetadata: null,
      modelInfo: null,
      contextCompression: null,
      operatorNote: '',
      ttsSpeaking: false,
      interruptQuestion: null,
      interruptChoices: null,
      inlineSecurityPrompt: null,
    }),
  setActivePersonaId: (activePersonaId) => set({ activePersonaId }),
}))
