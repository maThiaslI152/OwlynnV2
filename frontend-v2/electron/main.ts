import { app, BrowserWindow, ipcMain, systemPreferences, desktopCapturer, Tray, Menu, nativeImage, shell } from 'electron'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import os from 'node:os'
import fs from 'node:fs'
import { execFile, spawn, type ChildProcess } from 'node:child_process'

const require = createRequire(import.meta.url)
const __dirname = path.dirname(fileURLToPath(import.meta.url))

process.env.APP_ROOT = path.join(__dirname, '..')

export const VITE_DEV_SERVER_URL = process.env['VITE_DEV_SERVER_URL']
export const MAIN_DIST = path.join(process.env.APP_ROOT, 'dist-electron')
export const RENDERER_DIST = path.join(process.env.APP_ROOT, 'dist')

process.env.VITE_PUBLIC = VITE_DEV_SERVER_URL ? path.join(process.env.APP_ROOT, 'public') : RENDERER_DIST

// ── State ────────────────────────────────────────────────────────
let win: BrowserWindow | null = null
let splashWin: BrowserWindow | null = null
let tray: Tray | null = null
let backendProcess: ChildProcess | null = null
let isQuitting = false

const CONFIG_PATH = path.join(app.getPath('home'), '.owlynn', 'config.json')
const PID_PATH = path.join(app.getPath('home'), '.owlynn', 'backend.pid')
const SECRETS_PATH = path.join(app.getPath('home'), '.owlynn', 'secrets.env')

interface ActionProposal {
  id: string
  summary: string
  source: string
  created_at: number
  status: string
}
const proposals: ActionProposal[] = []

// ── Helpers ──────────────────────────────────────────────────────

function findUvPath(): string {
  const candidates = [
    '/opt/homebrew/bin/uv',
    '/usr/local/bin/uv',
    path.join(os.homedir(), '.cargo', 'bin', 'uv'),
    '/usr/bin/uv',
  ]
  for (const p of candidates) {
    if (fs.existsSync(p)) return p
  }
  return 'uv'
}

function getProjectRoot(): string {
  // Packaged app: read from ~/.owlynn/config.json
  try {
    if (fs.existsSync(CONFIG_PATH)) {
      const config = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf-8'))
      if (config.project_root && fs.existsSync(config.project_root)) {
        return config.project_root
      }
    }
  } catch { /* ignore */ }
  // Dev mode: fallback to repo root (two levels up from electron/)
  return path.join(__dirname, '..', '..')
}

function getExtensionPath(): string {
  // Packaged app: bundled in Resources/browser-extension
  const packaged = path.join(process.resourcesPath, 'browser-extension')
  if (fs.existsSync(packaged)) return packaged
  // Dev mode: repo root
  return path.join(getProjectRoot(), 'browser-extension')
}

function readEnvFile(filePath: string): Record<string, string> {
  const env: Record<string, string> = {}
  try {
    if (!fs.existsSync(filePath)) return env
    for (const line of fs.readFileSync(filePath, 'utf-8').split('\n')) {
      const trimmed = line.trim()
      if (!trimmed || trimmed.startsWith('#')) continue
      const eqIdx = trimmed.indexOf('=')
      if (eqIdx > 0) {
        env[trimmed.slice(0, eqIdx)] = trimmed.slice(eqIdx + 1)
      }
    }
  } catch { /* ignore */ }
  return env
}

function sendSplash(step: string, status: string, message?: string) {
  splashWin?.webContents.send('splash-status', { step, status, message })
}

function execFileAsync(cmd: string, args: string[]): Promise<string> {
  return new Promise((resolve, reject) => {
    execFile(cmd, args, (error, stdout) => {
      if (error) reject(error)
      else resolve(stdout)
    })
  })
}

