interface BridgeResult<T = string> {
  ok: boolean
  data?: T
  error?: string
}

function electronAvailable(): boolean {
  try {
    return typeof (window as any).electronAPI !== 'undefined'
  } catch {
    return false
  }
}

async function invokeOrResult<T>(command: string, ...args: any[]): Promise<BridgeResult<T>> {
  if (!electronAvailable()) {
    return { ok: false, error: 'Electron IPC not available (browser mode)' }
  }
  
  try {
    const data = await (window as any).electronAPI.invoke(command, ...args)
    return { ok: true, data }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    return { ok: false, error: message }
  }
}

function convertFileSrc(path: string): string {
  try {
    if (!electronAvailable()) return path
    return `file://${path}`
  } catch {
    return ''
  }
}

export function listen<T>(channel: string, callback: (event: { payload: T }) => void) {
  if (!electronAvailable()) {
    return Promise.resolve(() => {})
  }
  const unlisten = (window as any).electronAPI.on(channel, (payload: T) => {
    callback({ payload })
  })
  return Promise.resolve(unlisten)
}

export const electronBridge = {
  // TTS is now natively synthesized via Web Speech API in the browser renderer, skipping IPC
  speakText: async (text: string): Promise<BridgeResult<string>> => {
    try {
      if (!('speechSynthesis' in window)) {
        return { ok: false, error: 'Web Speech API not supported' }
      }
      const utterance = new SpeechSynthesisUtterance(text)
      window.speechSynthesis.speak(utterance)
      return { ok: true, data: 'speech queued' }
    } catch (err) {
      return { ok: false, error: String(err) }
    }
  },

  setSafeMode: (mode: string) => invokeOrResult<string>('set_safe_mode', mode),
  startScreenPreview: (source: string) => invokeOrResult<string>('start_screen_preview', source),
  stopScreenPreview: () => invokeOrResult<string>('stop_screen_preview', {}),
  createActionProposal: (summary: string) =>
    invokeOrResult<{
      id: string
      summary: string
      source: 'screen_assist' | 'voice' | 'system'
      created_at: number
      status: 'pending' | 'approved' | 'rejected'
    }>('create_action_proposal', summary),
  approveActionProposal: (id: string) => invokeOrResult<string>('approve_action_proposal', id),
  rejectActionProposal: (id: string) => invokeOrResult<string>('reject_action_proposal', id),
  setWindowSize: (width: number, height: number) => invokeOrResult<string>('set_window_size', width, height),
  convertFileSrc,
}
