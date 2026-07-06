import { useEffect, useRef } from 'react'
import { useAppStore } from '../state/useAppStore'
import { electronBridge as tauriBridge } from '../lib/electronBridge'

export function ScreenAssistLivePanel() {
  const screenAssist = useAppStore((s) => s.screenAssist)
  const screenAssistEnabled = useAppStore((s) => s.screenAssistEnabled)

  const pollingRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Polling logic when enabled
  useEffect(() => {
    if (screenAssistEnabled) {
      // Immediate first capture
      void tauriBridge.startScreenPreview('screen')
      
      // Setup auto-request interval every 3 seconds
      pollingRef.current = setInterval(() => {
        void tauriBridge.startScreenPreview('screen')
      }, 3000)
    } else {
      // Clear interval and stop if disabled
      if (pollingRef.current) {
        clearInterval(pollingRef.current)
        pollingRef.current = null
      }
      void tauriBridge.stopScreenPreview()
    }

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current)
      }
    }
  }, [screenAssistEnabled])

  if (!screenAssistEnabled) {
    return null
  }

  const { mode, previewPath } = screenAssist

  return (
    <div className="pd-panel" style={{ flex: '0 0 auto', maxHeight: '300px', gridColumn: '1 / -1', marginBottom: 12 }}>
      <div className="pd-panel-header" style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span>Screen Assist Live</span>
        <span style={{ fontSize: 10, opacity: 0.5, color: mode === 'preview' ? '#4caf50' : '#888' }}>
          {mode === 'preview' ? 'Capturing live...' : 'Waiting for frame...'}
        </span>
      </div>
      <div style={{ 
        background: '#0c0c0c', 
        padding: 4, 
        borderRadius: 6, 
        border: '1px solid rgba(255,255,255,0.05)', 
        marginTop: 8,
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '150px'
      }}>
        {previewPath ? (
          <img 
            src={tauriBridge.convertFileSrc(previewPath)} 
            alt="Screen Assist Live Preview"
            style={{
              maxWidth: '100%',
              maxHeight: '250px',
              objectFit: 'contain',
              borderRadius: 4
            }}
          />
        ) : (
          <div style={{ color: '#666', fontSize: 12 }}>No frame captured yet.</div>
        )}
      </div>
    </div>
  )
}
