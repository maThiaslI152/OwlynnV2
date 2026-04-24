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

  // Local draft for the input field — synced from the store on mount
  const [draftPhrase, setDraftPhrase] = useState(storedPhrase)

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

  const saveWakeWordPhrase = async () => {
    const trimmed = draftPhrase.trim()
    if (!trimmed) {
      setVoiceError('Wake-word phrase cannot be empty')
      return
    }
    const result = await tauriBridge.setWakeWordPhrase(trimmed)
    if (!result.ok) {
      setVoiceError(result.error ?? 'Failed to save wake-word phrase')
      setOperatorNote(`Live Talk error: ${result.error}`)
      return
    }
    setWakeWordPhrase(trimmed)
    setVoiceError(null)
    setOperatorNote(`Wake-word phrase saved: "${trimmed}"`)
  }

  const startPtt = async () => {
    const result = await tauriBridge.startPushToTalk()
    if (!result.ok) {
      setVoiceError(result.error ?? 'Failed to start push-to-talk')
      setOperatorNote(`Live Talk error: ${result.error}`)
      return
    }
    setVoiceError(null)
    setOperatorNote('Push-to-talk started')
  }

  const stopPtt = async () => {
    const result = await tauriBridge.stopPushToTalk()
    if (!result.ok) {
      setVoiceError(result.error ?? 'Failed to stop push-to-talk')
      setOperatorNote(`Live Talk error: ${result.error}`)
      return
    }
    setVoiceError(null)
    setOperatorNote('Push-to-talk stopped')
  }

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

    // Sync the current store phrase to Rust before starting
    if (storedPhrase.trim()) {
      await tauriBridge.setWakeWordPhrase(storedPhrase.trim())
    }

    const result = await tauriBridge.startVoiceListening()
    if (!result.ok) {
      setVoiceError(result.error ?? 'Failed to start wake-word listener')
      setOperatorNote(`Live Talk error: ${result.error}`)
      return
    }
    setVoiceError(null)
    setWakeWordListening(true)
    setOperatorNote(`Wake-word listening started (${storedPhrase.trim() || 'Hey Owlynn'})`)
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
          onChange={(e) => setDraftPhrase(e.target.value)}
          placeholder="Wake word phrase"
          aria-label="Wake-word phrase"
        />
        <button type="button" onClick={saveWakeWordPhrase}>
          Save
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
      <div className="row">
        <button type="button" onClick={startPtt}>
          Push-to-Talk
        </button>
        <button type="button" onClick={stopPtt}>
          Release
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
