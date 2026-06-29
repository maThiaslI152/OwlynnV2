import type { ActionProposal, ToolExecutionSnapshot, InterruptChoice } from './state/useAppStore'
import type { SecurityApprovalClientEvent, ToolExecutionEvent } from './types/protocol'

export function deriveRiskHint(toolName?: string, input?: string | null): string {
  const hay = `${toolName ?? ''} ${input ?? ''}`.toLowerCase()
  if (hay.includes('delete') || hay.includes('rm ') || hay.includes('drop ')) return 'destructive-action risk'
  if (hay.includes('sudo') || hay.includes('chmod') || hay.includes('chown')) return 'privilege escalation risk'
  if (hay.includes('curl') || hay.includes('wget') || hay.includes('http')) return 'network exfiltration risk'
  return 'manual approval required'
}

export function toToolExecutionSnapshot(
  event: ToolExecutionEvent,
  now: number
): ToolExecutionSnapshot {
  return {
    toolName: event.tool_name,
    ts: now,
    input: event.input ?? null,
    toolCallId: event.tool_call_id ?? null,
    batchId: event.batch_id ?? null,
    status: event.status,
    duration: event.duration ?? null,
    riskLabel: event.risk_label ?? null,
    riskConfidence: event.risk_confidence ?? null,
    riskRationale: event.risk_rationale ?? null,
    remediationHint: event.remediation_hint ?? null,
  }
}

// ── Conversation timeline model ──────────────────────────────────────

export type ConversationItemKind = 'message' | 'tool_activity' | 'hitl_prompt' | 'chart_embed'

export interface ConversationMessage {
  kind: 'message'
  id: string
  role: 'user' | 'assistant'
  content: string
  ts: number
}

export interface ConversationToolActivity {
  kind: 'tool_activity'
  id: string
  toolName: string
  toolCallId: string | null
  input: string | null
  status: 'running' | 'success' | 'error'
  duration?: number | null
  riskLabel?: string | null
  riskConfidence?: number | null
  riskRationale?: string | null
  remediationHint?: string | null
  chartArtifact?: {
    filename: string
    url: string
    kind: 'interactive' | 'static'
    mimeType: string
  }
  ts: number
}

export type HitlPromptStatus = 'pending' | 'approved' | 'rejected' | 'dismissed'

export interface ConversationHitlPrompt {
  kind: 'hitl_prompt'
  id: string
  variant: 'scope_clarification' | 'plan_review' | 'security_approval' | 'ask_user'
  title: string
  viewModel: Record<string, unknown>
  status: HitlPromptStatus
  ts: number
}

export interface ConversationChartEmbed {
  kind: 'chart_embed'
  id: string
  url: string
  filename: string
  chartKind: 'interactive' | 'static'
  mimeType: string
  toolCallId?: string | null
  ts: number
}

export type ConversationItem =
  | ConversationMessage
  | ConversationToolActivity
  | ConversationHitlPrompt
  | ConversationChartEmbed

/** Build a timeline chart embed item from a successful notebook_run tool event. */
export function buildChartEmbedItem(
  event: ToolExecutionEvent,
  now: number,
): ConversationChartEmbed | null {
  const artifact = event.chart_artifact
  if (event.status !== 'success' || !artifact) return null
  return {
    kind: 'chart_embed',
    id: event.tool_call_id ? `chart-${event.tool_call_id}` : `chart-${now}`,
    url: artifact.url,
    filename: artifact.filename,
    chartKind: artifact.kind,
    mimeType: artifact.mime_type,
    toolCallId: event.tool_call_id ?? null,
    ts: now,
  }
}

type InterruptMetadata = {
  backendToolName: string
  backendToolArgs: string | null
  backendRiskLabel: string
  backendRiskConfidence: number | null
  backendRiskRationale: string
  backendRemediationHint: string
  primaryInterrupt: unknown
}

function getInterruptMetadata(interrupts: unknown[] | undefined): InterruptMetadata {
  const primaryInterrupt = interrupts?.[0]
  const backendToolName =
    typeof primaryInterrupt === 'object' && primaryInterrupt !== null && 'tool_name' in primaryInterrupt
      ? String((primaryInterrupt as { tool_name?: string }).tool_name ?? '')
      : ''
  const backendToolArgs =
    typeof primaryInterrupt === 'object' && primaryInterrupt !== null && 'tool_args' in primaryInterrupt
      ? ((primaryInterrupt as { tool_args?: string | null }).tool_args ?? null)
      : null
  const backendRiskLabel =
    typeof primaryInterrupt === 'object' && primaryInterrupt !== null && 'risk_label' in primaryInterrupt
      ? String((primaryInterrupt as { risk_label?: string }).risk_label ?? '')
      : ''
  const backendRiskConfidence =
    typeof primaryInterrupt === 'object' &&
    primaryInterrupt !== null &&
    'risk_confidence' in primaryInterrupt &&
    typeof (primaryInterrupt as { risk_confidence?: number }).risk_confidence === 'number'
      ? ((primaryInterrupt as { risk_confidence?: number }).risk_confidence ?? null)
      : null
  const backendRiskRationale =
    typeof primaryInterrupt === 'object' && primaryInterrupt !== null && 'risk_rationale' in primaryInterrupt
      ? String((primaryInterrupt as { risk_rationale?: string }).risk_rationale ?? '')
      : ''
  const backendRemediationHint =
    typeof primaryInterrupt === 'object' && primaryInterrupt !== null && 'remediation_hint' in primaryInterrupt
      ? String((primaryInterrupt as { remediation_hint?: string }).remediation_hint ?? '')
      : ''

  return {
    backendToolName,
    backendToolArgs,
    backendRiskLabel,
    backendRiskConfidence,
    backendRiskRationale,
    backendRemediationHint,
    primaryInterrupt,
  }
}

