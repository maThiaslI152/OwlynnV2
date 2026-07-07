import { useState, useEffect, useCallback, useRef } from 'react'

function getWsUrl(path: string): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  return `${proto}//${host}${path}`
}

export function LiveTerminal() {
  const [connected, setConnected] = useState(false)
  const [output, setOutput] = useState('')
  const [vmRunning, setVmRunning] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const preRef = useRef<HTMLPreElement>(null)
  const outputRef = useRef('')

  const checkVmStatus = useCallback(async () => {
    try {
      const token = localStorage.getItem('owlynn_local_run_token') || ''
      const resp = await fetch('/api/pentest/status', {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (resp.ok) {
        const data = await resp.json()
        setVmRunning(data?.lima?.running ?? false)
      }
    } catch { /* ignore */ }
  }, [])

  const connectWs = useCallback(() => {
    if (wsRef.current) return
    const token = localStorage.getItem('owlynn_local_run_token') || ''
    const url = getWsUrl(`/ws/pentest/terminal?token=${encodeURIComponent(token)}`)
    const ws = new WebSocket(url)

    ws.addEventListener('open', () => {
      setConnected(true)
    })

    ws.addEventListener('message', (event) => {
      try {
        const payload = JSON.parse(event.data)
        if (payload.type === 'pentest.terminal') {
          if (payload.snapshot) {
            outputRef.current = payload.snapshot
          } else if (payload.data) {
            outputRef.current += payload.data
            if (outputRef.current.length > 50000) {
              outputRef.current = outputRef.current.slice(-40000)
            }
          }
          setOutput(outputRef.current)
        } else if (payload.type === 'pentest.terminal_status') {
          setConnected(payload.connected)
        }
      } catch { /* ignore parse errors */ }
    })

    ws.addEventListener('close', () => {
      setConnected(false)
      wsRef.current = null
    })

    ws.addEventListener('error', () => {
      setConnected(false)
      wsRef.current = null
    })

    wsRef.current = ws
  }, [])

  useEffect(() => {
    void checkVmStatus()
    const int = setInterval(checkVmStatus, 15000)
    return () => clearInterval(int)
  }, [checkVmStatus])

  useEffect(() => {
    if (vmRunning && !wsRef.current) {
      connectWs()
    }
    return () => {
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [vmRunning, connectWs])

  useEffect(() => {
    if (preRef.current) {
      preRef.current.scrollTop = preRef.current.scrollHeight
    }
  }, [output])

  if (!vmRunning) return null

  return (
    <div className="pd-panel" style={{ flex: '0 0 auto', maxHeight: '350px', gridColumn: '1 / -1' }}>
      <div className="pd-panel-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>Kali Terminal</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            fontSize: 10,
            color: connected ? '#4ade80' : '#f87171',
            display: 'flex',
            alignItems: 'center',
            gap: 4,
          }}>
            <span style={{
              width: 6, height: 6, borderRadius: '50%',
              background: connected ? '#4ade80' : '#f87171',
              display: 'inline-block',
            }} />
            {connected ? 'LIVE' : 'DISCONNECTED'}
          </span>
          {!connected && vmRunning && (
            <button
              onClick={() => { wsRef.current?.close(); wsRef.current = null; connectWs() }}
              style={{
                fontSize: 10, padding: '2px 8px', borderRadius: 4,
                background: 'rgba(255,255,255,0.1)', color: '#a5d6a7',
                border: '1px solid rgba(255,255,255,0.1)', cursor: 'pointer',
              }}
            >
              Reconnect
            </button>
          )}
        </div>
      </div>
      <div style={{
        background: '#0a0a0a', padding: 8, borderRadius: 6,
        border: '1px solid rgba(255,255,255,0.05)', marginTop: 8,
        position: 'relative',
      }}>
        <pre
          ref={preRef}
          style={{
            margin: 0, fontSize: 11, fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
            color: '#a5d6a7', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
            maxHeight: '280px', overflowY: 'auto', lineHeight: 1.4,
            tabSize: 4,
          }}
        >
          {output || 'Waiting for terminal output...'}
        </pre>
      </div>
    </div>
  )
}
