import { electronBridge as defaultBridge } from '../../lib/electronBridge'
import { useAppStore } from '../../state/useAppStore'
import type { InterruptChoice } from '../../state/useAppStore'

interface ActionProposalQueueProps {
  onApprove?: (id: string) => Promise<void>
  onReject?: (id: string) => Promise<void>
  onSelectChoice?: (choice: InterruptChoice, userInput?: string) => void
  bridge?: {
    approveActionProposal: (id: string) => Promise<{ ok: boolean; error?: string }>
    rejectActionProposal: (id: string) => Promise<{ ok: boolean; error?: string }>
  }
}

export function ActionProposalQueue({ onApprove, onReject, bridge }: ActionProposalQueueProps) {
  const proposals = useAppStore((s) => s.actionProposals)
  const updateStatus = useAppStore((s) => s.updateActionProposalStatus)
  const setOperatorNote = useAppStore((s) => s.setOperatorNote)
  const activeBridge = bridge ?? defaultBridge

  const approve = async (id: string) => {
    if (onApprove) { await onApprove(id); updateStatus(id, 'approved'); return }
    const result = await activeBridge.approveActionProposal(id)
    if (!result.ok) { setOperatorNote(`Proposal error: ${result.error}`); return }
    updateStatus(id, 'approved')
    setOperatorNote(`Proposal approved`)
  }

  const reject = async (id: string) => {
    if (onReject) { await onReject(id); updateStatus(id, 'rejected'); return }
    const result = await activeBridge.rejectActionProposal(id)
    if (!result.ok) { setOperatorNote(`Proposal error: ${result.error}`); return }
    updateStatus(id, 'rejected')
    setOperatorNote(`Proposal rejected`)
  }

  // ── Security proposal view ────────────────────────────────────────────
  return (
    <div>
      {proposals.length === 0 ? (
        <p className="empty">No pending proposals.</p>
      ) : (
        <div className="proposal-list">
          {proposals.map((proposal) => (
            <div key={proposal.id} className="proposal-item">
              <p><strong>{proposal.summary}</strong></p>
              <p className="meta">{proposal.source} · {proposal.status}</p>
              {proposal.toolContext ? (
                <p className="meta">Tool: {proposal.toolContext.toolName}</p>
              ) : null}
              {proposal.riskHint ? <p className="meta">Risk: {proposal.riskHint}</p> : null}
              {proposal.riskRationale ? <p className="meta">Rationale: {proposal.riskRationale}</p> : null}
              {proposal.status === 'pending' ? (
                <div className="proposal-actions">
                  <button type="button" className="btn-approve" onClick={() => approve(proposal.id)}>
                    Approve
                  </button>
                  <button type="button" className="btn-reject" onClick={() => reject(proposal.id)}>
                    Reject
                  </button>
                </div>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
