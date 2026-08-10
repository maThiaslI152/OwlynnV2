import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { useAppStore } from '../../state/useAppStore'
import { ActionProposalQueue } from '../shared/ActionProposalQueue'

// Note: ToolExecutionPanel is not tested here because it depends heavily on
// browser-only APIs (crypto.subtle, Clipboard API, Blob, URL.createObjectURL)
// that are not available in vitest's node environment and would require
// significant polyfilling beyond the scope of this regression slice.

beforeEach(() => {
  vi.clearAllMocks()
  useAppStore.setState(useAppStore.getInitialState(), true)
  ;(window as any).electronAPI = {
    invoke: vi.fn(),
    on: vi.fn(),
  }
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ActionProposalQueue regression', () => {
  it('renders empty state when no proposals exist', () => {
    render(<ActionProposalQueue />)
    expect(screen.getByText('No pending proposals.')).toBeTruthy()
  })

  it('renders pending proposals with approve/reject buttons', () => {
    useAppStore.getState().upsertActionProposal({
      id: 'p-1',
      summary: 'Approve delete_workspace_file execution',
      source: 'system',
      created_at: 1000,
      status: 'pending',
      riskHint: 'destructive_action (98%)',
      riskRationale: 'delete semantics',
      remediationHint: 'backup first',
    })

    render(<ActionProposalQueue />)

    expect(screen.getByText('Approve delete_workspace_file execution')).toBeTruthy()
    expect(screen.getByText((content) => content.includes('destructive_action'))).toBeTruthy()
    expect(screen.getByText('Approve')).toBeTruthy()
    expect(screen.getByText('Reject')).toBeTruthy()
  })

  it('shows tool context when available', () => {
    useAppStore.getState().upsertActionProposal({
      id: 'p-2',
      summary: 'Approve custom tool',
      source: 'system',
      created_at: 2000,
      status: 'pending',
      toolContext: {
        toolName: 'read_workspace_file',
        ts: 2000,
        input: '{"path":"README.md"}',
        status: 'running',
      },
    })

    render(<ActionProposalQueue />)
    expect(screen.getByText(/read_workspace_file/)).toBeTruthy()
  })

  it('hides approve/reject buttons for non-pending proposals', () => {
    useAppStore.getState().upsertActionProposal({
      id: 'p-3',
      summary: 'Approved proposal',
      source: 'system',
      created_at: 3000,
      status: 'approved',
    })

    render(<ActionProposalQueue />)
    expect(screen.getByText('Approved proposal')).toBeTruthy()
    expect(screen.queryByText('Approve')).toBeNull()
    expect(screen.queryByText('Reject')).toBeNull()
  })

  it('calls onApprove when provided instead of bridge', async () => {
    const onApprove = vi.fn().mockResolvedValue(undefined)

    useAppStore.getState().upsertActionProposal({
      id: 'p-4',
      summary: 'Approve with callback',
      source: 'system',
      created_at: 4000,
      status: 'pending',
    })

    render(<ActionProposalQueue onApprove={onApprove} />)

    fireEvent.click(screen.getByText('Approve'))
    expect(onApprove).toHaveBeenCalledWith('p-4')

    // Wait for async and check store updated
    await vi.waitFor(() => {
      const proposal = useAppStore.getState().actionProposals.find((p) => p.id === 'p-4')
      expect(proposal?.status).toBe('approved')
    })
  })

  it('calls onReject when provided instead of bridge', async () => {
    const onReject = vi.fn().mockResolvedValue(undefined)

    useAppStore.getState().upsertActionProposal({
      id: 'p-5',
      summary: 'Reject with callback',
      source: 'system',
      created_at: 5000,
      status: 'pending',
    })

    render(<ActionProposalQueue onReject={onReject} />)

    fireEvent.click(screen.getByText('Reject'))
    expect(onReject).toHaveBeenCalledWith('p-5')

    await vi.waitFor(() => {
      const proposal = useAppStore.getState().actionProposals.find((p) => p.id === 'p-5')
      expect(proposal?.status).toBe('rejected')
    })
  })

  it('uses injected bridge when no onApprove/onReject callbacks', async () => {
    const mockBridge = {
      approveActionProposal: vi.fn().mockResolvedValue({ ok: true }),
      rejectActionProposal: vi.fn().mockResolvedValue({ ok: true }),
    }

    useAppStore.getState().upsertActionProposal({
      id: 'p-6',
      summary: 'Approve via bridge',
      source: 'system',
      created_at: 6000,
      status: 'pending',
    })

    render(<ActionProposalQueue bridge={mockBridge} />)

    fireEvent.click(screen.getByText('Approve'))
    expect(mockBridge.approveActionProposal).toHaveBeenCalledWith('p-6')

    await vi.waitFor(() => {
      expect(useAppStore.getState().operatorNote).toContain('approved')
    })
  })

  it('shows bridge error note on approve failure', async () => {
    const mockBridge = {
      approveActionProposal: vi.fn().mockResolvedValue({ ok: false, error: 'bridge not available' }),
      rejectActionProposal: vi.fn().mockResolvedValue({ ok: true }),
    }

    useAppStore.getState().upsertActionProposal({
      id: 'p-7',
      summary: 'Fail via bridge',
      source: 'system',
      created_at: 7000,
      status: 'pending',
    })

    render(<ActionProposalQueue bridge={mockBridge} />)

    fireEvent.click(screen.getByText('Approve'))

    await vi.waitFor(() => {
      expect(useAppStore.getState().operatorNote).toContain('Proposal error')
    })
  })
})

