export type ConnectionState = 'connecting' | 'connected' | 'disconnected' | 'error'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  ts: number
}

export interface UserMessageEvent {
  type: 'user.message'
  correlation_id?: string
  id: string
  content: string
  message?: string
  project_id?: string
  persona_id?: string
  source?: 'text' | 'voice'
}

export interface SecurityApprovalClientEvent {
  type: 'security_approval'
  approved: boolean
  correlation_id?: string
}

export interface AskUserResponseClientEvent {
  type: 'ask_user_response'
  answer: Record<string, unknown>
  correlation_id?: string
}

export interface PlanReviewResponseClientEvent {
  type: 'plan_review_response'
  approved: boolean
  feedback?: string
  correlation_id?: string
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

export type ClientEvent = UserMessageEvent | SecurityApprovalClientEvent | AskUserResponseClientEvent | PlanReviewResponseClientEvent
export interface ChunkEvent {
  type: 'chunk'
  content: string
}

export interface StatusEvent {
  type: 'status'
  content: string
}

export type ServerEvent =
  | AssistantMessageEvent
  | ChunkEvent
  | StatusEvent
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
