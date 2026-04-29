import { convertFileSrc, invoke } from '@tauri-apps/api/core'

interface BridgeResult<T = string> {
  ok: boolean
  data?: T
  error?: string
}

async function invokeOrResult<T>(command: string, args?: Record<string, unknown>): Promise<BridgeResult<T>> {
  try {
    const data = await invoke<T>(command, args)
    return { ok: true, data }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    return { ok: false, error: message }
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

  convertFileSrc: (path: string) => {
    try {
      return convertFileSrc(path)
    } catch {
      return ''
    }
  },
}
