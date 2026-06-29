import { useAppStore, type ExecutionPolicy, type SafeModeLevel } from '../state/useAppStore'
import { electronBridge as tauriBridge } from '../lib/electronBridge'
import toast from 'react-hot-toast'
import { fetchWithAuth } from '../lib/localRunToken'

const SAFE_MODES: SafeModeLevel[] = ['normal', 'safe_readonly', 'safe_confirmed_exec', 'safe_isolated']

const MODE_LABELS: Record<SafeModeLevel, string> = {
  normal: 'Normal',
  safe_readonly: 'Read-only',
  safe_confirmed_exec: 'Confirmed Exec',
  safe_isolated: 'Isolated',
}

export function SafeModePanel() {
  const safeMode = useAppStore((s) => s.safeMode)
  const executionPolicy = useAppStore((s) => s.executionPolicy)
  const setSafeMode = useAppStore((s) => s.setSafeMode)
  const setExecutionPolicy = useAppStore((s) => s.setExecutionPolicy)
  const setOperatorNote = useAppStore((s) => s.setOperatorNote)

  const onModeChange = async (mode: SafeModeLevel) => {
    // Try Tauri IPC first
    const result = await tauriBridge.setSafeMode(mode)
    if (result.ok) {
      setSafeMode(mode)
      setOperatorNote(`Safe Mode set to ${mode}`)
      return
    }
    // Tauri IPC unavailable (browser mode) — fall back to REST API
    console.warn('[SafeModePanel] Tauri IPC unavailable, falling back to REST API')
    setSafeMode(mode) // optimistic update — prevents visual bounce
    try {
        const response = await fetchWithAuth('/api/advanced-settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ safe_mode: mode }),
      })
      if (!response.ok) {
        throw new Error(`request failed (${response.status})`)
      }
      setOperatorNote(`Safe Mode set to ${mode}`)
    } catch (error) {
      toast.error(`Safe Mode error: ${(error as Error).message}`)
      setOperatorNote(`Safe Mode error: ${(error as Error).message}`)
    }
  }

  const onPolicyChange = (policy: ExecutionPolicy) => {
    void (async () => {
      try {
      const response = await fetchWithAuth('/api/advanced-settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ execution_policy: policy }),
        })
        if (!response.ok) {
          throw new Error(`request failed (${response.status})`)
        }
        const payload = (await response.json()) as { status?: string; message?: string }
        if (payload.status === 'error') {
          setOperatorNote(`Execution policy error: ${payload.message ?? 'unknown error'}`)
          return
        }
        setExecutionPolicy(policy)
        setOperatorNote(
          policy === 'auto_approve'
            ? 'Execution policy: auto-approve'
            : 'Execution policy: manual HITL approval'
        )
      } catch (error) {
        toast.error(`Execution policy error: ${(error as Error).message}`)
        setOperatorNote(`Execution policy error: ${(error as Error).message}`)
      }
    })()
  }

  return (
    <div>
      <label>
        Active mode
        <select data-testid="safemode-toggle" value={safeMode} onChange={(e) => onModeChange(e.target.value as SafeModeLevel)}>
          {SAFE_MODES.map((mode) => (
            <option key={mode} value={mode}>
              {MODE_LABELS[mode]}
            </option>
          ))}
        </select>
      </label>
      <label>
        Execution policy
        <select
          value={executionPolicy}
          onChange={(e) => onPolicyChange(e.target.value as ExecutionPolicy)}
        >
          <option value="auto_approve">Auto-approve</option>
          <option value="hitl">Manual approval (HITL)</option>
        </select>
      </label>
      <p className="safe-mode-info">
        {safeMode === 'normal'
          ? 'All tools allowed'
          : safeMode === 'safe_readonly'
            ? 'Read-only operations only'
            : safeMode === 'safe_confirmed_exec'
              ? 'Requires confirmation for exec'
              : 'Isolated sandbox execution'}
      </p>
      {import.meta.env.DEV && (
        <div className="safe-mode-dev-preview">
          <p className="safe-mode-info" style={{ marginTop: 12 }}>
            <strong>Dev: HITL Preview</strong>
          </p>
          <select
            onChange={(e) => {
              const variant = e.target.value
              if (!variant) return
              e.target.value = ''
              import('../dev/hitlPreview').then(({ getDevHitlPreview }) => {
                const preview = getDevHitlPreview(variant as any)
                if (preview) {
                  // Push through the same handleInterrupt path
                  const store = useAppStore.getState()
                  const interrupts = preview.event.interrupts
                  if (import.meta.env.DEV) {
                    // Use the parseHitlPrompt function directly
                    import('./HitlPromptCard').then(({ parseHitlPrompt }) => {
                      const model = parseHitlPrompt(interrupts)
                      if (model) {
                        store.appendConversationItem({
                          kind: 'hitl_prompt',
                          id: `hitl-dev-${Date.now()}`,
                          variant: model.variant,
                          title: model.title,
                          viewModel: model as unknown as Record<string, unknown>,
                          status: 'pending',
                          ts: Date.now(),
                        })
                      }
                    })
                  }
                }
              })
            }}
          >
            <option value="">Preview HITL...</option>
            <option value="router">Router — Skill Ambiguity</option>
            <option value="security">Security — Delete File</option>
            <option value="plan_review">Plan Review — Write File</option>
            <option value="scope_clarify">Scope Clarification — Calculator</option>
            <option value="ask_user">Ask User — Mid-task</option>
          </select>
        </div>
      )}
    </div>
  )
}
