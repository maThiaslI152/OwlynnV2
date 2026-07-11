

interface ModeSwitchModalProps {
  targetMode: 'normal' | 'study' | 'pentest'
  currentMode: 'normal' | 'study' | 'pentest'
  onConfirm: () => void
  onCancel: () => void
}

const overlayStyle: React.CSSProperties = {
  position: 'fixed',
  inset: 0,
  background: 'rgba(0,0,0,0.7)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 9999,
  backdropFilter: 'blur(4px)',
}

const modalStyle: React.CSSProperties = {
  background: '#1a1a2e',
  borderRadius: 12,
  padding: '28px 32px',
  maxWidth: 420,
  width: '90%',
  border: '1px solid rgba(255,255,255,0.1)',
  boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
}

const btnBase: React.CSSProperties = {
  padding: '8px 20px',
  borderRadius: 6,
  fontSize: 13,
  fontWeight: 500,
  border: 'none',
  cursor: 'pointer',
  transition: 'all 0.15s',
}

const btnPrimary: React.CSSProperties = {
  ...btnBase,
  background: '#e94560',
  color: '#fff',
}

const btnSecondary: React.CSSProperties = {
  ...btnBase,
  background: 'rgba(255,255,255,0.08)',
  color: 'rgba(255,255,255,0.7)',
  border: '1px solid rgba(255,255,255,0.1)',
}

const spinnerStyle: React.CSSProperties = {
  width: 32,
  height: 32,
  border: '3px solid rgba(233,69,96,0.2)',
  borderTopColor: '#e94560',
  borderRadius: '50%',
  animation: 'spin 0.8s linear infinite',
  margin: '0 auto 16px',
}
import { useAppStore } from '../../state/useAppStore'

export function ModeSwitchConfirmation({
  targetMode,
  onConfirm,
  onCancel,
}: ModeSwitchModalProps) {
  const isEntering = targetMode === 'pentest'
  const isEcoMode = useAppStore(state => state.isEcoMode)

  return (
    <div style={overlayStyle} onClick={onCancel}>
      <div style={modalStyle} onClick={(e) => e.stopPropagation()}>
        <div style={{ textAlign: 'center', marginBottom: 20 }}>
          <div style={{ fontSize: 28, marginBottom: 8 }}>
            {isEntering ? '!' : '<'}
          </div>
          <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>
            {isEntering ? 'Switch to Pentest Mode?' : 'Exit Pentest Mode?'}
          </div>
        </div>

        <div style={{ fontSize: 12, lineHeight: 1.8, color: 'rgba(255,255,255,0.6)', marginBottom: 24 }}>
          {isEntering ? (
            <>
              {isEcoMode && (
                <div style={{ color: '#e94560', fontWeight: 'bold', marginBottom: 8, padding: 8, background: 'rgba(233,69,96,0.1)', borderRadius: 6, border: '1px solid rgba(233,69,96,0.3)' }}>
                  ⚠️ Warning: Mac is on battery (Eco-Mode active).
                  Running Kali VM and the Pentest Model is highly power intensive. 
                  Please connect to a power adapter to prevent performance degradation or battery drain.
                </div>
              )}
              <div>- Kali VM will start (~30-60s cold boot)</div>
              <div>- Local pentest model (Gemma 4 12B)</div>
              <div>- Workspace and chats will be hidden</div>
              <div>- Cloud APIs will be disabled</div>
              <div>- All work stays local</div>
            </>
          ) : (
            <>
              <div>- Kali VM will keep running (~2GB RAM)</div>
              <div>- Stop it later from the sidebar</div>
              <div>- Engagement data will be preserved</div>
              <div>- Workspace and chats will reappear</div>
            </>
          )}
        </div>

        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button type="button" style={btnSecondary} onClick={onCancel}>
            Cancel
          </button>
          <button type="button" style={btnPrimary} onClick={onConfirm}>
            {isEntering ? 'Switch to Pentest' : 'Exit Pentest'}
          </button>
        </div>
      </div>
    </div>
  )
}


interface PentestLoadingProps {
  status: string
}

export function PentestLoadingOverlay({ status }: PentestLoadingProps) {
  return (
    <div style={overlayStyle}>
      <div style={{ ...modalStyle, textAlign: 'center' }}>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        <div style={spinnerStyle} />
        <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>
          Starting Pentest Mode
        </div>
        <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.5)' }}>
          {status || 'Initializing...'}
        </div>
      </div>
    </div>
  )
}
