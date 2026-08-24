import { app, BrowserWindow, ipcMain, systemPreferences, desktopCapturer, Tray, Menu, nativeImage, shell } from 'electron'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import os from 'node:os'
import fs from 'node:fs'
import { execFile, spawn, type ChildProcess } from 'node:child_process'

const require = createRequire(import.meta.url)
const __dirname = path.dirname(fileURLToPath(import.meta.url))

// Augment PATH for macOS packaged apps which do not inherit user shell environment
function fixPath(): void {
  const home = os.homedir()
  const extraPaths = [
    path.join(home, 'homebrew', 'bin'),
    path.join(home, 'homebrew', 'sbin'),
    path.join(home, '.cargo', 'bin'),
    path.join(home, '.local', 'bin'),
    path.join(home, '.lmstudio', 'bin'),
    '/opt/homebrew/bin',
    '/opt/homebrew/sbin',
    '/usr/local/bin',
    '/usr/local/sbin',
    '/usr/bin',
    '/bin',
    '/usr/sbin',
    '/sbin',
  ]
  const current = (process.env.PATH || '').split(path.delimiter)
  for (const p of extraPaths) {
    if (fs.existsSync(p) && !current.includes(p)) {
      current.unshift(p)
    }
  }
  process.env.PATH = current.join(path.delimiter)
}
fixPath()

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
const OWLYNN_DIR = path.join(app.getPath('home'), '.owlynn')
const RUNTIME_DIR = path.join(OWLYNN_DIR, 'runtime')
const EXTENSION_HINT_FLAG = path.join(OWLYNN_DIR, '.extension_hint_shown')
const PID_PATH = path.join(OWLYNN_DIR, 'backend.pid')
const SECRETS_PATH = path.join(OWLYNN_DIR, 'secrets.env')
const MVP_COMPOSE_FILE = 'docker-compose.mvp.yml'
const MVP_SERVICES = ['postgres', 'stirling-pdf'] as const
const MVP_CONTAINER_NAMES = ['owlynn_postgres', 'owlynn_stirling_pdf'] as const

interface ActionProposal {
  id: string
  summary: string
  source: string
  created_at: number
  status: string
}
const proposals: ActionProposal[] = []

// ── Helpers ──────────────────────────────────────────────────────

function findPythonCmd(projectRoot: string): { cmd: string; prefixArgs: string[] } {
  const venvPython = path.join(projectRoot, '.venv', 'bin', 'python')
  if (fs.existsSync(venvPython)) {
    return { cmd: venvPython, prefixArgs: [] }
  }

  if (app.isPackaged) {
    throw new Error(`Bundled Python not found at ${venvPython}. Try reinstalling Owlynn.`)
  }

  const uvCandidates = [
    path.join(os.homedir(), 'homebrew', 'bin', 'uv'),
    '/opt/homebrew/bin/uv',
    '/usr/local/bin/uv',
    path.join(os.homedir(), '.cargo', 'bin', 'uv'),
    path.join(os.homedir(), '.local', 'bin', 'uv'),
    'uv',
  ]
  for (const p of uvCandidates) {
    if (p === 'uv' || fs.existsSync(p)) {
      return { cmd: p, prefixArgs: ['run', 'python'] }
    }
  }

  return { cmd: 'python3', prefixArgs: [] }
}

function findPythonOrUv(projectRoot: string): { cmd: string; args: string[] } {
  const { cmd, prefixArgs } = findPythonCmd(projectRoot)
  return {
    cmd,
    args: [
      ...prefixArgs,
      '-m',
      'uvicorn',
      'src.api.server:app',
      '--host',
      '127.0.0.1',
      '--port',
      '8000',
      '--ws-max-size',
      '16777216',
      '--no-access-log',
    ],
  }
}

function getMvpComposePath(projectRoot: string): string {
  return path.join(projectRoot, MVP_COMPOSE_FILE)
}

function ensureOwlynnConfig(runtimeRoot: string): void {
  const owlynnDir = path.dirname(CONFIG_PATH)
  fs.mkdirSync(owlynnDir, { recursive: true })

  let runtimeVersion = 'dev'
  try {
    const pkgPath = path.join(process.env.APP_ROOT || '', 'package.json')
    if (fs.existsSync(pkgPath)) {
      runtimeVersion = JSON.parse(fs.readFileSync(pkgPath, 'utf-8')).version || runtimeVersion
    }
  } catch { /* ignore */ }

  const config = {
    project_root: runtimeRoot,
    runtime_version: runtimeVersion,
    written_at: new Date().toISOString(),
  }
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2), 'utf-8')
  console.log('[startup] Wrote config.json →', CONFIG_PATH)
}

