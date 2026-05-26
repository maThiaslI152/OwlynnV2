export type ConnectionState = 'connecting' | 'connected' | 'disconnected' | 'error'

export interface CloudStatus {
  available: boolean
  key_valid: boolean
  model: string
  error: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  ts: number
}

export interface UserMessageEvent {
  type: 'user.message'
  id: string
  content: string
  message?: string
  project_id?: string
  source?: 'text' | 'voice'
}

export interface SecurityApprovalClientEvent {
  type: 'security_approval'
  approved: boolean
}

export interface AskUserResponseClientEvent {
  type: 'ask_user_response'
  answer: Record<string, unknown>
}

export interface AssistantMessageEvent {
  type: 'assistant.message'
  id?: string
  content?: string
  message?: {
    id?: string
    type?: string
    content?: string
    tool_calls?: unknown[]
    tool_name?: string
    tool_call_id?: string
    model_used?: string
    token_usage?: Record<string, number>
  }
}

// --- Voice events (reserved -- Live Talk removed 2026-04-29, types kept for forward compat) ---
export interface VoiceStateEvent {
  type: 'voice.state'
  state: 'idle' | 'recording' | 'transcribing' | 'speaking' | 'interrupted' | 'approval_pending'
}

export interface VoiceTranscriptEvent {
  type: 'voice.transcript'
  text: string
  is_final: boolean
  confidence?: number
}

export interface VoiceWakeWordEvent {
  type: 'voice.wake_word'
  phrase: string
  confidence?: number
}

export interface VoiceErrorEvent {
  type: 'voice.error'
  message: string
  code?: string
}

export interface VoiceTtsStateEvent {
  type: 'voice.tts_state'
  speaking: boolean
  utterance_id?: string
}

export interface VoiceStartedEvent {
  type: 'voice.started'
  mode: 'wake_word' | 'ptt'
}
// --- End voice events ---

export interface SafeModeChangedEvent {
  type: 'safe_mode.changed'
  mode: 'normal' | 'safe_readonly' | 'safe_confirmed_exec' | 'safe_isolated'
}

export interface ScreenAssistStateEvent {
  type: 'screen_assist.state'
  mode: 'off' | 'preview' | 'annotating'
  source: 'screen' | 'window' | 'region'
  preview_path?: string | null
}

export interface ActionProposalEvent {
  type: 'action.proposal'
  proposal: {
    id: string
    summary: string
    source: 'screen_assist' | 'voice' | 'system'
    created_at: number
    status: 'pending' | 'approved' | 'rejected'
  }
}

export interface ActionProposalResultEvent {
  type: 'action.proposal.result'
  id: string
  status: 'approved' | 'rejected'
}

export interface InterruptEvent {
  type: 'interrupt'
  interrupts: Array<
    | unknown
    | {
        type?: string
        risk_label?: string
        risk_confidence?: number
        risk_rationale?: string
        remediation_hint?: string
        tool_name?: string
        tool_args?: string | null
      }
  >
}

export interface ToolExecutionEvent {
  type: 'tool_execution'
  status: 'running' | 'success' | 'error'
  tool_name: string
  tool_call_id?: string | null
  input?: string | null
  output?: string | null
  error?: string | null
  risk_label?: string
  risk_confidence?: number
  risk_rationale?: string
  remediation_hint?: string
  duration?: number
}

export type ClientEvent = UserMessageEvent | SecurityApprovalClientEvent | AskUserResponseClientEvent

export interface ChunkEvent {
  type: 'chunk'
  content: string
}

export interface StatusEvent {
  type: 'status'
  content: string
}

// Emitted by server.py on graph execution error
export interface ErrorEvent {
  type: 'error'
  content: string
}

// Emitted by server.py notify_file_processed() broadcast
export interface FileStatusEvent {
  type: 'file_status'
  name: string
  status: 'processed' | 'deleted'
}

// Emitted by server.py after streaming completes
export interface TokenBudgetUpdateEvent {
  type: 'token_budget_update'
  used: number
  total: number
  remaining: number
  percent: number
}

// Emitted by server.py when cumulative cloud token usage crosses thresholds
export interface CloudBudgetWarningEvent {
  type: 'cloud_budget_warning'
  used: number
  limit: number
  percent: number
  level: 'info' | 'warning' | 'critical'
}

export type ServerEvent =
  | AssistantMessageEvent
  | ChunkEvent
  | StatusEvent
  | ErrorEvent
  | FileStatusEvent
  | TokenBudgetUpdateEvent
  | CloudBudgetWarningEvent
  | VoiceStateEvent
  | VoiceTranscriptEvent
  | VoiceWakeWordEvent
  | VoiceErrorEvent
  | VoiceTtsStateEvent
  | VoiceStartedEvent
  | SafeModeChangedEvent
  | ScreenAssistStateEvent
  | ActionProposalEvent
  | ActionProposalResultEvent
  | InterruptEvent
  | ToolExecutionEvent
  | RouterInfoEvent
  | ModelInfoEvent
  | ContextSummarizedEvent
  | MemoryUpdatedEvent

export interface RouterInfoEvent {
  type: 'router_info'
  metadata: Record<string, unknown>
}

export interface ModelInfoEvent {
  type: 'model_info'
  model: string
  model_used?: string
  swapping?: boolean
  fallback_chain?: Array<{
    model: string
    status: string
    reason: string
    duration_ms: number
  }>
}

export interface ContextSummarizedEvent {
  type: 'context_summarized'
  summary: string
  takeaways: string[]
  messages_compressed: number
  tokens_freed: number
}

export interface MemoryUpdatedEvent {
  type: 'memory_updated'
  thread_id?: string
}
