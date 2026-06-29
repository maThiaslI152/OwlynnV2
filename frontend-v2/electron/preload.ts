import { ipcRenderer, contextBridge } from 'electron'

// ── Allowed IPC channels ──────────────────────────────────────────────────
const ALLOWED_INVOKE_CHANNELS = [
  'set_safe_mode',
  'start_screen_preview',
  'stop_screen_preview',
  'create_action_proposal',
  'approve_action_proposal',
  'reject_action_proposal',
  'set_window_size',
]

const ALLOWED_SEND_CHANNELS: string[] = []

const ALLOWED_LISTEN_CHANNELS = [
  'main-process-message',
  'runtime-event',
  'screen_assist.state',
  'action.proposal',
  'action.proposal.result',
  'safe_mode.changed',
  'voice.tts_state',
]

// --------- Expose some API to the Renderer process ---------
contextBridge.exposeInMainWorld('ipcRenderer', {
  on(channel: string, listener: (...args: any[]) => void) {
    if (!ALLOWED_LISTEN_CHANNELS.includes(channel)) {
      console.warn(`[preload] Blocked listen on unauthorized channel: ${channel}`)
      return
    }
    return ipcRenderer.on(channel, (event, ...args) => listener(event, ...args))
  },
  off(channel: string, ...omit: any[]) {
    if (!ALLOWED_LISTEN_CHANNELS.includes(channel)) return
    return ipcRenderer.off(channel, ...omit)
  },
  send(channel: string, ...omit: any[]) {
    if (!ALLOWED_SEND_CHANNELS.includes(channel)) {
      console.warn(`[preload] Blocked send on unauthorized channel: ${channel}`)
      return
    }
    return ipcRenderer.send(channel, ...omit)
  },
  invoke(channel: string, ...omit: any[]) {
    if (!ALLOWED_INVOKE_CHANNELS.includes(channel)) {
      console.warn(`[preload] Blocked invoke on unauthorized channel: ${channel}`)
      return Promise.reject(new Error(`Unauthorized IPC channel: ${channel}`))
    }
    return ipcRenderer.invoke(channel, ...omit)
  },
})

// Specifically expose electronAPI to match the new electronBridge expectations
contextBridge.exposeInMainWorld('electronAPI', {
  invoke: (channel: string, args: any) => {
    if (!ALLOWED_INVOKE_CHANNELS.includes(channel)) {
      console.warn(`[preload] Blocked invoke on unauthorized channel: ${channel}`)
      return Promise.reject(new Error(`Unauthorized IPC channel: ${channel}`))
    }
    return ipcRenderer.invoke(channel, args)
  },
  on: (channel: string, listener: (...args: any[]) => void) => {
    if (!ALLOWED_LISTEN_CHANNELS.includes(channel)) {
      console.warn(`[preload] Blocked listen on unauthorized channel: ${channel}`)
      return () => {}
    }
    const subscription = (_event: any, ...args: any[]) => listener(...args)
    ipcRenderer.on(channel, subscription)
    return () => ipcRenderer.off(channel, subscription)
  }
})
