/**
 * HitlPromptCard — inline card in the chat timeline for HITL interrupts.
 *
 * Renders a unified card for all interrupt types:
 *  - scope_clarification_required
 *  - plan_review_required
 *  - security_approval_required
 *  - ask_user (single question)
 *
 * Replaces sidebar InterruptChoicesInline and composer-adjacent security prompts.
 */

import { useState } from 'react'

interface ChoiceOption {
  label: string
  route?: string
  toolbox?: string[]
  skill_name?: string | null
  allows_user_input?: boolean
}

interface ScopeQuestion {
  id: string
  question: string
  choices: ChoiceOption[]
  allows_user_input?: boolean
}

export interface HitlPromptViewModel {
  /** Interrupt type identifier */
  variant: 'scope_clarification' | 'plan_review' | 'security_approval' | 'ask_user'
  /** Short title for the card header */
  title: string
  /** User's original request (truncated) */
  conversationSnippet?: string
  /** What Owlynn wants to do */
  statedIntent?: string
  /** Tool calls being reviewed */
  plannedActions?: Array<{ tool: string; summary: string }>
  /** Risks / pitfalls */
  pitfalls?: string[]
  /** Multi-question scope clarification */
  questions?: ScopeQuestion[]
  /** Scope clarification: task description */
  task_summary?: string
  /** Security-specific: tool name being blocked */
  toolName?: string
  /** Security-specific: risk details */
  riskLabel?: string
  riskRationale?: string
  remediationHint?: string
  /** ask_user: single question + choices */
  question?: string
  choices?: ChoiceOption[]
}

interface HitlPromptCardProps {
  model: HitlPromptViewModel
  status: 'pending' | 'approved' | 'rejected' | 'dismissed'
  onApprove?: (answers?: Record<string, unknown>) => void
  onDecline?: () => void
  onSelectChoice?: (choice: ChoiceOption, userInput?: string) => void
  onSkip?: () => void
}

