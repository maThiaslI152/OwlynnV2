import { useAppStore } from '../state/useAppStore'
import { electronBridge as defaultBridge } from '../lib/electronBridge'

interface ScreenAssistPanelProps {
  bridge?: {
    startScreenPreview: (source: string) => Promise<{ ok: boolean; error?: string; data?: string }>
    stopScreenPreview: () => Promise<{ ok: boolean; error?: string; data?: string }>
    convertFileSrc: (path: string) => string
  }
}

export function ScreenAssistPanel({ bridge }: ScreenAssistPanelProps) {
  const screenAssist = useAppStore((s) => s.screenAssist)
  const setMode = useAppStore((s) => s.setScreenAssistMode)
  const setSource = useAppStore((s) => s.setScreenAssistSource)
  const setOperatorNote = useAppStore((s) => s.setOperatorNote)
  const activeBridge = bridge ?? defaultBridge
  const previewSrc = screenAssist.previewPath ? activeBridge.convertFileSrc(screenAssist.previewPath) : ''

  const startPreview = async () => {
    const result = await activeBridge.startScreenPreview(screenAssist.source)
    if (!result.ok) {
      setOperatorNote(`Screen Assist error: ${result.error}`)
      return
    }
    setMode('preview')
    setOperatorNote(`Screen preview started`)
  }

  const startAnnotating = async () => {
    const result = await activeBridge.startScreenPreview(screenAssist.source)
    if (!result.ok) {
      setOperatorNote(`Screen Assist error: ${result.error}`)
      return
    }
    setMode('annotating')
    setOperatorNote(`Screen annotate started`)
  }

  const stopPreview = async () => {
    const result = await activeBridge.stopScreenPreview()
    if (!result.ok) {
      setOperatorNote(`Screen Assist error: ${result.error}`)
      return
    }
    setMode('off')
    setOperatorNote(`Screen preview stopped`)
  }

  // Capture and send to backend for analysis
  const captureAndAnalyze = async () => {
    const result = await activeBridge.startScreenPreview(screenAssist.source)
    if (!result.ok) {
      setOperatorNote(`Capture error: ${result.error}`)
      return
    }
    setMode('preview')
    if (result.data) {
      setOperatorNote(`Captured ${screenAssist.source}. Ask Owlynn about it.`)
    }
  }

  return (
    <div>
      <label>
        Source
        <select value={screenAssist.source} onChange={(e) => setSource(e.target.value as 'screen' | 'window' | 'region')}>
          <option value="screen">Screen</option>
          <option value="window">Window</option>
          <option value="region">Region</option>
        </select>
      </label>
      <div className="row">
        <button type="button" data-testid="screen-assist-btn" onClick={captureAndAnalyze} title={`Capture ${screenAssist.source}`}>
          Capture
        </button>
        <button type="button" onClick={startPreview}>
          Preview
        </button>
        <button type="button" onClick={startAnnotating}>
          Annotate
        </button>
        <button type="button" onClick={stopPreview}>
          Stop
        </button>
      </div>
      <p className="meta">
        Mode: {screenAssist.mode === 'off' ? 'Off' : screenAssist.mode}
        {screenAssist.source && ` · ${screenAssist.source}`}
      </p>
      {screenAssist.previewPath ? (
        <div className="preview-box">
          {previewSrc ? <img src={previewSrc} alt="screen capture" /> : null}
        </div>
      ) : null}
    </div>
  )
}