function fetchJson(url: string, timeoutMs = 3000): Promise<any> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('timeout')), timeoutMs)
    // Use http module to avoid fetch compatibility issues in Electron main
    const http = require('http')
    http.get(url, (res: any) => {
      let data = ''
      res.on('data', (chunk: string) => { data += chunk })
      res.on('end', () => {
        clearTimeout(timer)
        try { resolve(JSON.parse(data)) } catch { reject(new Error('invalid json')) }
      })
    }).on('error', (err: Error) => {
      clearTimeout(timer)
      reject(err)
    })
  })
}

// ── Startup Sequence ─────────────────────────────────────────────

async function startContainers(projectRoot: string): Promise<void> {
  // Check if containers are already running (idempotent — works with start.sh)
  for (const cmd of ['podman', 'docker']) {
    try {
      const stdout = await execFileAsync(cmd, [
        'ps', '--filter', 'name=owlynn_qdrant', '--filter', 'name=owlynn_redis',
        '--format', '{{.Names}}',
      ])
      const running = stdout.trim().split('\n').filter(Boolean)
      if (running.length >= 2) {
        console.log('[startup] Containers already running:', running.join(', '))
        return
      }
    } catch { /* ignore */ }
  }

  const cmds = [
    ['podman', ['compose', 'up', '-d', 'qdrant', 'redis']],
    ['docker', ['compose', 'up', '-d', 'qdrant', 'redis']],
    ['podman-compose', ['up', '-d', 'qdrant', 'redis']],
  ]
  for (const [cmd, args] of cmds) {
    try {
      await execFileAsync(cmd as string, args as string[])
      return
    } catch { /* ignore */ }
  }
  console.warn('[startup] Could not start containers (podman/docker not found). Qdrant/Redis may be unavailable.')
}

async function waitForLMStudio(): Promise<void> {
  const startTime = Date.now()
  const hintDelay = 10_000
  const timeout = 120_000

  while (Date.now() - startTime < timeout) {
    try {
      await fetchJson('http://127.0.0.1:1234/v1/models', 2000)
      return
    } catch { /* ignore */ }
    if (Date.now() - startTime > hintDelay) {
      sendSplash('lmstudio', 'active', 'Waiting for LM Studio — please open it...')
    }
    await new Promise(r => setTimeout(r, 1000))
  }
  throw new Error('LM Studio did not respond within 120 seconds')
}

async function killStaleBackend(): Promise<void> {
  // Kill by PID file
  try {
    if (fs.existsSync(PID_PATH)) {
      const pid = parseInt(fs.readFileSync(PID_PATH, 'utf-8').trim(), 10)
      if (pid > 0) {
        try { process.kill(pid, 'SIGKILL') } catch { /* ignore */ }
      }
      fs.unlinkSync(PID_PATH)
    }
  } catch { /* ignore */ }

  // Kill anything on port 8000
  try {
    const stdout = await execFileAsync('lsof', ['-ti', ':8000'])
    for (const pidStr of stdout.trim().split('\n')) {
      const pid = parseInt(pidStr.trim(), 10)
      if (pid > 0) {
        try { process.kill(pid, 'SIGKILL') } catch { /* ignore */ }
      }
    }
  } catch { /* ignore */ }

  // Wait for port 8000 to be free (up to 5 seconds)
  for (let i = 0; i < 10; i++) {
    try {
      await execFileAsync('lsof', ['-ti', ':8000'])
      await new Promise(r => setTimeout(r, 500))
    } catch {
      break // Port is free (lsof found nothing)
    }
  }
}

