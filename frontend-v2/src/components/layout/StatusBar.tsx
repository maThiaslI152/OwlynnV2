import { useState, useRef, useEffect } from 'react'
import {
  Circle,
  Database,
  Cpu,
  Cloud,
  CloudOff,
  Server,
  ChevronUp,
  Globe,
  Activity,
} from 'lucide-react'
import { useAppStore } from '../../state/useAppStore'
import { CloudUsagePanel } from '../shared/CloudUsagePanel'
import { OrchestrationPanel } from '../shared/OrchestrationPanel'
import { SystemInfoCard } from '../shared/SystemInfoCard'

// ── Popover ────────────────────────────────────────────────────────────────────
function StatusPopover({
  anchorRef,
  onClose,
  children,
}: {
  anchorRef: React.RefObject<HTMLButtonElement | null>
  onClose: () => void
  children: React.ReactNode
}) {
  const popoverRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (
        popoverRef.current &&
        !popoverRef.current.contains(e.target as Node) &&
        anchorRef.current &&
        !anchorRef.current.contains(e.target as Node)
      ) {
        onClose()
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [anchorRef, onClose])

  const [pos, setPos] = useState({ bottom: 30, left: 0 })
  useEffect(() => {
    if (anchorRef.current) {
      const rect = anchorRef.current.getBoundingClientRect()
      setPos({
        bottom: window.innerHeight - rect.top + 4,
        left: Math.min(rect.left, window.innerWidth - 340),
      })
    }
  }, [anchorRef])

  return (
    <div
      ref={popoverRef}
      className="sb-popover"
      style={{ position: 'fixed', bottom: pos.bottom, left: pos.left }}
    >
      {children}
    </div>
  )
}

// ── Connection dot ─────────────────────────────────────────────────────────────
function ConnectionDot({ state }: { state: string }) {
  const color =
    state === 'connected'
      ? 'var(--green)'
      : state === 'connecting' || state === 'reconnecting'
        ? 'var(--amber)'
        : state === 'error'
          ? 'var(--red)'
          : 'var(--text-muted)'

  const label =
    state === 'connected'
      ? 'Connected'
      : state === 'connecting'
        ? 'Connecting'
        : state === 'reconnecting'
          ? 'Reconnecting'
          : state === 'error'
            ? 'Error'
            : 'Disconnected'

  return (
    <span className="sb-segment sb-connection" title={label}>
      <Circle
        size={7}
        fill={color}
        stroke="none"
        className={
          state === 'connecting' || state === 'reconnecting'
            ? 'sb-dot-pulse'
            : ''
        }
        style={{ color }}
      />
      <span className="sb-label">{label}</span>
    </span>
  )
}

