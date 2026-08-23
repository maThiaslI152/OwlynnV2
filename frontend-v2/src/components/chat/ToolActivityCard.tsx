/**
 * ToolActivityCard — inline card in the chat timeline showing tool execution status.
 *
 * Replaces the sidebar ToolExecutionPanel live view. Compact row with:
 *  - Icon + tool name + status chip (running / success / error)
 *  - Optional risk badge
 *  - Expand chevron for args snippet
 */

import { useState, type ReactNode } from 'react'
import { Check, X, RotateCw, ChevronDown, ChevronRight } from 'lucide-react'

export interface ToolActivitySnapshot {
  id: string
  toolName: string
  toolCallId?: string | null
  status: 'running' | 'success' | 'error'
  input?: string | null
  duration?: number | null
  riskLabel?: string | null
  riskConfidence?: number | null
  riskRationale?: string | null
  remediationHint?: string | null
}

interface ToolActivityCardProps {
  activity: ToolActivitySnapshot
  onExportAudit?: () => void
}

function statusIcon(status: ToolActivitySnapshot['status']): ReactNode {
  switch (status) {
    case 'running':
      return <RotateCw size={12} className="spinning" />
    case 'success':
      return <Check size={12} />
    case 'error':
      return <X size={12} />
  }
}

export function ToolActivityCard({ activity, onExportAudit }: ToolActivityCardProps) {
  const [expanded, setExpanded] = useState(false)
  const statusClass = `tool-activity-${activity.status}`

  return (
    <div className={`tool-activity-card ${statusClass}`}>
      <div className="tool-activity-row" onClick={() => setExpanded(!expanded)}>
        <span className="tool-activity-icon">{statusIcon(activity.status)}</span>
        <span className="tool-activity-name">
          <code>{activity.toolName}</code>
        </span>
        <span className={`tool-activity-chip ${statusClass}`}>{activity.status}</span>
        {activity.riskLabel && (
          <span className="tool-activity-risk">{activity.riskLabel}</span>
        )}
        {activity.duration != null && (
          <span className="tool-activity-duration">{(activity.duration / 1000).toFixed(1)}s</span>
        )}
        <span className="tool-activity-chevron">{expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}</span>
      </div>
      {expanded && (
        <div className="tool-activity-details">
          {activity.input && (
            <div className="tool-activity-input">
              <strong>Input:</strong>
              <pre>{activity.input}</pre>
            </div>
          )}
          {activity.riskRationale && (
            <div className="tool-activity-risk-detail">
              <strong>Risk:</strong> {activity.riskRationale}
            </div>
          )}
          {activity.remediationHint && (
            <div className="tool-activity-remediation">
              <strong>Tip:</strong> {activity.remediationHint}
            </div>
          )}
          {onExportAudit && (
            <button className="tool-activity-audit-btn" onClick={onExportAudit}>
              Export Audit
            </button>
          )}
        </div>
      )}
    </div>
  )
}
