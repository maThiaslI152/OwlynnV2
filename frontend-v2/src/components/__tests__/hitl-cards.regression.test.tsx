import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { HitlPromptCard, type HitlPromptViewModel } from '../chat/HitlPromptCard'
import { ToolActivityCard, type ToolActivitySnapshot } from '../chat/ToolActivityCard'

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ── HitlPromptCard regression ─────────────────────────────────────────────

describe('HitlPromptCard — scope_clarification', () => {
  const model: HitlPromptViewModel = {
    variant: 'scope_clarification',
    title: 'Build a calculator',
    task_summary: 'Build a calculator application',
    questions: [
      {
        id: 'language',
        question: 'Which language?',
        choices: [{ label: 'Python' }, { label: 'JavaScript' }],
        allows_user_input: true,
      },
      {
        id: 'ui',
        question: 'What interface?',
        choices: [{ label: 'CLI' }, { label: 'GUI' }],
        allows_user_input: false,
      },
    ],
    pitfalls: ['Wrong stack wastes a full pass.'],
  }

  it('renders scope clarification questions and choices', () => {
    render(<HitlPromptCard model={model} status="pending" />)
    expect(screen.getByText('Clarify Scope')).toBeTruthy()
    expect(screen.getByText('Build a calculator application')).toBeTruthy()
    expect(screen.getByText('Which language?')).toBeTruthy()
    expect(screen.getByText('Python')).toBeTruthy()
    expect(screen.getByText('JavaScript')).toBeTruthy()
  })

  it('shows submit and skip buttons', () => {
    render(<HitlPromptCard model={model} status="pending" />)
    expect(screen.getByText('Submit Answers')).toBeTruthy()
    expect(screen.getByText(/Skip/)).toBeTruthy()
  })

  it('renders resolved chip when approved', () => {
    render(<HitlPromptCard model={model} status="approved" />)
    expect(screen.getByText(/Approved/)).toBeTruthy()
  })
})

describe('HitlPromptCard — plan_review', () => {
  const model: HitlPromptViewModel = {
    variant: 'plan_review',
    title: 'Plan review',
    statedIntent: 'Write auth module',
    plannedActions: [
      { tool: 'write_workspace_file', summary: 'Create auth.py' },
      { tool: 'edit_workspace_file', summary: 'Update app.py' },
    ],
    pitfalls: ['Hardcoding credentials'],
  }

  it('renders plan review with planned actions and pitfalls', () => {
    render(<HitlPromptCard model={model} status="pending" />)
    expect(screen.getByText('Plan Review')).toBeTruthy()
    expect(screen.getByText('Write auth module')).toBeTruthy()
    expect(screen.getByText(/Create auth.py/)).toBeTruthy()
    expect(screen.getByText(/Update app.py/)).toBeTruthy()
    expect(screen.getByText('Hardcoding credentials')).toBeTruthy()
  })

  it('shows approve and decline buttons', () => {
    render(<HitlPromptCard model={model} status="pending" />)
    expect(screen.getByText('Approve Plan')).toBeTruthy()
    expect(screen.getByText('Decline')).toBeTruthy()
  })

  it('calls onApprove when approve button clicked', () => {
    const onApprove = vi.fn()
    render(<HitlPromptCard model={model} status="pending" onApprove={onApprove} />)
    fireEvent.click(screen.getByText('Approve Plan'))
    expect(onApprove).toHaveBeenCalledOnce()
  })

  it('renders resolved chip when rejected', () => {
    render(<HitlPromptCard model={model} status="rejected" />)
    expect(screen.getByText(/Declined/)).toBeTruthy()
  })
})