async function areMvpContainersRunning(projectRoot: string): Promise<string[]> {
  for (const cmd of ['podman', 'docker']) {
    try {
      const filters = MVP_CONTAINER_NAMES.flatMap((name) => ['--filter', `name=${name}`])
      const stdout = await execFileAsync(cmd, ['ps', ...filters, '--format', '{{.Names}}'], {
        cwd: projectRoot,
      })
      const running = stdout.trim().split('\n').filter(Boolean)
      if (running.length >= MVP_CONTAINER_NAMES.length) {
        return running
      }
    } catch { /* ignore */ }
  }
  return []
}

async function isPostgresReady(): Promise<boolean> {
  for (const cmd of ['podman', 'docker']) {
    try {
      await execFileAsync(cmd, ['exec', 'owlynn_postgres', 'pg_isready', '-U', 'owlynn', '-d', 'owlynn'])
      return true
    } catch { /* ignore */ }
  }
  return false
}

function getBundledBackendPath(): string | null {
  if (!app.isPackaged) return null
  const bundled = path.join(process.resourcesPath, 'owlynn-backend')
  return fs.existsSync(bundled) ? bundled : null
}

function readRuntimeVersion(runtimeRoot: string): string | null {
  const versionFile = path.join(runtimeRoot, 'VERSION')
  if (!fs.existsSync(versionFile)) return null
  try {
    return fs.readFileSync(versionFile, 'utf-8').trim() || null
  } catch {
    return null
  }
}

async function extractRuntimeBundle(): Promise<void> {
  const bundled = getBundledBackendPath()
  if (!bundled) return

  const appVersion = app.getVersion()
  const runtimeVersion = fs.existsSync(RUNTIME_DIR) ? readRuntimeVersion(RUNTIME_DIR) : null
  const runtimeFrontendIndex = path.join(RUNTIME_DIR, 'frontend-v2', 'dist', 'index.html')
  const runtimeReady =
    runtimeVersion === appVersion &&
    fs.existsSync(path.join(RUNTIME_DIR, '.venv', 'bin', 'python')) &&
    fs.existsSync(runtimeFrontendIndex)

  if (runtimeReady) {
    console.log('[runtime] Already extracted at version', appVersion)
    return
  }

  sendSplash('containers', 'active', 'Preparing backend runtime...', `Extracting bundled backend v${appVersion}`)

  const modelsBackup = path.join(OWLYNN_DIR, '.runtime_models_backup')
  const runtimeModels = path.join(RUNTIME_DIR, '.models')
  if (fs.existsSync(runtimeModels)) {
    fs.rmSync(modelsBackup, { recursive: true, force: true })
    fs.cpSync(runtimeModels, modelsBackup, { recursive: true })
  }

  if (fs.existsSync(RUNTIME_DIR)) {
    fs.rmSync(RUNTIME_DIR, { recursive: true, force: true })
  }
  fs.mkdirSync(OWLYNN_DIR, { recursive: true })

  await execFileAsync('cp', ['-R', bundled, RUNTIME_DIR])

  if (fs.existsSync(modelsBackup)) {
    fs.cpSync(modelsBackup, path.join(RUNTIME_DIR, '.models'), { recursive: true })
    fs.rmSync(modelsBackup, { recursive: true, force: true })
  }

  fs.writeFileSync(path.join(RUNTIME_DIR, 'VERSION'), appVersion, 'utf-8')
  console.log('[runtime] Extracted backend to', RUNTIME_DIR)
  sendSplash('containers', 'active', 'Backend runtime ready', `Extracted v${appVersion} to ~/.owlynn/runtime`)
}

