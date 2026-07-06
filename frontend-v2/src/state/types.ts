

export type SafeModeLevel = 'normal' | 'safe_readonly' | 'safe_confirmed_exec' | 'safe_isolated'
export type ExecutionPolicy = 'hitl' | 'auto_approve'
export type WindowMode = 'full' | 'compact'

export interface ScreenAssistState {
  mode: 'off' | 'preview' | 'annotating'
  source: 'screen' | 'window' | 'region'
  previewPath: string | null
}

export interface ToolExecutionSnapshot {
  toolName: string
  ts: number
  input?: string | null
  toolCallId?: string | null
  batchId?: string | null
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

export interface PentestVmStatus {
  installed: boolean
  running: boolean
  vm_name: string
}

export interface ActivityFeedItem {
  id: string
  type: 'tool_running' | 'tool_success' | 'tool_error' | 'agent_message' | 'hitl_prompt' | 'phase_change'
  batchId?: string | null
  toolName?: string
  toolCallId?: string
  summary: string
  output?: string
  error?: string
  duration?: number | null
  ts: number
  riskLabel?: string | null
}
