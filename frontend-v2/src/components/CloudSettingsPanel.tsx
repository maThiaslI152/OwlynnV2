import { useEffect, useState } from 'react'
import { useAppStore } from '../state/useAppStore'

type CloudModelTier = 'flash' | 'pro'
type CloudThinkingMode = 'auto' | 'always' | 'never'
type CloudReasoningEffort = 'high' | 'max'

export function CloudSettingsPanel() {
  const setOperatorNote = useAppStore((s) => s.setOperatorNote)
  const setCloudStatus = useAppStore((s) => s.setCloudStatus)
  const [tier, setTier] = useState<CloudModelTier>('flash')
  const [thinkingMode, setThinkingMode] = useState<CloudThinkingMode>('auto')
  const [reasoningEffort, setReasoningEffort] = useState<CloudReasoningEffort>('high')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let disposed = false
    const load = async () => {
      try {
        const response = await fetch('/api/unified-settings')
        if (!response.ok) return
        const payload = (await response.json()) as Record<string, unknown>
        if (disposed) return
        const t = String(payload.cloud_model_tier || 'flash').toLowerCase()
        setTier(t === 'pro' ? 'pro' : 'flash')
        const tm = String(payload.cloud_thinking_mode || 'auto').toLowerCase()
        if (tm === 'always' || tm === 'never') setThinkingMode(tm)
        else setThinkingMode('auto')
        const re = String(payload.cloud_reasoning_effort || 'high').toLowerCase()
        setReasoningEffort(re === 'max' ? 'max' : 'high')
      } catch (e) {
        console.warn('[CloudSettingsPanel]', e)
      } finally {
        if (!disposed) setLoading(false)
      }
    }
    void load()
    return () => {
      disposed = true
    }
  }, [])

  const saveField = async (fields: Record<string, string>) => {
    try {
      const response = await fetch('/api/unified-settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(fields),
      })
      if (!response.ok) {
        setOperatorNote(`Cloud settings error (${response.status})`)
        return
      }
      setOperatorNote('Cloud settings updated')
      const statusResponse = await fetch('/api/cloud-status')
      if (statusResponse.ok) {
        setCloudStatus(await statusResponse.json())
      }
    } catch (error) {
      setOperatorNote(`Cloud settings error: ${(error as Error).message}`)
    }
  }

  if (loading) {
    return <p className="safe-mode-info">Loading cloud settings…</p>
  }

  return (
    <div className="cloud-settings-panel">
      <p className="safe-mode-info">
        <strong>DeepSeek cloud</strong>
      </p>
      <label>
        Model tier
        <select
          data-testid="cloud-model-tier"
          value={tier}
          onChange={(e) => {
            const next = e.target.value as CloudModelTier
            setTier(next)
            void saveField({ cloud_model_tier: next })
          }}
        >
          <option value="flash">Standard (Flash) — lower cost</option>
          <option value="pro">Frontier (Pro) — higher reasoning</option>
        </select>
      </label>
      <label>
        Thinking mode
        <select
          data-testid="cloud-thinking-mode"
          value={thinkingMode}
          onChange={(e) => {
            const next = e.target.value as CloudThinkingMode
            setThinkingMode(next)
            void saveField({ cloud_thinking_mode: next })
          }}
        >
          <option value="auto">Auto (task-dependent)</option>
          <option value="always">Always on</option>
          <option value="never">Never (tools may force on)</option>
        </select>
      </label>
      <label>
        Reasoning effort
        <select
          data-testid="cloud-reasoning-effort"
          value={reasoningEffort}
          onChange={(e) => {
            const next = e.target.value as CloudReasoningEffort
            setReasoningEffort(next)
            void saveField({ cloud_reasoning_effort: next })
          }}
        >
          <option value="high">High</option>
          <option value="max">Max (frontier tasks)</option>
        </select>
      </label>
    </div>
  )
}