function getProjectRoot(): string {
  if (app.isPackaged) {
    if (fs.existsSync(RUNTIME_DIR)) {
      return RUNTIME_DIR
    }
    const bundled = getBundledBackendPath()
    if (bundled) return bundled
  }

  // Dev mode: prefer config.json, then repo root
  try {
    if (fs.existsSync(CONFIG_PATH)) {
      const config = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf-8'))
      if (config.project_root && fs.existsSync(config.project_root)) {
        return config.project_root
      }
    }
  } catch { /* ignore */ }
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

function sendSplash(step: string, status: string, message?: string, logLine?: string) {
  if (splashWin && !splashWin.isDestroyed()) {
    splashWin.webContents.send('splash-status', { step, status, message, logLine })
  }
}

function execFileAsync(cmd: string, args: string[], options?: { cwd?: string }): Promise<string> {
  return new Promise((resolve, reject) => {
    execFile(cmd, args, { env: process.env, ...options }, (error, stdout) => {
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

async function findContainerRuntime(): Promise<'podman' | 'docker' | null> {
  for (const cmd of ['podman', 'docker'] as const) {
    try {
      await execFileAsync(cmd, ['--version'])
      return cmd
    } catch { /* ignore */ }
  }
  return null
}

async function startContainers(projectRoot: string): Promise<void> {
  sendSplash('containers', 'active', 'Checking container runtime...', 'Looking for Podman or Docker...')

  const runtime = await findContainerRuntime()
  if (!runtime) {
    const msg = 'Install Podman Desktop (podman-desktop.io) or Docker Desktop (docker.com)'
    console.error('[startup] No container runtime found')
    sendSplash('containers', 'error', 'Podman or Docker required', msg)
    if (app.isPackaged) {
      throw new Error(`Container runtime not found. ${msg}`)
    }
    sendSplash('containers', 'done', 'Containers skipped', msg)
    return
  }

  sendSplash('containers', 'active', 'Checking container status...', `Using ${runtime} — Postgres & StirlingPDF`)

  try {
    await execFileAsync('podman', ['machine', 'start'])
  } catch { /* docker desktop or podman already running */ }

  const running = await areMvpContainersRunning(projectRoot)
  if (running.length >= MVP_CONTAINER_NAMES.length) {
    console.log('[startup] MVP containers already running:', running.join(', '))
    sendSplash('containers', 'done', 'Containers ready', `Running: ${running.join(', ')}`)
    return
  }

  const composePath = getMvpComposePath(projectRoot)
  if (!fs.existsSync(composePath)) {
    console.warn('[startup] Missing compose file:', composePath)
  }

  sendSplash('containers', 'active', 'Starting Podman/Docker compose...', 'Starting Postgres & StirlingPDF...')
  const composeArgs = ['-f', MVP_COMPOSE_FILE, 'up', '-d', ...MVP_SERVICES]
  const cmds: [string, string[]][] = [
    ['podman', ['compose', ...composeArgs]],
    ['docker', ['compose', ...composeArgs]],
    ['podman-compose', ['-f', MVP_COMPOSE_FILE, 'up', '-d', ...MVP_SERVICES]],
  ]
  for (const [cmd, args] of cmds) {
    try {
      await execFileAsync(cmd, args, { cwd: projectRoot })
      sendSplash('containers', 'done', 'Containers started', 'Postgres & StirlingPDF started')
      return
    } catch { /* try next */ }
  }
  console.warn('[startup] Could not start MVP containers (podman/docker not found).')
  sendSplash('containers', 'done', 'Containers skipped', 'Postgres/StirlingPDF not started — install Podman or Docker')
}

async function waitForPostgres(timeoutMs = 90_000): Promise<void> {
  const startTime = Date.now()
  sendSplash('database', 'active', 'Waiting for PostgreSQL...', 'Checking pg_isready on owlynn_postgres')

  while (Date.now() - startTime < timeoutMs) {
    if (await isPostgresReady()) {
      return
    }
    await new Promise((r) => setTimeout(r, 1000))
  }
  throw new Error('PostgreSQL did not become ready within 90 seconds')
}

async function runMigrations(projectRoot: string): Promise<void> {
  sendSplash('database', 'active', 'Running database migrations...', 'alembic upgrade head')

  const env = { ...process.env }
  env.PYTHONPATH = `${projectRoot}${path.delimiter}${env.PYTHONPATH || ''}`
  env.DATABASE_URL =
    env.DATABASE_URL || 'postgresql+asyncpg://owlynn:owlynn_password@127.0.0.1:5432/owlynn'

  const { cmd, prefixArgs } = findPythonCmd(projectRoot)
  const args = [...prefixArgs, '-m', 'alembic', 'upgrade', 'head']

  try {
    const output = await new Promise<string>((resolve, reject) => {
      execFile(cmd, args, { cwd: projectRoot, env }, (error, stdout, stderr) => {
        if (error) reject(new Error(stderr || error.message))
        else resolve(stdout || stderr)
      })
    })
    const summary = output.trim().split('\n').filter(Boolean).slice(-1)[0] || 'Schema up to date'
    sendSplash('database', 'done', 'Database ready', summary.slice(0, 90))
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    sendSplash('database', 'error', 'Migration failed', msg.slice(0, 90))
    throw err
  }
}

async function waitForLMStudio(): Promise<void> {
  const startTime = Date.now()
  const hintDelay = 5_000
  const timeout = 120_000

  sendSplash('lmstudio', 'active', 'Connecting to LM Studio on :1234...', 'Probing http://127.0.0.1:1234/v1/models')

  while (Date.now() - startTime < timeout) {
    try {
      const data = await fetchJson('http://127.0.0.1:1234/v1/models', 2000)
      const models = Array.isArray(data?.data) ? data.data.map((m: any) => m.id) : []
      const mainModel = models.find((m: string) => !m.includes('embed') && !m.includes('ocr')) || models[0] || 'active'
      const short = mainModel.length > 25 ? mainModel.slice(0, 22) + '…' : mainModel
      sendSplash('lmstudio', 'done', 'LM Studio connected', `Loaded: ${short}`)
      return
    } catch { /* ignore */ }

    if (Date.now() - startTime > hintDelay) {
      sendSplash('lmstudio', 'active', 'Waiting for LM Studio — please open it...', 'Waiting for LM Studio local server on port 1234')
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
  env.DATABASE_URL =
    env.DATABASE_URL || 'postgresql+asyncpg://owlynn:owlynn_password@127.0.0.1:5432/owlynn'
  env.STIRLING_PDF_URL = env.STIRLING_PDF_URL || 'http://localhost:8090'
  env.STIRLING_PDF_API_KEY = env.STIRLING_PDF_API_KEY || 'owlynn-local-dev'
  env.DOCLING_ARTIFACTS_PATH =
    env.DOCLING_ARTIFACTS_PATH || path.join(projectRoot, '.models', 'docling')
  if (app.isPackaged) {
    env.OWLYNN_PACKAGED = '1'
  }

  const { cmd, args } = findPythonOrUv(projectRoot)
  console.log('[startup] Launching backend:', cmd, args.join(' '))
  sendSplash('backend', 'active', 'Starting Python backend...', `Executing: ${path.basename(cmd)} ${args.slice(0, 3).join(' ')}`)

  return new Promise((resolve, reject) => {
    let settled = false

    const child = spawn(cmd, args, {
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
      const lines = data.toString().trim().split('\n').filter(Boolean)
      for (const line of lines) {
        console.log('[backend]', line)
        sendSplash('backend', 'active', 'Starting server...', line.slice(0, 90))
      }
    })

    child.stderr?.on('data', (data: Buffer) => {
      const lines = data.toString().trim().split('\n').filter(Boolean)
      for (const line of lines) {
        console.error('[backend]', line)
        sendSplash('backend', 'active', 'Initializing backend...', line.slice(0, 90))
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
        reject(new Error(`Failed to spawn backend (${cmd}): ${err.message}`))
      }
    })

    // Give the process 2 seconds to stabilize before resolving
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

  sendSplash('ready', 'active', 'Initializing AI engine...', 'Compiling LangGraph nodes and memory pools...')

  while (Date.now() - startTime < timeout) {
    try {
      const data = await fetchJson('http://127.0.0.1:8000/api/health', 2000)
      if (data.agent === 'ready') {
        consecutiveReady++
        if (consecutiveReady >= 2) {
          sendSplash('ready', 'done', 'Owlynn ready', 'LangGraph pipeline and tools initialized')
          return
        }
      } else {
        consecutiveReady = 0
        const statusMsg = data.agent ? `Initializing AI (${data.agent})...` : 'Initializing AI engine...'
        sendSplash('ready', 'active', statusMsg, `State: ${data.agent || 'loading'}`)
      }
    } catch {
      sendSplash('ready', 'active', 'Waiting for backend HTTP server...', 'Connecting to http://127.0.0.1:8000/api/health')
    }
    await new Promise(r => setTimeout(r, 1000))
  }
  throw new Error('Backend health check timed out after 180 seconds')
}

// ── Window Creation ──────────────────────────────────────────────

function createSplashWindow(): Promise<void> {
  return new Promise((resolve) => {
    splashWin = new BrowserWindow({
      width: 440,
      height: 330,
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
    splashWin.webContents.on('did-finish-load', () => {
      setTimeout(resolve, 150)
    })
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
    { label: 'Quit Owlynn', click: async () => { isQuitting = true; await gracefulShutdown(); app.quit() } },
  ]))
  tray.on('double-click', () => win?.show())
}

// ── IPC Handlers ─────────────────────────────────────────────────

function registerIpcHandlers() {
  ipcMain.handle('get_app_version', () => app.getVersion())

  ipcMain.handle('is_packaged', () => app.isPackaged)

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
  ipcMain.handle('quit_app', async () => {
    isQuitting = true
    await gracefulShutdown()
    app.quit()
  })
}

async function gracefulShutdown(): Promise<void> {
  console.log('[shutdown] Initiating graceful shutdown...')
  const projectRoot = getProjectRoot()

  // 1. Unload model from LM Studio to free RAM
  try {
    const http = require('http')
    const getLoadedModels = (): Promise<any[]> =>
      new Promise((resolve) => {
        const timer = setTimeout(() => resolve([]), 1500)
        http
          .get('http://127.0.0.1:1234/v1/models', (res: any) => {
            let data = ''
            res.on('data', (c: string) => { data += c })
            res.on('end', () => {
              clearTimeout(timer)
              try {
                const parsed = JSON.parse(data)
                resolve(Array.isArray(parsed?.data) ? parsed.data : [])
              } catch {
                resolve([])
              }
            })
          })
          .on('error', () => {
            clearTimeout(timer)
            resolve([])
          })
      })

    const models = await getLoadedModels()
    for (const m of models) {
      if (m?.id) {
        const req = http.request({
          hostname: '127.0.0.1',
          port: 1234,
          path: `/v1/models/${encodeURIComponent(m.id)}`,
          method: 'DELETE',
          timeout: 2000,
        })
        req.on('error', () => {})
        req.end()
      }
    }
    console.log('[shutdown] Sent model unload requests to LM Studio')
  } catch (e) {
    console.warn('[shutdown] Model unload error:', e)
  }

  // 2. Stop Python backend process cleanly
  if (backendProcess) {
    backendProcess.kill('SIGTERM')
    await new Promise((resolve) => {
      const timer = setTimeout(() => {
        try { backendProcess?.kill('SIGKILL') } catch { /* ignore */ }
        resolve(null)
      }, 2500)
      backendProcess?.on('exit', () => {
        clearTimeout(timer)
        resolve(null)
      })
    })
    backendProcess = null
  }
  try { fs.unlinkSync(PID_PATH) } catch { /* ignore */ }

  // 3. Stop MVP Podman/Docker containers
  try {
    const stopArgs = ['-f', MVP_COMPOSE_FILE, 'stop', ...MVP_SERVICES]
    for (const cmd of ['podman', 'docker']) {
      try {
        await execFileAsync(cmd, ['compose', ...stopArgs], { cwd: projectRoot })
        console.log(`[shutdown] Stopped MVP containers via ${cmd}`)
        break
      } catch { /* try next */ }
    }
  } catch (e) {
    console.warn('[shutdown] Container stop error:', e)
  }

  console.log('[shutdown] Graceful shutdown complete.')
}

function maybeShowExtensionHint(): void {
  if (!app.isPackaged || !win) return
  if (fs.existsSync(EXTENSION_HINT_FLAG)) return

  const extensionPath = getExtensionPath()
  const showHint = (): void => {
    if (!win || win.isDestroyed()) return
    win.webContents.send('runtime-event', {
      type: 'extension.hint',
      path: extensionPath,
    })
    try {
      fs.mkdirSync(OWLYNN_DIR, { recursive: true })
      fs.writeFileSync(EXTENSION_HINT_FLAG, new Date().toISOString(), 'utf-8')
    } catch { /* ignore */ }
  }

  if (win.webContents.isLoading()) {
    win.webContents.once('did-finish-load', showHint)
  } else {
    showHint()
  }
}
function launchBraveBrowser(): void {
  try {
    const extensionPath = getExtensionPath()
    const candidates = [
      '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',
      path.join(app.getPath('home'), 'Applications', 'Brave Browser.app', 'Contents', 'MacOS', 'Brave Browser'),
    ]
    let braveBin = ''
    for (const c of candidates) {
      if (fs.existsSync(c)) {
        braveBin = c
        break
      }
    }

    if (!braveBin) {
      if (process.platform === 'darwin') {
        execFile('open', ['-a', 'Brave Browser'], () => {})
      }
      return
    }

    if (!fs.existsSync(extensionPath)) {
      console.warn('[startup] Extension path missing:', extensionPath)
      execFile('open', ['-a', 'Brave Browser'], () => {})
      return
    }

    // --load-extension fails with "unexpected error" when Brave is already running.
    execFile('pgrep', ['-x', 'Brave Browser'], (pgrepErr) => {
      if (!pgrepErr) {
        console.log('[startup] Brave already running — skipping --load-extension (load unpacked extension manually if needed)')
        return
      }

      console.log('[startup] Launching Brave with extension:', extensionPath)
      const braveProc = spawn(
        braveBin,
        [`--load-extension=${extensionPath}`, '--no-first-run', '--no-default-browser-check'],
        { detached: true, stdio: 'ignore' },
      )
      braveProc.on('error', (err) => {
        console.warn('[startup] Brave spawn failed:', err.message)
      })
      braveProc.unref()
    })
  } catch (err) {
    console.warn('[startup] Could not auto-launch Brave Browser:', err)
  }
}

// ── Main Flow ────────────────────────────────────────────────────

app.whenReady().then(async () => {
  registerIpcHandlers()

  // 1. Splash screen — await load so IPC listener is ready
  await createSplashWindow()
  const splashStartTime = Date.now()

  // 2. Packaged app: extract bundled backend to ~/.owlynn/runtime
  if (app.isPackaged) {
    try {
      await extractRuntimeBundle()
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      sendSplash('containers', 'error', 'Runtime extraction failed', msg.slice(0, 90))
      return
    }
  }

  const projectRoot = getProjectRoot()
  ensureOwlynnConfig(projectRoot)

  // 3. Start MVP containers (Postgres + StirlingPDF)
  try {
    await startContainers(projectRoot)
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    sendSplash('containers', 'error', 'Container runtime required', msg.slice(0, 90))
    return
  }

  // 4. Database — wait for Postgres, then run Alembic migrations
  try {
    await waitForPostgres()
    await runMigrations(projectRoot)
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    sendSplash('database', 'error', 'Database setup failed', msg)
    // Continue — backend may still start with degraded memory
  }

  // 5. Wait for LM Studio
  try {
    await waitForLMStudio()
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    sendSplash('lmstudio', 'error', 'LM Studio offline', `Port 1234: ${msg}`)
    // Continue anyway — backend can start and fall back to cloud/local
  }

  // 6. Start backend
  try {
    await killStaleBackend()
    await spawnBackend(projectRoot)
    sendSplash('backend', 'done', 'Backend running', 'Uvicorn server running on http://127.0.0.1:8000')
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    sendSplash('backend', 'error', `Backend failed: ${msg}`, `Process error: ${msg}`)
    return // Stay on splash — don't transition to broken main window
  }

  // 7. Wait for readiness
  try {
    await waitForHealth()
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    sendSplash('ready', 'error', `Startup timed out: ${msg}`, `Timeout waiting for agent readiness: ${msg}`)
    return // Stay on splash — don't transition to broken main window
  }

  // 8. Ensure splash was visible for at least 1.5s so user can read status
  const splashElapsed = Date.now() - splashStartTime
  if (splashElapsed < 1500) {
    await new Promise(r => setTimeout(r, 1500 - splashElapsed))
  }

  // 9. Switch to main window
  splashWin?.close()
  splashWin = null
  createMainWindow()
  createTray()
  launchBraveBrowser()
  maybeShowExtensionHint()
})

// ── Shutdown ─────────────────────────────────────────────────────

app.on('before-quit', async (e) => {
  if (!isQuitting) {
    e.preventDefault()
    isQuitting = true
    await gracefulShutdown()
    app.quit()
  }
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