export function HitlPromptCard({
  model,
  status,
  onApprove,
  onDecline,
  onSelectChoice,
  onSkip,
}: HitlPromptCardProps) {
  const [scopeAnswers, setScopeAnswers] = useState<Record<string, { label: string; userInput?: string }>>({})
  const [freeInputs, setFreeInputs] = useState<Record<string, string>>({})
  const [selectedChoice, setSelectedChoice] = useState<ChoiceOption | null>(null)

  if (status !== 'pending') {
    const label = status === 'approved' ? 'Approved' : status === 'rejected' ? 'Declined' : 'Dismissed'
    return (
      <div className={`hitl-resolved-chip hitl-resolved-${status}`}>
        <span className="hitl-resolved-icon">{status === 'approved' ? '✓' : status === 'rejected' ? '✗' : '—'}</span>
        <span>{label}: {model.title}</span>
      </div>
    )
  }

  // ── Scope clarification (multi-question) ─────────────────────────
  if (model.variant === 'scope_clarification' && model.questions) {
    return (
      <div className="hitl-prompt-card hitl-pending">
        <div className="hitl-prompt-header">
          <strong>Clarify Scope</strong>
          <span className="hitl-prompt-badge">Before building</span>
        </div>
        {model.task_summary && <p className="hitl-prompt-intent">{model.task_summary}</p>}
        {model.pitfalls && model.pitfalls.length > 0 && (
          <div className="hitl-prompt-pitfalls">
            <strong>Why this matters:</strong>
            <ul>
              {model.pitfalls.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          </div>
        )}
        <div className="hitl-prompt-questions">
          {model.questions.map((q) => (
            <div key={q.id} className="hitl-scope-question">
              <label>{q.question}</label>
              <div className="hitl-scope-choices">
                {q.choices.map((c, ci) => (
                  <button
                    key={ci}
                    className={`hitl-choice-btn${scopeAnswers[q.id]?.label === c.label ? ' selected' : ''}`}
                    onClick={() => setScopeAnswers((prev) => ({ ...prev, [q.id]: c }))}
                  >
                    {c.label}
                  </button>
                ))}
              </div>
              {q.allows_user_input && (
                <input
                  className="hitl-free-input"
                  placeholder="Or type your own..."
                  value={freeInputs[q.id] || ''}
                  onChange={(e) =>
                    setFreeInputs((prev) => ({ ...prev, [q.id]: e.target.value }))
                  }
                />
              )}
            </div>
          ))}
        </div>
        <div className="hitl-prompt-actions">
          <button
            className="hitl-btn-approve"
            onClick={() => {
              const answers: Record<string, unknown> = {}
              for (const qid of Object.keys(scopeAnswers)) {
                answers[qid] = {
                  label: scopeAnswers[qid].label,
                  user_input: freeInputs[qid] || undefined,
                }
              }
              onApprove?.(answers)
            }}
          >
            Submit Answers
          </button>
          <button className="hitl-btn-skip" onClick={onSkip}>
            Skip — use your best judgment
          </button>
        </div>
      </div>
    )
  }

  // ── Plan review ──────────────────────────────────────────────────
  if (model.variant === 'plan_review') {
    return (
      <div className="hitl-prompt-card hitl-pending">
        <div className="hitl-prompt-header">
          <strong>Plan Review</strong>
          <span className="hitl-prompt-badge hitl-badge-warn">Approval required</span>
        </div>
        {model.statedIntent && <p className="hitl-prompt-intent">{model.statedIntent}</p>}
        {model.plannedActions && model.plannedActions.length > 0 && (
          <div className="hitl-prompt-actions-list">
            <strong>Planned actions:</strong>
            <ul>
              {model.plannedActions.map((a, i) => (
                <li key={i}><code>{a.tool}</code> — {a.summary}</li>
              ))}
            </ul>
          </div>
        )}
        {model.pitfalls && model.pitfalls.length > 0 && (
          <div className="hitl-prompt-pitfalls">
            <strong>Risks to consider:</strong>
            <ul>
              {model.pitfalls.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          </div>
        )}
        <div className="hitl-prompt-actions">
          <button className="hitl-btn-approve" onClick={() => onApprove?.()}>
            Approve Plan
          </button>
          <button className="hitl-btn-decline" onClick={onDecline}>
            Decline
          </button>
        </div>
      </div>
    )
  }

  // ── Security approval ────────────────────────────────────────────
  if (model.variant === 'security_approval') {
    return (
      <div className="hitl-prompt-card hitl-pending">
        <div className="hitl-prompt-header">
          <strong>Security Check</strong>
          <span className="hitl-prompt-badge hitl-badge-danger">{model.riskLabel || 'sensitive'}</span>
        </div>
        {model.statedIntent && <p className="hitl-prompt-intent">{model.statedIntent}</p>}
        <p className="hitl-prompt-tool"><code>{model.toolName || 'unknown tool'}</code></p>
        {model.riskRationale && <p className="hitl-prompt-risk">{model.riskRationale}</p>}
        {model.remediationHint && <p className="hitl-prompt-remediation">Tip: {model.remediationHint}</p>}
        <div className="hitl-prompt-actions">
          <button className="hitl-btn-approve" onClick={() => onApprove?.()}>
            Allow
          </button>
          <button className="hitl-btn-decline" onClick={onDecline}>
            Block
          </button>
        </div>
      </div>
    )
  }

  // ── ask_user (single question) ───────────────────────────────────
  if (model.variant === 'ask_user') {
    const choices = model.choices || []
    const hasInputChoice = choices.some((c) => c.allows_user_input)
    return (
      <div className="hitl-prompt-card hitl-pending">
        <div className="hitl-prompt-header">
          <strong>Question</strong>
        </div>
        <p className="hitl-prompt-intent">{model.question || 'Clarification needed'}</p>
        <div className="hitl-prompt-choices">
          {choices.map((c, i) => (
            <button
              key={i}
              className={`hitl-choice-btn${selectedChoice?.label === c.label ? ' selected' : ''}`}
              onClick={() => setSelectedChoice(c)}
            >
              {c.label}
            </button>
          ))}
        </div>
        {hasInputChoice && selectedChoice?.allows_user_input && (
          <input
            className="hitl-free-input"
            placeholder="Describe what you need..."
            onChange={(e) =>
              setFreeInputs((prev) => ({ ...prev, _other: e.target.value }))
            }
          />
        )}
        <div className="hitl-prompt-actions">
          <button
            className="hitl-btn-approve"
            disabled={!selectedChoice}
            onClick={() => selectedChoice && onSelectChoice?.(selectedChoice, freeInputs._other)}
          >
            Confirm Choice
          </button>
        </div>
      </div>
    )
  }

  return null
}

/**
 * Parse raw interrupts array into a HitlPromptViewModel or null.
 */
export function parseHitlPrompt(interrupts: unknown[] | undefined): HitlPromptViewModel | null {
  if (!interrupts || interrupts.length === 0) return null

  const primary = interrupts[0]
  if (typeof primary !== 'object' || primary === null) return null

  const p = primary as Record<string, unknown>
  const type = String(p.type || '')

  if (type === 'scope_clarification_required') {
    return {
      variant: 'scope_clarification',
      title: String(p.task_summary || 'Scope clarification'),
      task_summary: String(p.task_summary || ''),
      conversationSnippet: String(p.conversation_snippet || ''),
      questions: Array.isArray(p.questions) ? p.questions as ScopeQuestion[] : [],
      pitfalls: Array.isArray(p.pitfalls) ? p.pitfalls as string[] : [],
    }
  }

  if (type === 'plan_review_required') {
    return {
      variant: 'plan_review',
      title: String(p.title || 'Plan review'),
      statedIntent: String(p.stated_intent || ''),
      conversationSnippet: String(p.conversation_snippet || ''),
      plannedActions: Array.isArray(p.planned_actions) ? p.planned_actions as Array<{ tool: string; summary: string }> : [],
      pitfalls: Array.isArray(p.pitfalls) ? p.pitfalls as string[] : [],
    }
  }

  if (type === 'security_approval_required') {
    return {
      variant: 'security_approval',
      title: String(p.title || 'Security check'),
      statedIntent: String(p.stated_intent || p.conversation_snippet || ''),
      toolName: String(p.tool_name || ''),
      riskLabel: String(p.risk_label || 'sensitive'),
      riskRationale: String(p.risk_rationale || ''),
      remediationHint: String(p.remediation_hint || ''),
    }
  }

  if (type === 'ask_user') {
    const choices: ChoiceOption[] = Array.isArray(p.choices)
      ? p.choices.map((c: unknown) => {
          if (typeof c !== 'object' || c === null) return { label: String(c) }
          const co = c as Record<string, unknown>
          return {
            label: String(co.label || ''),
            route: typeof co.route === 'string' ? co.route : undefined,
            toolbox: Array.isArray(co.toolbox) ? co.toolbox as string[] : undefined,
            skill_name: co.skill_name != null ? String(co.skill_name) : undefined,
            allows_user_input: co.allows_user_input === true,
          }
        })
      : []
    return {
      variant: 'ask_user',
      title: String(p.question || 'Clarification needed'),
      question: String(p.question || ''),
      choices,
      conversationSnippet: String(p.conversation_snippet || ''),
    }
  }

  return null
}
