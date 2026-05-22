import { useState } from 'react'
import { tauriBridge as defaultBridge } from '../lib/tauriBridge'
import { useAppStore } from '../state/useAppStore'
import type { InterruptChoice } from '../state/useAppStore'

interface ActionProposalQueueProps {
  onApprove?: (id: string) => Promise<void>
  onReject?: (id: string) => Promise<void>
  onSelectChoice?: (choice: InterruptChoice, userInput?: string) => void
  bridge?: {
    approveActionProposal: (id: string) => Promise<{ ok: boolean; error?: string }>
    rejectActionProposal: (id: string) => Promise<{ ok: boolean; error?: string }>
  }
}

export function ActionProposalQueue({ onApprove, onReject, onSelectChoice, bridge }: ActionProposalQueueProps) {
  const proposals = useAppStore((s) => s.actionProposals)
  const updateStatus = useAppStore((s) => s.updateActionProposalStatus)
  const setOperatorNote = useAppStore((s) => s.setOperatorNote)
  const interruptQuestion = useAppStore((s) => s.interruptQuestion)
  const interruptChoices = useAppStore((s) => s.interruptChoices)
  const activeBridge = bridge ?? defaultBridge

  const [othersInput, setOthersInput] = useState('')

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

  const handleChoiceClick = (choice: InterruptChoice) => {
    if (choice.allows_user_input) {
      // Do nothing here — user must type and submit
      return
    }
    onSelectChoice?.(choice)
  }

  const handleOthersSubmit = () => {
    const othersChoice = interruptChoices?.find((c) => c.allows_user_input)
    if (othersChoice && othersInput.trim()) {
      onSelectChoice?.(othersChoice, othersInput.trim())
      setOthersInput('')
    }
  }

  // ── Interrupt choices view (ask_user / skill_ambiguity) ──────────────
  if (interruptQuestion && interruptChoices && interruptChoices.length > 0) {
    const hasOthers = interruptChoices.some((c) => c.allows_user_input)
    return (
      <div>
        <p className="interrupt-question">{interruptQuestion}</p>
        <div className="interrupt-choices">
          {interruptChoices.map((choice, idx) => {
            if (choice.allows_user_input) {
              return null // Rendered separately below
            }
            return (
              <button
                key={idx}
                type="button"
                className="btn-choice"
                onClick={() => handleChoiceClick(choice)}
              >
                {choice.label}
              </button>
            )
          })}
        </div>
        {hasOthers && (
          <div className="interrupt-others">
            <input
              type="text"
              placeholder="Describe what you need..."
              value={othersInput}
              onChange={(e) => setOthersInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleOthersSubmit()
              }}
            />
            <button
              type="button"
              className="btn-others-submit"
              disabled={!othersInput.trim()}
              onClick={handleOthersSubmit}
            >
              Submit
            </button>
          </div>
        )}
      </div>
    )
  }

  // ── Security proposal view (existing) ────────────────────────────────
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
