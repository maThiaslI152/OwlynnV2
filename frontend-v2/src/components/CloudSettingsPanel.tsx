import { useEffect, useState } from 'react'
import { useAppStore } from '../state/useAppStore'
import toast from 'react-hot-toast'

type CloudModelTier = 'flash' | 'pro'
type CloudThinkingMode = 'auto' | 'always' | 'never'
type CloudReasoningEffort = 'high' | 'max'

export function CloudSettingsPanel() {
  const setOperatorNote = useAppStore((s) => s.setOperatorNote)
  const setCloudStatus = useAppStore((s) => s.setCloudStatus)
  const [tier, setTier] = useState<CloudModelTier>('flash')
  const [thinkingMode, setThinkingMode] = useState<CloudThinkingMode>('auto')
  const [reasoningEffort, setReasoningEffort] = useState<CloudReasoningEffort>('high')
  const [escalationEnabled, setEscalationEnabled] = useState(true)
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
        setEscalationEnabled(payload.cloud_escalation_enabled !== false)
      } catch (e) {
        console.warn('[CloudSettingsPanel]', e)
        toast.error('Failed to load cloud settings')
      } finally {
        if (!disposed) setLoading(false)
      }
    }
    void load()
    return () => {
      disposed = true
    }
  }, [])

  const saveField = async (fields: Record<string, string | boolean>) => {
    try {
      const response = await fetch('/api/unified-settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(fields),
      })
      if (!response.ok) {
        throw new Error(`Cloud settings error (${response.status})`)
      }
      setOperatorNote('Cloud settings updated')
      const statusResponse = await fetch('/api/cloud-status')
      if (statusResponse.ok) {
        setCloudStatus(await statusResponse.json())
      }
    } catch (error) {
      toast.error(`Cloud settings error: ${(error as Error).message}`)
      setOperatorNote(`Cloud settings error: ${(error as Error).message}`)
    }
  }

  if (loading) {
    return <p className="safe-mode-info">Loading cloud settings…</p>
  }

  return (
    <div className="cloud-settings-panel">
      <p className="safe-mode-info">
        <strong>DeepSeek cloud</strong> — routes complex tasks to DeepSeek when a key is set.
      </p>
      <label>
        Cloud escalation
        <select
          data-testid="cloud-escalation-enabled"
          value={escalationEnabled ? 'on' : 'off'}
          onChange={(e) => {
            const next = e.target.value === 'on'
            setEscalationEnabled(next)
            void saveField({ cloud_escalation_enabled: next })
          }}
        >
          <option value="on">Enabled (cloud-first routing)</option>
          <option value="off">Disabled (no cloud)</option>
        </select>
      </label>
      <label>
        Model tier
        <select
          data-testid="cloud-model-tier"
          value={tier}
          disabled={!escalationEnabled}
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
          disabled={!escalationEnabled}
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
          disabled={!escalationEnabled || thinkingMode === 'never'}
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