async function spawnBackend(projectRoot: string): Promise<void> {
  // Merge environment
  const env = { ...process.env }
  const envFiles = [
    path.join(projectRoot, '.env'),
    path.join(projectRoot, '.env.local'),
    SECRETS_PATH,
  ]
  for (const envFile of envFiles) {
    Object.assign(env, readEnvFile(envFile))
  }
  env.PYTHONPATH = `${projectRoot}${path.delimiter}${env.PYTHONPATH || ''}`
  env.STIRLING_PDF_URL = env.STIRLING_PDF_URL || 'http://localhost:8090'
  env.STIRLING_PDF_API_KEY = env.STIRLING_PDF_API_KEY || 'owlynn-local-dev'
  env.DOCLING_ARTIFACTS_PATH = env.DOCLING_ARTIFACTS_PATH || path.join(projectRoot, '.models', 'docling')

  const uvPath = findUvPath()
  console.log('[startup] Using uv at:', uvPath)

  return new Promise((resolve, reject) => {
    let settled = false

    const child = spawn(uvPath, [
      'run', 'python', '-m', 'uvicorn', 'src.api.server:app',
      '--host', '127.0.0.1', '--port', '8000',
      '--ws-max-size', '16777216', '--no-access-log',
    ], {
      cwd: projectRoot,
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
    })

    backendProcess = child

    // Write PID file
    try {
      fs.mkdirSync(path.dirname(PID_PATH), { recursive: true })
      fs.writeFileSync(PID_PATH, String(child.pid), 'utf-8')
    } catch { /* ignore */ }

    child.stdout?.on('data', (data: Buffer) => {
      console.log('[backend]', data.toString().trim())
    })

    child.stderr?.on('data', (data: Buffer) => {
      const msg = data.toString().trim()
      console.error('[backend]', msg)
      // Forward backend errors to splash hint
      if (splashWin && !settled) {
        const shortMsg = msg.split('\n').pop()?.slice(0, 80) || msg.slice(0, 80)
        sendSplash('backend', 'active', shortMsg)
      }
    })

    // If process exits before grace period, it's a crash
    child.on('exit', (code) => {
      console.log(`[backend] exited with code ${code}`)
      backendProcess = null
      if (!settled) {
        settled = true
        reject(new Error(`Backend exited with code ${code}`))
      }
    })

    child.on('error', (err) => {
      console.error('[backend] spawn error:', err)
      backendProcess = null
      if (!settled) {
        settled = true
        reject(new Error(`Failed to spawn backend: ${err.message}`))
      }
    })

    // Give the process 2 seconds to stabilize before resolving
    // (the health check will verify it's actually working)
    setTimeout(() => {
      if (!settled) {
        settled = true
        resolve()
      }
    }, 2000)
  })
}

async function waitForHealth(): Promise<void> {
  const startTime = Date.now()
  const timeout = 180_000
  let consecutiveReady = 0

  while (Date.now() - startTime < timeout) {
    try {
      const data = await fetchJson('http://127.0.0.1:8000/api/health', 2000)
      if (data.agent === 'ready') {
        consecutiveReady++
        if (consecutiveReady >= 2) return // Require 2 consecutive "ready" to confirm
      } else {
        consecutiveReady = 0
        sendSplash('health', 'active', `Initializing AI — ${data.agent || 'loading'}...`)
      }
    } catch { /* ignore */ }
    await new Promise(r => setTimeout(r, 1000))
  }
  throw new Error('Backend health check timed out after 180 seconds')
}

// ── Window Creation ──────────────────────────────────────────────

function createSplashWindow(): Promise<void> {
  return new Promise((resolve) => {
    splashWin = new BrowserWindow({
      width: 400,
      height: 300,
      frame: false,
      resizable: false,
      transparent: true,
      alwaysOnTop: true,
      center: true,
      webPreferences: {
        preload: path.join(__dirname, 'preload.js'),
        contextIsolation: true,
        nodeIntegration: false,
      },
    })
    // Packaged: splash.html is in Resources/ via extraResources
    // Dev: splash.html is in electron/ directory
    const splashPath = fs.existsSync(path.join(process.resourcesPath, 'splash.html'))
      ? path.join(process.resourcesPath, 'splash.html')
      : path.join(__dirname, 'splash.html')
    splashWin.webContents.on('did-finish-load', () => resolve())
    splashWin.loadFile(splashPath)
  })
}

