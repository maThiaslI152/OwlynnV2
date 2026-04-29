import { useEffect, useState } from 'react'
import { useAppStore, type VoiceState } from '../state/useAppStore'
import { tauriBridge } from '../lib/tauriBridge'

const VOICE_LABELS: Record<VoiceState, string> = {
  idle: 'Idle',
  recording: 'Recording',
  transcribing: 'Transcribing',
  speaking: 'Speaking',
  interrupted: 'Interrupted',
  approval_pending: 'Approval pending',
}

export function LiveTalkControls() {
  const voiceState = useAppStore((s) => s.voiceState)
  const wakeWordListening = useAppStore((s) => s.wakeWordListening)
  const interimTranscript = useAppStore((s) => s.interimTranscript)
  const voiceError = useAppStore((s) => s.voiceError)
  const ttsSpeaking = useAppStore((s) => s.ttsSpeaking)
  const storedPhrase = useAppStore((s) => s.wakeWordPhrase)
  const setWakeWordListening = useAppStore((s) => s.setWakeWordListening)
  const setOperatorNote = useAppStore((s) => s.setOperatorNote)
  const setVoiceError = useAppStore((s) => s.setVoiceError)
  const setWakeWordPhrase = useAppStore((s) => s.setWakeWordPhrase)
  const voiceActive = !['idle', 'interrupted'].includes(voiceState)
  const [draftPhrase, setDraftPhrase] = useState('Athena')

  // Load the persisted phrase from Rust on mount
  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const result = await tauriBridge.getWakeWordPhrase()
        if (!cancelled && result.ok && result.data) {
          setWakeWordPhrase(result.data)
          setDraftPhrase(result.data)
        }
      } catch {
        // tauriBridge may not be available in all environments (e.g. tests without bridge)
      }
    }
    void load()
    return () => { cancelled = true }
  }, [setWakeWordPhrase])

  // Auto-start was removed — Live Talk is deferred to a future phase.
  // The UI controls remain as a placeholder for re-enabling later.

  const hardStop = async () => {
    const result = await tauriBridge.hardStopVoice()
    if (!result.ok) {
      setVoiceError(result.error ?? 'Failed to hard stop voice')
      setOperatorNote(`Live Talk error: ${result.error}`)
      return
    }
    setVoiceError(null)
    setWakeWordListening(false)
    setOperatorNote('Voice stopped')
  }

  const toggleWakeWord = async () => {
    if (wakeWordListening) {
      const result = await tauriBridge.stopVoiceListening()
      if (!result.ok) {
        setVoiceError(result.error ?? 'Failed to stop wake-word listener')
        setOperatorNote(`Live Talk error: ${result.error}`)
        return
      }
      setWakeWordListening(false)
      setOperatorNote('Wake-word listening stopped')
      return
    }

    const result = await tauriBridge.startVoiceListening()
    if (!result.ok) {
      setVoiceError(result.error ?? 'Failed to start wake-word listener')
      setOperatorNote(`Live Talk error: ${result.error}`)
      return
    }
    setVoiceError(null)
    setWakeWordListening(true)
    setOperatorNote('Wake-word listening started (Athena)')
  }

  return (
    <div>
      <div className={`live-talk-wave ${voiceActive ? 'live-talk-wave-active' : ''}`} aria-hidden="true">
        <span />
        <span />
        <span />
        <span />
        <span />
      </div>
      <div className="row">
        <span className={`badge badge-${voiceState === 'idle' || voiceState === 'interrupted' ? 'success' : 'running'}`}>
          {VOICE_LABELS[voiceState]}
        </span>
        <span className={`badge badge-${wakeWordListening ? 'running' : 'muted'}`}>
          {wakeWordListening ? 'Wake-word on' : 'Wake-word off'}
        </span>
        <span className={`badge badge-${ttsSpeaking ? 'running' : 'muted'}`}>
          {ttsSpeaking ? 'Speaking' : 'Silent'}
        </span>
        <button type="button" onClick={hardStop}>
          Hard Stop
        </button>
      </div>
      <div className="row">
        <input
          type="text"
          className="memory-search-input"
          value={draftPhrase}
          onChange={() => {}}
          placeholder="Wake word phrase"
          aria-label="Wake-word phrase"
          disabled
        />
        <button type="button" disabled>
          Fixed
        </button>
      </div>
      <div className="row row-status">
        <span className="badge badge-muted" title="Currently saved phrase">
          {storedPhrase}
        </span>
        <button type="button" onClick={toggleWakeWord}>
          {wakeWordListening ? 'Disable Wake-word' : 'Enable Wake-word'}
        </button>
      </div>
      <div className="tool-empty-preview">
        <div className="tool-empty-title">Transcript preview</div>
        <div className="tool-empty-row">{interimTranscript || 'No voice transcript yet.'}</div>
      </div>
      {voiceError ? <p className="operator-note">ⓘ Voice error: {voiceError}</p> : null}
    </div>
  )
}
