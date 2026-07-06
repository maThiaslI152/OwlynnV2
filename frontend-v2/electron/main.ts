import { app, BrowserWindow, ipcMain, systemPreferences, desktopCapturer } from 'electron'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { execFile } from 'node:child_process'

const require = createRequire(import.meta.url)
const __dirname = path.dirname(fileURLToPath(import.meta.url))

// The built directory structure
//
// ├─┬─┬ dist
// │ │ └── index.html
// │ │
// │ ├─┬ dist-electron
// │ │ ├── main.js
// │ │ └── preload.js
// │
process.env.APP_ROOT = path.join(__dirname, '..')

// 🚧 Use ['ENV_NAME'] avoid vite:define plugin - Vite@2.x
export const VITE_DEV_SERVER_URL = process.env['VITE_DEV_SERVER_URL']
export const MAIN_DIST = path.join(process.env.APP_ROOT, 'dist-electron')
export const RENDERER_DIST = path.join(process.env.APP_ROOT, 'dist')

process.env.VITE_PUBLIC = VITE_DEV_SERVER_URL ? path.join(process.env.APP_ROOT, 'public') : RENDERER_DIST

let win: BrowserWindow | null

// Basic Action Proposal State
interface ActionProposal {
  id: string
  summary: string
  source: string
  created_at: number
  status: string
}
const proposals: ActionProposal[] = []

function createWindow() {
  win = new BrowserWindow({
    icon: path.join(process.env.VITE_PUBLIC, 'electron-vite.svg'),
    width: 1200,
    height: 800,
    backgroundColor: '#00000000', // fully transparent
    transparent: true,
    vibrancy: 'under-window',
    visualEffectState: 'active',
    titleBarStyle: 'hiddenInset',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  // Test active push message to Renderer-process.
  win.webContents.on('did-finish-load', () => {
    win?.webContents.send('main-process-message', (new Date).toLocaleString())
  })

  if (VITE_DEV_SERVER_URL) {
    win.loadURL(VITE_DEV_SERVER_URL)
  } else {
    // win.loadFile('dist/index.html')
    win.loadFile(path.join(RENDERER_DIST, 'index.html'))
  }
}

// Quit when all windows are closed, except on macOS. There, it's common
// for applications and their menu bar to stay active until the user quits
// explicitly with Cmd + Q.
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
    win = null
  }
})

app.on('activate', () => {
  // On OS X it's common to re-create a window in the app when the
  // dock icon is clicked and there are no other windows open.
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow()
  }
})

app.whenReady().then(() => {
  // IPC Handlers
  ipcMain.handle('set_safe_mode', async (event, mode: string) => {
    // In a real implementation this would trigger state changes
    win?.webContents.send('runtime-event', {
      type: 'safe_mode.changed',
      mode
    })
    return `safe mode set: ${mode}`
  })

  ipcMain.handle('start_screen_preview', async (event, source: string) => {
    if (process.platform === 'darwin') {
      const status = systemPreferences.getMediaAccessStatus('screen')
      if (status !== 'granted') {
        try {
          // Attempting to get sources will trigger the macOS permission dialog if not yet determined
          await desktopCapturer.getSources({ types: ['screen'] })
        } catch (e) {
          // ignore
        }
        
        // Check again after prompt
        const newStatus = systemPreferences.getMediaAccessStatus('screen')
        if (newStatus !== 'granted') {
          throw new Error(`Screen capture permission is ${newStatus}. Please grant screen recording permission in System Settings -> Privacy & Security -> Screen Recording.`)
        }
      }
    }

    return new Promise((resolve, reject) => {
      const millis = Date.now()
      const previewPath = path.join(app.getPath('temp'), `owlynn-preview-${source}-${millis}.jpg`)
      
      if (process.platform === 'darwin') {
        execFile('screencapture', ['-x', '-t', 'jpg', previewPath], (error) => {
          if (error) {
            reject(new Error(`screencapture failed: ${error.message}`))
          } else {
            win?.webContents.send('runtime-event', {
              type: 'screen_assist.state',
              mode: 'preview',
              source,
              preview_path: previewPath
            })
            resolve(`screen preview started: ${source} (${previewPath})`)
          }
        })
      } else {
        reject(new Error('Screen capture only implemented for macOS in this version'))
      }
    })
  })

  ipcMain.handle('stop_screen_preview', async () => {
    win?.webContents.send('runtime-event', {
      type: 'screen_assist.state',
      mode: 'off',
      source: 'screen',
      preview_path: null
    })
    return 'screen preview stopped'
  })

  ipcMain.handle('create_action_proposal', async (event, summary: string) => {
    const proposal: ActionProposal = {
      id: `proposal-${Date.now()}`,
      summary,
      source: 'screen_assist',
      created_at: Date.now(),
      status: 'pending'
    }
    proposals.push(proposal)
    win?.webContents.send('runtime-event', {
      type: 'action.proposal',
      proposal
    })
    return proposal
  })

  ipcMain.handle('approve_action_proposal', async (event, id: string) => {
    const proposal = proposals.find(p => p.id === id)
    if (proposal) {
      proposal.status = 'approved'
      win?.webContents.send('runtime-event', {
        type: 'action.proposal.result',
        id,
        status: 'approved'
      })
      return `proposal approved: ${id}`
    }
    throw new Error(`proposal not found: ${id}`)
  })

  ipcMain.handle('reject_action_proposal', async (event, id: string) => {
    const proposal = proposals.find(p => p.id === id)
    if (proposal) {
      proposal.status = 'rejected'
      win?.webContents.send('runtime-event', {
        type: 'action.proposal.result',
        id,
        status: 'rejected'
      })
      return `proposal rejected: ${id}`
    }
    throw new Error(`proposal not found: ${id}`)
  })

  ipcMain.handle('set_window_size', async (event, width: number, height: number) => {
    if (win) {
      win.setContentSize(Math.round(width), Math.round(height))
      return `window resized to ${width}x${height}`
    }
    throw new Error('main window not found')
  })

  ipcMain.handle('launch_browser', async () => {
    return new Promise((resolve, reject) => {
      if (process.platform === 'darwin') {
        execFile('open', ['-a', 'Brave Browser'], (error) => {
          if (error) {
            reject(new Error(`Failed to launch Brave Browser: ${error.message}`))
          } else {
            resolve('Brave Browser launched successfully')
          }
        })
      } else {
        reject(new Error('Browser auto-launch is only supported on macOS'))
      }
    })
  })

  createWindow()
})