function createMainWindow() {
  win = new BrowserWindow({
    icon: path.join(process.env.VITE_PUBLIC, 'favicon.svg'),
    width: 1200,
    height: 800,
    backgroundColor: '#00000000',
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

  win.webContents.on('did-finish-load', () => {
    win?.webContents.send('main-process-message', new Date().toLocaleString())
  })

  // Close-to-background: hide instead of destroy
  win.on('close', (e) => {
    if (!isQuitting) {
      e.preventDefault()
      win?.hide()
    }
  })

  // Load the backend URL (packaged) or dev server (dev mode)
  if (VITE_DEV_SERVER_URL) {
    win.loadURL(VITE_DEV_SERVER_URL)
  } else {
    win.loadURL('http://127.0.0.1:8000/')
  }
}

function createTray() {
  const iconPath = path.join(getProjectRoot(), 'frontend-v2', 'public', 'favicon.svg')
  let icon: Electron.NativeImage
  try {
    icon = nativeImage.createFromPath(iconPath)
    if (icon.isEmpty()) throw new Error('empty')
  } catch {
    // Fallback: create a 16x16 template icon
    icon = nativeImage.createEmpty()
  }

  tray = new Tray(icon)
  tray.setToolTip('Owlynn')
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Show Owlynn', click: () => win?.show() },
    { type: 'separator' },
    { label: 'Quit Owlynn', click: () => { isQuitting = true; app.quit() } },
  ]))
  tray.on('double-click', () => win?.show())
}

// ── IPC Handlers ─────────────────────────────────────────────────

function registerIpcHandlers() {
  ipcMain.handle('get_app_version', () => app.getVersion())

  ipcMain.handle('hide_to_tray', () => {
    win?.hide()
    return 'hidden'
  })

  ipcMain.handle('get_extension_path', () => getExtensionPath())

  ipcMain.handle('open_extension_folder', () => {
    shell.openPath(getExtensionPath())
    return 'opened'
  })

  ipcMain.handle('set_safe_mode', async (_event, mode: string) => {
    win?.webContents.send('runtime-event', { type: 'safe_mode.changed', mode })
    return `safe mode set: ${mode}`
  })

  ipcMain.handle('start_screen_preview', async (_event, source: string) => {
    if (process.platform === 'darwin') {
      const status = systemPreferences.getMediaAccessStatus('screen')
      if (status !== 'granted') {
        try { await desktopCapturer.getSources({ types: ['screen'] }) } catch { /* ignore */ }
        const newStatus = systemPreferences.getMediaAccessStatus('screen')
        if (newStatus !== 'granted') {
          throw new Error(`Screen capture permission is ${newStatus}. Please grant screen recording permission in System Settings -> Privacy & Security -> Screen Recording.`)
        }
      }
    }

    return new Promise((resolve, reject) => {
      const previewPath = path.join(app.getPath('temp'), `owlynn-preview-${source}-${Date.now()}.jpg`)
      if (process.platform === 'darwin') {
        execFile('screencapture', ['-x', '-t', 'jpg', previewPath], (error) => {
          if (error) {
            reject(new Error(`screencapture failed: ${error.message}`))
          } else {
            win?.webContents.send('runtime-event', {
              type: 'screen_assist.state', mode: 'preview', source, preview_path: previewPath,
            })
            resolve(`screen preview started: ${source} (${previewPath})`)
          }
        })
      } else {
        reject(new Error('Screen capture only implemented for macOS'))
      }
    })
  })

  ipcMain.handle('stop_screen_preview', async () => {
    win?.webContents.send('runtime-event', {
      type: 'screen_assist.state', mode: 'off', source: 'screen', preview_path: null,
    })
    return 'screen preview stopped'
  })

  ipcMain.handle('create_action_proposal', async (_event, summary: string) => {
    const proposal: ActionProposal = {
      id: `proposal-${Date.now()}`, summary, source: 'screen_assist',
      created_at: Date.now(), status: 'pending',
    }
    proposals.push(proposal)
    win?.webContents.send('runtime-event', { type: 'action.proposal', proposal })
    return proposal
  })

  ipcMain.handle('approve_action_proposal', async (_event, id: string) => {
    const proposal = proposals.find(p => p.id === id)
    if (proposal) {
      proposal.status = 'approved'
      win?.webContents.send('runtime-event', { type: 'action.proposal.result', id, status: 'approved' })
      return `proposal approved: ${id}`
    }
    throw new Error(`proposal not found: ${id}`)
  })

  ipcMain.handle('reject_action_proposal', async (_event, id: string) => {
    const proposal = proposals.find(p => p.id === id)
    if (proposal) {
      proposal.status = 'rejected'
      win?.webContents.send('runtime-event', { type: 'action.proposal.result', id, status: 'rejected' })
      return `proposal rejected: ${id}`
    }
    throw new Error(`proposal not found: ${id}`)
  })

  ipcMain.handle('set_window_size', async (_event, width: number, height: number) => {
    if (win) {
      win.setContentSize(Math.round(width), Math.round(height))
      return `window resized to ${width}x${height}`
    }
    throw new Error('main window not found')
  })

  ipcMain.handle('launch_browser', async () => {
    if (process.platform !== 'darwin') {
      throw new Error('Browser auto-launch is only supported on macOS')
    }
    return new Promise((resolve, reject) => {
      execFile('open', ['-a', 'Brave Browser'], (error) => {
        if (error) {
          reject(new Error('Brave Browser not found. Please install Brave.'))
        } else {
          resolve('Brave Browser launched successfully')
        }
      })
    })
  })
}