describe('HitlPromptCard — security_approval', () => {
  const model: HitlPromptViewModel = {
    variant: 'security_approval',
    title: 'Security check',
    toolName: 'delete_workspace_file',
    riskLabel: 'destructive_action',
    riskRationale: 'Delete semantics detected.',
    remediationHint: 'Backup first.',
  }

  it('renders security approval with risk details', () => {
    render(<HitlPromptCard model={model} status="pending" />)
    expect(screen.getByText('Security Check')).toBeTruthy()
    expect(screen.getByText(/destructive_action/)).toBeTruthy()
    expect(screen.getByText('Delete semantics detected.')).toBeTruthy()
    expect(screen.getByText(/Backup first/)).toBeTruthy()
  })

  it('shows allow and block buttons', () => {
    render(<HitlPromptCard model={model} status="pending" />)
    expect(screen.getByText('Allow')).toBeTruthy()
    expect(screen.getByText('Block')).toBeTruthy()
  })

  it('calls onDecline when block button clicked', () => {
    const onDecline = vi.fn()
    render(<HitlPromptCard model={model} status="pending" onDecline={onDecline} />)
    fireEvent.click(screen.getByText('Block'))
    expect(onDecline).toHaveBeenCalledOnce()
  })
})

describe('HitlPromptCard — ask_user', () => {
  const model: HitlPromptViewModel = {
    variant: 'ask_user',
    title: 'Clarification needed',
    question: 'Which skill should I use?',
    choices: [
      { label: 'Web Search' },
      { label: 'Code Analysis' },
      { label: 'Other', allows_user_input: true },
    ],
  }

  it('renders question and choices', () => {
    render(<HitlPromptCard model={model} status="pending" />)
    expect(screen.getByText('Question')).toBeTruthy()
    expect(screen.getByText('Which skill should I use?')).toBeTruthy()
    expect(screen.getByText('Web Search')).toBeTruthy()
    expect(screen.getByText('Code Analysis')).toBeTruthy()
  })

  it('confirm button is disabled until a choice is selected', () => {
    render(<HitlPromptCard model={model} status="pending" />)
    const btn = screen.getByText('Confirm Choice')
    expect((btn as HTMLButtonElement).disabled).toBe(true)
  })

  it('shows resolved chip when dismissed', () => {
    render(<HitlPromptCard model={model} status="dismissed" />)
    expect(screen.getByText(/Dismissed/)).toBeTruthy()
  })
})

// ── ToolActivityCard regression ────────────────────────────────────────────

describe('ToolActivityCard', () => {
  it('renders running tool card', () => {
    const activity: ToolActivitySnapshot = {
      id: 'tool-1',
      toolName: 'read_workspace_file',
      status: 'running',
      riskLabel: 'info',
    }
    render(<ToolActivityCard activity={activity} />)
    expect(screen.getByText('read_workspace_file')).toBeTruthy()
    expect(screen.getByText('running')).toBeTruthy()
  })

  it('renders success tool card with duration', () => {
    const activity: ToolActivitySnapshot = {
      id: 'tool-2',
      toolName: 'web_search',
      status: 'success',
      duration: 1500,
    }
    render(<ToolActivityCard activity={activity} />)
    expect(screen.getByText('success')).toBeTruthy()
  })

  it('renders error tool card', () => {
    const activity: ToolActivitySnapshot = {
      id: 'tool-3',
      toolName: 'delete_workspace_file',
      status: 'error',
      riskLabel: 'destructive_action',
    }
    render(<ToolActivityCard activity={activity} />)
    expect(screen.getByText('error')).toBeTruthy()
    expect(screen.getByText('destructive_action')).toBeTruthy()
  })

  it('expands to show input details on click', () => {
    const activity: ToolActivitySnapshot = {
      id: 'tool-4',
      toolName: 'write_workspace_file',
      status: 'success',
      input: '{"filename": "test.py", "content": "print(1)"}',
    }
    render(<ToolActivityCard activity={activity} />)
    // Click the row to expand
    fireEvent.click(screen.getByText('write_workspace_file'))
    expect(screen.getByText('Input:')).toBeTruthy()
    expect(screen.getByText(/print\(1\)/)).toBeTruthy()
  })

  it('shows export audit button when onExportAudit provided', () => {
    const onExportAudit = vi.fn()
    const activity: ToolActivitySnapshot = {
      id: 'tool-5',
      toolName: 'read_workspace_file',
      status: 'success',
    }
    render(<ToolActivityCard activity={activity} onExportAudit={onExportAudit} />)
    fireEvent.click(screen.getByText('read_workspace_file'))
    const btn = screen.getByText('Export Audit')
    expect(btn).toBeTruthy()
    fireEvent.click(btn)
    expect(onExportAudit).toHaveBeenCalledOnce()
  })
})
