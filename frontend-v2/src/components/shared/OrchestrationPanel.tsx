import { useAppStore } from '../../state/useAppStore'
import { ScreenAssistLivePanel } from '../pentest/ScreenAssistLivePanel'

function formatModelBadge(raw: string): string {
  let name = raw
  if (name.startsWith('local-fallback(') && name.endsWith(')')) {
    name = name.slice('local-fallback('.length, -1)
  }
  if (name.startsWith('small-local-fallback(') && name.endsWith(')')) {
    name = name.slice('small-local-fallback('.length, -1)
  }
  if (name.includes('gemma-4-12b-agentic')) {
    const quantMatch = name.match(/@(q[0-9]_[a-z0-9_]+)/i)
    return quantMatch ? `gemma-4-12b-agentic@${quantMatch[1]}` : 'gemma-4-12b-agentic'
  }
  if (name.includes('gemma-4-12b-it')) return 'gemma-4-12b-it'
  if (name.includes('deepseek-chat')) return 'DeepSeek-V3'
  if (name.includes('deepseek-reasoner')) return 'DeepSeek-R1'
  if (name.length > 26) return name.slice(0, 24) + '…'
  return name
}

export function OrchestrationPanel() {
  const routerMetadata = useAppStore((s) => s.routerMetadata)
  const modelInfo = useAppStore((s) => s.modelInfo)
  const contextCompression = useAppStore((s) => s.contextCompression)
  const memoryUpdatedAt = useAppStore((s) => s.memoryUpdatedAt)

  const route = routerMetadata?.route as string | undefined
  const confidence = routerMetadata?.confidence as number | undefined
  const confidencePct = confidence !== undefined ? Math.max(0, Math.min(100, Math.round(confidence * 100))) : null
  const classificationSource = routerMetadata?.classification_source as string | undefined

  const hasRoutingData = !!(modelInfo || route || contextCompression)
  const hasMemoryOnly = !hasRoutingData && !!memoryUpdatedAt

  if (!hasRoutingData && !hasMemoryOnly) {
    return <p className="orchestration-empty">No routing information yet.</p>
  }

  if (hasMemoryOnly) {
    return (
      <div>
        <div className="orchestration-row">
          <span className="orchestration-label">Memory</span>
          <span className="orchestration-value orchestration-memory-ok">Saved</span>
        </div>
        {memoryUpdatedAt && (
          <div className="orchestration-row">
            <span className="orchestration-label">Last Saved</span>
            <span className="orchestration-value orchestration-memory-ok">
              {new Date(memoryUpdatedAt).toLocaleTimeString()}
            </span>
          </div>
        )}
        <p className="orchestration-empty" style={{marginTop: 8}}>No routing data yet — send a message to populate.</p>
      </div>
    )
  }

  const displayModel = modelInfo || null

  return (
    <div>
      {displayModel && (
        <div className="orchestration-row">
          <span className="orchestration-label">Model</span>
          <span className="orchestration-value">
            <span
              className={`model-badge ${displayModel.includes('cloud') || displayModel.includes('deepseek') ? 'model-cloud' : 'model-local'}`}
              title={displayModel}
            >
              {formatModelBadge(displayModel)}
            </span>
          </span>
        </div>
      )}
      {route && (
        <div className="orchestration-row">
          <span className="orchestration-label">Route</span>
          <span className="orchestration-value">
            <span className="route-badge">{route}</span>
          </span>
        </div>
      )}
      {confidencePct !== null && (
        <div className="orchestration-gauge-wrap">
          <div
            className="orchestration-gauge"
            style={{ background: `conic-gradient(var(--accent) ${confidencePct}%, var(--bg-base) ${confidencePct}% 100%)` }}
          >
            <div className="orchestration-gauge-inner">
              <span className="orchestration-gauge-value">{confidencePct}%</span>
              <span className="orchestration-gauge-label">Confidence</span>
            </div>
          </div>
        </div>
      )}
      {classificationSource && (
        <div className="orchestration-row">
          <span className="orchestration-label">Source</span>
          <span className="orchestration-value">{classificationSource}</span>
        </div>
      )}
      {contextCompression && (
        <div className="orchestration-compression">
          <span className="orchestration-label">Compressed</span>
          <p className="compression-detail">
            {contextCompression.messagesCompressed} messages, freed ~{contextCompression.tokensFreed} tokens
          </p>
        </div>
      )}
      {memoryUpdatedAt && (
        <div className="orchestration-row">
          <span className="orchestration-label">Memory</span>
          <span className="orchestration-value orchestration-memory-ok">Saved</span>
        </div>
      )}
      
      <ScreenAssistLivePanel />
    </div>
  )
}
