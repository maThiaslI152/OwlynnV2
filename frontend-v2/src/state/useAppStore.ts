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
  duration?: number | null
  riskLabel?: string | null
  riskConfidence?: number | null
  riskRationale?: string | null
  remediationHint?: string | null
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

export interface CloudUsageTurn {
  prompt_tokens: number
  completion_tokens: number
  prompt_cache_hit_tokens?: number
  prompt_cache_miss_tokens?: number
  reasoning_tokens?: number
  model_tier?: string
  model_name?: string
  estimated_cost_usd?: number
  cache_hit_ratio?: number
}

export interface CloudUsageSession {
  prompt_tokens: number
  completion_tokens: number
  prompt_cache_hit_tokens: number
  prompt_cache_miss_tokens: number
  reasoning_tokens: number
  total_tokens: number
  cache_hit_ratio: number
  total_calls: number
  failed_calls: number
  estimated_cost_usd: number
  elapsed_seconds: number
  last_turn?: CloudUsageTurn | null
}

export interface CloudUsageBudget {
  daily_token_limit: number
  used_tokens: number
  remaining_tokens: number | null
  used_pct: number
}

export interface CloudUsageState {
  session: CloudUsageSession
  budget: CloudUsageBudget
  lastTurn: CloudUsageTurn | null
}

export interface ContextBreakdown {
  max_context: number
  categories: {
    system: number
    conversation: number
    tools: number
    output: number
    reasoning: number
  }
  category_pct: {
    system: number
    conversation: number
    tools: number
    output: number
    reasoning: number
  }
  input_estimated: number
  total_used: number
  used_pct: number
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
  screenAssistEnabled: boolean
  actionProposals: ActionProposal[]
  latestToolExecution: ToolExecutionSnapshot | null
  toolExecutionHistory: ToolExecutionSnapshot[]
  operatorNote: string
  routerMetadata: Record<string, unknown> | null
  modelInfo: string | null
  cloudStatus: { available: boolean; key_valid: boolean; model: string; error: string } | null
  cloudUsage: CloudUsageState | null
  contextBreakdown: ContextBreakdown | null
  contextCompression: CompressionInfo | null
  memoryUpdatedAt: number | null
  ttsSpeaking: boolean
  interruptQuestion: string | null
  interruptChoices: InterruptChoice[] | null
  inlineSecurityPrompt: InlineSecurityPrompt | null
  activePersonaId: string
  pendingCorrelationId: string | null
  evalResponseStyle: string | null
  responseStyle: string | null
  browserPageContext: import('../lib/browserPageContext').BrowserPageContext | null
  browserPageContextNonce: number
  coherenceRetryActive: boolean
  coherenceRetryAttempt: number
  coherenceRetryOriginalConfidence: number | null
  cloudFallback: { reason: string; fallback_model: string; can_retry: boolean } | null
  activeMode: 'normal' | 'study' | 'pentest'
  setConnectionState: (state: ConnectionState) => void
  addMessage: (message: ChatMessage) => void
  appendStreamChunk: (chunk: string) => void
  setSafeMode: (mode: SafeModeLevel) => void
  setExecutionPolicy: (policy: ExecutionPolicy) => void
  setWindowMode: (mode: WindowMode) => void
  setScreenAssistMode: (mode: ScreenAssistState['mode']) => void
  setScreenAssistSource: (source: ScreenAssistState['source']) => void
  setScreenAssistPreviewPath: (previewPath: string | null) => void
  setScreenAssistEnabled: (enabled: boolean) => void
  upsertActionProposal: (proposal: ActionProposal) => void
  updateActionProposalStatus: (id: string, status: ActionProposal['status']) => void
  setLatestToolExecution: (tool: ToolExecutionSnapshot | null) => void
  pushToolExecution: (tool: ToolExecutionSnapshot) => void
  setOperatorNote: (note: string) => void
  setRouterMetadata: (meta: Record<string, unknown>) => void
  setModelInfo: (model: string | null) => void
  setCloudStatus: (status: { available: boolean; key_valid: boolean; model: string; error: string } | null) => void
  setCloudUsage: (usage: CloudUsageState | null) => void
  setContextBreakdown: (breakdown: ContextBreakdown | null) => void
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
  setPendingCorrelationId: (id: string | null) => void
  setCoherenceRetryActive: (active: boolean, attempt?: number, confidence?: number | null) => void
  setCloudFallback: (fallback: { reason: string; fallback_model: string; can_retry: boolean } | null) => void
  setEvalResponseStyle: (style: string | null) => void
  setResponseStyle: (style: string | null) => void
  setActiveMode: (mode: 'normal' | 'study' | 'pentest') => void
  applyBrowserPageContext: (ctx: import('../lib/browserPageContext').BrowserPageContext) => void
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
  screenAssistEnabled: false,
  actionProposals: [],
  latestToolExecution: null,
  toolExecutionHistory: [],
  operatorNote: '',
  routerMetadata: null,
  modelInfo: null,
  cloudStatus: null,
  cloudUsage: null,
  contextBreakdown: null,
  contextCompression: null,
  memoryUpdatedAt: null,
  ttsSpeaking: false,
  interruptQuestion: null,
  interruptChoices: null,
  inlineSecurityPrompt: null,
  pendingCorrelationId: null,
  activePersonaId: 'default',
  evalResponseStyle: null,
  responseStyle: null,
  browserPageContext: null,
  browserPageContextNonce: 0,
  coherenceRetryActive: false,
  coherenceRetryAttempt: 0,
  coherenceRetryOriginalConfidence: null,
  cloudFallback: null,
  activeMode: 'normal',
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
  setScreenAssistEnabled: (enabled) => set({ screenAssistEnabled: enabled }),
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
  setCloudStatus: (cloudStatus) => set({ cloudStatus }),
  setCloudUsage: (cloudUsage) => set({ cloudUsage }),
  setContextBreakdown: (contextBreakdown) => set({ contextBreakdown }),
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
      contextBreakdown: null,
      contextCompression: null,
      operatorNote: '',
      ttsSpeaking: false,
      interruptQuestion: null,
      interruptChoices: null,
      inlineSecurityPrompt: null,
      pendingCorrelationId: null,
      coherenceRetryActive: false,
      coherenceRetryAttempt: 0,
      coherenceRetryOriginalConfidence: null,
      cloudFallback: null,
    }),
  setActivePersonaId: (activePersonaId) => set({ activePersonaId }),
  setPendingCorrelationId: (pendingCorrelationId) => set({ pendingCorrelationId }),
  setCoherenceRetryActive: (active, attempt = 1, confidence = null) =>
    set({
      coherenceRetryActive: active,
      coherenceRetryAttempt: active ? attempt : 0,
      coherenceRetryOriginalConfidence: active ? confidence : null,
    }),
  setCloudFallback: (cloudFallback) => set({ cloudFallback }),
  setActiveMode: (activeMode) => set({ activeMode }),
  setEvalResponseStyle: (evalResponseStyle) => set({ evalResponseStyle }),
  setResponseStyle: (responseStyle) => set({ responseStyle }),
  applyBrowserPageContext: (ctx) =>
    set((state) => ({
      browserPageContext: ctx,
      browserPageContextNonce: state.browserPageContextNonce + 1,
      operatorNote: 'Page received from Brave.',
    })),
}))