// ── Main Flow ────────────────────────────────────────────────────

app.whenReady().then(async () => {
  registerIpcHandlers()

  const projectRoot = getProjectRoot()

  // 1. Splash screen — await load so IPC listener is ready
  await createSplashWindow()
  const splashStartTime = Date.now()

  // 2. Start containers
  sendSplash('containers', 'active', 'Starting containers...')
  await startContainers(projectRoot)
  sendSplash('containers', 'done')

  // 3. Wait for LM Studio
  sendSplash('lmstudio', 'active', 'Connecting to LM Studio...')
  try {
    await waitForLMStudio()
    sendSplash('lmstudio', 'done')
  } catch (err) {
    sendSplash('lmstudio', 'error', 'LM Studio not responding')
    // Continue anyway — backend can start without LM Studio
  }

  // 4. Start backend
  sendSplash('backend', 'active', 'Starting backend...')
  try {
    await killStaleBackend()
    await spawnBackend(projectRoot)
    sendSplash('backend', 'done')
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    sendSplash('backend', 'error', `Backend failed: ${msg}`)
    return // Stay on splash — don't transition to broken main window
  }

  // 5. Wait for health
  sendSplash('health', 'active', 'Initializing AI...')
  try {
    await waitForHealth()
    sendSplash('health', 'done')
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    sendSplash('health', 'error', `Backend timed out: ${msg}`)
    return // Stay on splash — don't transition to broken main window
  }

  // 6. Ensure splash was visible for at least 3 seconds
  const splashElapsed = Date.now() - splashStartTime
  if (splashElapsed < 3000) {
    await new Promise(r => setTimeout(r, 3000 - splashElapsed))
  }

  // 7. Switch to main window
  splashWin?.close()
  splashWin = null
  createMainWindow()
  createTray()
})

// ── Shutdown ─────────────────────────────────────────────────────

app.on('before-quit', () => {
  isQuitting = true
  if (backendProcess) {
    backendProcess.kill('SIGTERM')
    const killTimer = setTimeout(() => {
      backendProcess?.kill('SIGKILL')
    }, 5000)
    backendProcess.on('exit', () => clearTimeout(killTimer))
  }
  try { fs.unlinkSync(PID_PATH) } catch { /* ignore */ }
})

app.on('window-all-closed', () => {
  // On macOS, keep app alive in tray/dock
  if (process.platform !== 'darwin') {
    app.quit()
    win = null
  }
})

app.on('activate', () => {
  if (win) {
    win.show()
  } else if (!splashWin) {
    createMainWindow()
  }
})
