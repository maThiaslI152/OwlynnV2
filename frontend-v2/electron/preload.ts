import { ipcRenderer, contextBridge } from 'electron'

// --------- Expose some API to the Renderer process ---------
contextBridge.exposeInMainWorld('ipcRenderer', {
  on(...args: Parameters<typeof ipcRenderer.on>) {
    const [channel, listener] = args
    return ipcRenderer.on(channel, (event, ...args) => listener(event, ...args))
  },
  off(...args: Parameters<typeof ipcRenderer.off>) {
    const [channel, ...omit] = args
    return ipcRenderer.off(channel, ...omit)
  },
  send(...args: Parameters<typeof ipcRenderer.send>) {
    const [channel, ...omit] = args
    return ipcRenderer.send(channel, ...omit)
  },
  invoke(...args: Parameters<typeof ipcRenderer.invoke>) {
    const [channel, ...omit] = args
    return ipcRenderer.invoke(channel, ...omit)
  },
})

// Specifically expose electronAPI to match the new electronBridge expectations
contextBridge.exposeInMainWorld('electronAPI', {
  invoke: (channel: string, args: any) => {
    // In Tauri, args is an object, but Electron's invoke takes individual arguments or an object.
    // For easiest migration from `invoke('cmd', { arg1: 'val' })`, we'll pass the whole object.
    return ipcRenderer.invoke(channel, args)
  },
  on: (channel: string, listener: (...args: any[]) => void) => {
    const subscription = (_event: any, ...args: any[]) => listener(...args)
    ipcRenderer.on(channel, subscription)
    return () => ipcRenderer.off(channel, subscription)
  }
})
