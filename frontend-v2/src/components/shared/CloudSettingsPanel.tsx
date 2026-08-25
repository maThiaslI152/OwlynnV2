import { useEffect, useState } from 'react'
import { useAppStore } from '../../state/useAppStore'
import toast from 'react-hot-toast'
import { fetchWithAuth } from '../../lib/localRunToken'

type CloudModelTier = 'flash' | 'pro'
type CloudThinkingMode = 'auto' | 'always' | 'never'
type CloudReasoningEffort = 'high' | 'max'
type CloudRoutingMode = 'auto' | 'local_only' | 'cloud_first'

export function CloudSettingsPanel() {
  const setOperatorNote = useAppStore((s) => s.setOperatorNote)
  const setCloudStatus = useAppStore((s) => s.setCloudStatus)
  const [provider, setProvider] = useState<'deepseek' | 'openrouter'>('deepseek')
  const [tier, setTier] = useState<CloudModelTier>('flash')
  const [thinkingMode, setThinkingMode] = useState<CloudThinkingMode>('auto')
  const [reasoningEffort, setReasoningEffort] = useState<CloudReasoningEffort>('high')
  const [routingMode, setRoutingMode] = useState<CloudRoutingMode>('local_only')
  const [escalationEnabled, setEscalationEnabled] = useState(true)
  const [apiKey, setApiKey] = useState('')
  const [openrouterKey, setOpenrouterKey] = useState('')
  const [openrouterModel, setOpenrouterModel] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let disposed = false
    const load = async () => {
      try {
        const response = await fetchWithAuth('/api/unified-settings')
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
        const rm = String(payload.cloud_routing_mode || 'local_only').toLowerCase() as CloudRoutingMode
        setRoutingMode(rm === 'auto' || rm === 'cloud_first' ? rm : 'local_only')
        setEscalationEnabled(payload.cloud_escalation_enabled !== false)
        
        setProvider(payload.cloud_provider === 'openrouter' ? 'openrouter' : 'deepseek')
        setApiKey(String(payload.deepseek_api_key || ''))
        setOpenrouterKey(String(payload.openrouter_api_key || ''))
        setOpenrouterModel(String(payload.openrouter_model || ''))
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
      const response = await fetchWithAuth('/api/unified-settings', {
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
        <strong>Local-only by default</strong> — Owlynn runs on your local Gemma 4 12B model.
        Cloud (DeepSeek) is opt-in: flip Cloud Routing Policy below when you want offload.
      </p>

      <div className="settings-group api-key-group" style={{ marginBottom: '1.5rem', padding: '1rem', background: 'rgba(255,255,255,0.05)', borderRadius: '8px' }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginBottom: '1rem' }}>
          Cloud Provider
          <select
            value={provider}
            onChange={(e) => {
              const val = e.target.value as 'deepseek' | 'openrouter'
              setProvider(val)
              void saveField({ cloud_provider: val })
            }}
            style={{ padding: '0.5rem', borderRadius: '4px', border: '1px solid rgba(255,255,255,0.2)', background: 'rgba(0,0,0,0.2)', color: 'white' }}
          >
            <option value="deepseek">DeepSeek</option>
            <option value="openrouter">OpenRouter</option>
          </select>
        </label>

        {provider === 'deepseek' ? (
          <>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginBottom: '1rem' }}>
              DeepSeek API Key
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="sk-..."
                style={{ padding: '0.5rem', borderRadius: '4px', border: '1px solid rgba(255,255,255,0.2)', background: 'rgba(0,0,0,0.2)', color: 'white' }}
              />
            </label>
            <div style={{ display: 'flex', gap: '1rem' }}>
              <button 
                onClick={() => void saveField({ deepseek_api_key: apiKey })}
                style={{ padding: '0.4rem 1rem', background: '#3b82f6', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
              >
                Save Key
              </button>
            </div>
          </>
        ) : (
          <>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginBottom: '1rem' }}>
              OpenRouter API Key
              <input
                type="password"
                value={openrouterKey}
                onChange={(e) => setOpenrouterKey(e.target.value)}
                placeholder="sk-or-v1-..."
                style={{ padding: '0.5rem', borderRadius: '4px', border: '1px solid rgba(255,255,255,0.2)', background: 'rgba(0,0,0,0.2)', color: 'white' }}
              />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginBottom: '1rem' }}>
              OpenRouter Model (optional, overrides tier)
              <input
                type="text"
                value={openrouterModel}
                onChange={(e) => setOpenrouterModel(e.target.value)}
                onBlur={() => void saveField({ openrouter_model: openrouterModel })}
                placeholder="e.g. meta-llama/llama-3-70b-instruct"
                style={{ padding: '0.5rem', borderRadius: '4px', border: '1px solid rgba(255,255,255,0.2)', background: 'rgba(0,0,0,0.2)', color: 'white' }}
              />
            </label>
            <div style={{ display: 'flex', gap: '1rem' }}>
              <button 
                onClick={() => void saveField({ openrouter_api_key: openrouterKey })}
                style={{ padding: '0.4rem 1rem', background: '#3b82f6', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
              >
                Save Key
              </button>
            </div>
          </>
        )}
      </div>

      <label>
        Cloud Routing Policy
        <select
          data-testid="cloud-routing-mode"
          value={routingMode}
          onChange={(e) => {
            const next = e.target.value as CloudRoutingMode
            setRoutingMode(next)
            void saveField({ cloud_routing_mode: next })
          }}
        >
          <option value="local_only">Always Local (default — 100% offline)</option>
          <option value="auto">Auto (Local on AC, Cloud on Battery / Escalation)</option>
          <option value="cloud_first">Cloud-First (Prefer DeepSeek for complex tasks)</option>
        </select>
      </label>

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