export function buildInterruptProposal(
  interrupts: unknown[] | undefined,
  latestToolExecution: ToolExecutionSnapshot | null,
  now: number
): ActionProposal {
  const meta = getInterruptMetadata(interrupts)
  const backendRiskConfidencePct =
    typeof meta.backendRiskConfidence === 'number' ? Math.round(meta.backendRiskConfidence * 100) : null
  const proposalId = `interrupt-${now}`

  return {
    id: proposalId,
    summary: meta.backendToolName
      ? `Approve ${meta.backendToolName} execution`
      : latestToolExecution
        ? `Approve ${latestToolExecution.toolName} execution`
        : 'Security approval required before executing sensitive action',
    source: 'system',
    created_at: now,
    status: 'pending',
    backendInterrupt: meta.primaryInterrupt,
    toolContext: meta.backendToolName
      ? {
          toolName: meta.backendToolName,
          ts: now,
          input: meta.backendToolArgs,
          status: 'running',
        }
      : (latestToolExecution ?? undefined),
    riskHint: meta.backendRiskLabel
      ? `${meta.backendRiskLabel}${backendRiskConfidencePct !== null ? ` (${backendRiskConfidencePct}%)` : ''}`
      : deriveRiskHint(latestToolExecution?.toolName, latestToolExecution?.input),
    riskRationale: meta.backendRiskRationale || undefined,
    remediationHint: meta.backendRemediationHint || undefined,
  }
}

export function buildAutoApproveInterruptResponse(): {
  clientEvent: SecurityApprovalClientEvent
  operatorNote: string
} {
  return {
    clientEvent: { type: 'security_approval', approved: true },
    operatorNote: 'Auto-approved interrupt (no HITL mode).',
  }
}

export function resolveProjectSwitch(params: {
  activeProjectId: string
  currentThreadId: string
  targetProjectId: string
  projectThreads: Record<string, string>
  makeThreadId: () => string
}):
  | null
  | {
      nextActiveProjectId: string
      nextCurrentThreadId: string
      nextProjectThreads: Record<string, string>
      operatorNote: string
    } {
  const { activeProjectId, currentThreadId, targetProjectId, projectThreads, makeThreadId } = params
  if (targetProjectId === activeProjectId) return null

  const nextProjectThreads = { ...projectThreads, [activeProjectId]: currentThreadId }
  const nextThreadId = nextProjectThreads[targetProjectId] ?? makeThreadId()
  nextProjectThreads[targetProjectId] = nextThreadId

  return {
    nextActiveProjectId: targetProjectId,
    nextCurrentThreadId: nextThreadId,
    nextProjectThreads,
    operatorNote: `Switched to project ${targetProjectId}`,
  }
}

export interface AskUserInterrupt {
  question: string
  choices: InterruptChoice[]
}

/**
 * Detect and parse an ask_user / skill_ambiguity interrupt from the raw
 * interrupts array. Returns null if this is a security-style interrupt.
 */
export function parseInterruptChoices(
  interrupts: unknown[] | undefined,
): AskUserInterrupt | null {
  if (!interrupts || interrupts.length === 0) return null

  const primary = interrupts[0]
  if (typeof primary !== 'object' || primary === null) return null

  const typed = primary as Record<string, unknown>
  // Only handle ask_user type (includes skill_ambiguity sent as ask_user)
  if (typed.type !== 'ask_user') return null

  const question = typeof typed.question === 'string' ? typed.question : ''
  const rawChoices = Array.isArray(typed.choices) ? typed.choices : []

  const choices: InterruptChoice[] = rawChoices.map((c: unknown) => {
    if (typeof c !== 'object' || c === null) {
      return { label: String(c) }
    }
    const choice = c as Record<string, unknown>
    return {
      label: typeof choice.label === 'string' ? choice.label : String(choice.label ?? ''),
      route: typeof choice.route === 'string' ? choice.route : undefined,
      toolbox: Array.isArray(choice.toolbox) ? choice.toolbox as string[] : undefined,
      skill_name: choice.skill_name != null ? String(choice.skill_name) : undefined,
      allows_user_input: choice.allows_user_input === true,
    }
  })

  return { question, choices }
}