// ── Main StatusBar ─────────────────────────────────────────────────────────────
export function StatusBar() {
  const connectionState = useAppStore((s) => s.connectionState)
  const cloudStatus = useAppStore((s) => s.cloudStatus)
  const cloudUsage = useAppStore((s) => s.cloudUsage)
  const routerMetadata = useAppStore((s) => s.routerMetadata)
  const modelInfo = useAppStore((s) => s.modelInfo)
  const memoryUpdatedAt = useAppStore((s) => s.memoryUpdatedAt)
  const pentestVmStatus = useAppStore((s) => s.pentestVmStatus)
  const activeMode = useAppStore((s) => s.activeMode)

  const [openPopover, setOpenPopover] = useState<'model' | 'cloud' | 'system' | null>(null)
  const modelBtnRef = useRef<HTMLButtonElement>(null)
  const cloudBtnRef = useRef<HTMLButtonElement>(null)
  const systemBtnRef = useRef<HTMLButtonElement>(null)
  const [extConnected, setExtConnected] = useState<boolean>(false)

  useEffect(() => {
    const checkExt = async () => {
      try {
        const r = await fetch('/api/browser_extension/status')
        if (r.ok) {
          const d = await r.json()
          setExtConnected(!!d.connected)
        }
      } catch {
        setExtConnected(false)
      }
    }
    void checkExt()
    const interval = setInterval(checkExt, 5000)
    return () => clearInterval(interval)
  }, [])

  const route = routerMetadata?.route as string | undefined
  const confidence = routerMetadata?.confidence as number | undefined
  const confidencePct =
    confidence !== undefined
      ? Math.max(0, Math.min(100, Math.round(confidence * 100)))
      : null

  const modelDisplay = modelInfo
    ? modelInfo.length > 24
      ? modelInfo.slice(0, 22) + '\u2026'
      : modelInfo
    : 'Local'

  const isCloud =
    Boolean(modelInfo?.includes('cloud') || modelInfo?.includes('deepseek'))

  const sessionCost = cloudUsage?.session?.estimated_cost_usd
  const hasCost = sessionCost != null && (cloudUsage?.session.total_calls ?? 0) > 0
  const costStr = hasCost ? `$${sessionCost!.toFixed(3)}` : null
  const memoryRecent = !!memoryUpdatedAt

  return (
    <div className="status-bar">
      <ConnectionDot state={connectionState} />
      <span className="sb-divider" />

      {/* Model & Routing */}
      <button
        ref={modelBtnRef}
        type="button"
        className="sb-segment sb-btn"
        onClick={() => setOpenPopover(openPopover === 'model' ? null : 'model')}
        title="Routing & model details"
      >
        {isCloud ? <Cloud size={11} /> : <Cpu size={11} />}
        <span className="sb-label">{modelDisplay}</span>
        {route && (
          <>
            <span className="sb-divider-inline">/</span>
            <span className="sb-route">{route}</span>
          </>
        )}
        {confidencePct !== null && (
          <span className="sb-confidence">{confidencePct}%</span>
        )}
        <ChevronUp size={10} className="sb-chevron" />
      </button>

      {/* Brave / Extension Status */}
      <span className="sb-divider" />
      <span
        className="sb-segment"
        title={extConnected ? 'Brave Extension: Connected' : 'Brave Extension: Disconnected'}
      >
        <Globe size={11} style={{ color: extConnected ? 'var(--green)' : 'var(--text-muted)' }} />
        <span className="sb-label">Brave Ext</span>
        <Circle
          size={5}
          fill={extConnected ? 'var(--green)' : 'var(--amber)'}
          stroke="none"
          style={{ color: extConnected ? 'var(--green)' : 'var(--amber)' }}
        />
      </span>

      {/* System Infrastructure Health Button */}
      <span className="sb-divider" />
      <button
        ref={systemBtnRef}
        type="button"
        className="sb-segment sb-btn"
        onClick={() => setOpenPopover(openPopover === 'system' ? null : 'system')}
        title="System infrastructure health"
      >
        <Activity size={11} style={{ color: 'var(--accent)' }} />
        <span className="sb-label">System</span>
        <ChevronUp size={10} className="sb-chevron" />
      </button>

      {memoryRecent && (
        <>
          <span className="sb-divider" />
          <span className="sb-segment" title="Memory saved recently">
            <Database size={11} style={{ color: 'var(--green)' }} />
          </span>
        </>
      )}

      <span className="sb-spacer" />

      {costStr ? (
        <>
          <button
            ref={cloudBtnRef}
            type="button"
            className="sb-segment sb-btn sb-cost"
            onClick={() => setOpenPopover(openPopover === 'cloud' ? null : 'cloud')}
            title="Cloud usage details"
          >
            <Cloud size={11} />
            <span className="sb-label">{costStr}</span>
          </button>
          <span className="sb-divider" />
        </>
      ) : (
        <>
          <span
            className="sb-segment"
            title={cloudStatus?.available ? 'Cloud available' : 'Cloud unavailable'}
          >
            {cloudStatus?.available ? (
              <Cloud size={11} style={{ color: 'var(--accent)' }} />
            ) : (
              <CloudOff size={11} style={{ color: 'var(--text-muted)' }} />
            )}
          </span>
          <span className="sb-divider" />
        </>
      )}

      {activeMode === 'pentest' && pentestVmStatus && (
        <>
          <span
            className="sb-segment"
            title={`Kali VM: ${pentestVmStatus.running ? 'running' : 'stopped'}`}
          >
            <Server size={11} />
            <span className="sb-label">Kali</span>
            <Circle
              size={6}
              fill={pentestVmStatus.running ? 'var(--green)' : 'var(--amber)'}
              stroke="none"
              style={{ color: pentestVmStatus.running ? 'var(--green)' : 'var(--amber)' }}
            />
          </span>
          <span className="sb-divider" />
        </>
      )}

      {openPopover === 'model' && (
        <StatusPopover anchorRef={modelBtnRef} onClose={() => setOpenPopover(null)}>
          <div className="sb-popover-title">Routing &amp; Model</div>
          <OrchestrationPanel />
        </StatusPopover>
      )}

      {openPopover === 'cloud' && (
        <StatusPopover anchorRef={cloudBtnRef} onClose={() => setOpenPopover(null)}>
          <div className="sb-popover-title">Cloud Usage</div>
          <CloudUsagePanel />
        </StatusPopover>
      )}

      {openPopover === 'system' && (
        <StatusPopover anchorRef={systemBtnRef} onClose={() => setOpenPopover(null)}>
          <div className="sb-popover-title">Infrastructure Health</div>
          <div style={{ width: 280, padding: 8 }}>
            <SystemInfoCard />
          </div>
        </StatusPopover>
      )}
    </div>
  )
}
