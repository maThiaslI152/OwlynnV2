interface BridgeResult<T = string> {
  ok: boolean
  data?: T
  error?: string
}

function tauriAvailable(): boolean {
  try {
    return typeof (window as any).__TAURI__ !== 'undefined'
  } catch {
    return false
  }
}

/** Lazily load Tauri core APIs; returns null in browser mode. */
async function loadTauriCore() {
  try {
    return await import('@tauri-apps/api/core')
  } catch {
    return null
  }
}

async function invokeOrResult<T>(command: string, args?: Record<string, unknown>): Promise<BridgeResult<T>> {
  if (!tauriAvailable()) {
    return { ok: false, error: 'Tauri IPC not available (browser mode)' }
  }
  const tauriCore = await loadTauriCore()
  if (!tauriCore) {
    return { ok: false, error: 'Tauri IPC not available (browser mode)' }
  }
  try {
    const data = await tauriCore.invoke<T>(command, args)
    return { ok: true, data }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    return { ok: false, error: message }
  }
}

function convertFileSrc(path: string): string {
  try {
    if (!tauriAvailable()) return path
    // In Tauri runtime, lazily attempt the conversion
    return path
  } catch {
    return ''
  }
}

export const tauriBridge = {
  speakText: (text: string) => invokeOrResult<string>('speak_text', { text }),
  setSafeMode: (mode: string) => invokeOrResult<string>('set_safe_mode', { mode }),
  startScreenPreview: (source: string) =>
    invokeOrResult<string>('start_screen_preview', { source }),
  stopScreenPreview: () => invokeOrResult<string>('stop_screen_preview', {}),
  createActionProposal: (summary: string) =>
    invokeOrResult<{
      id: string
      summary: string
      source: 'screen_assist' | 'voice' | 'system'
      created_at: number
      status: 'pending' | 'approved' | 'rejected'
    }>('create_action_proposal', { summary }),
  approveActionProposal: (id: string) =>
    invokeOrResult<string>('approve_action_proposal', { id }),
  rejectActionProposal: (id: string) =>
    invokeOrResult<string>('reject_action_proposal', { id }),
  setWindowSize: (width: number, height: number) =>
    invokeOrResult<string>('set_window_size', { width, height }),
  convertFileSrc,
}
