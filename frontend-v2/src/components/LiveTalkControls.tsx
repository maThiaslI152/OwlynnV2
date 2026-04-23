import { useAppStore, type VoiceState } from '../state/useAppStore'
import { tauriBridge } from '../lib/tauriBridge'

const VOICE_SEQUENCE: VoiceState[] = ['recording', 'transcribing', 'speaking', 'interrupted', 'approval_pending', 'idle']

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
  const setVoiceState = useAppStore((s) => s.setVoiceState)
  const setOperatorNote = useAppStore((s) => s.setOperatorNote)

  const cycleState = () => {
    const idx = VOICE_SEQUENCE.indexOf(voiceState)
    const next = VOICE_SEQUENCE[(idx + 1) % VOICE_SEQUENCE.length]
    setVoiceState(next)
  }

  const startPtt = async () => {
    const result = await tauriBridge.startPushToTalk()
    if (!result.ok) {
      setOperatorNote(`Live Talk error: ${result.error}`)
      return
    }
    setOperatorNote(`Push-to-talk started`)
    setVoiceState('recording')
  }

  const stopPtt = async () => {
    const result = await tauriBridge.stopPushToTalk()
    if (!result.ok) {
      setOperatorNote(`Live Talk error: ${result.error}`)
      return
    }
    setOperatorNote(`Push-to-talk stopped`)
    setVoiceState('transcribing')
  }

  const hardStop = async () => {
    const result = await tauriBridge.hardStopVoice()
    if (!result.ok) {
      setOperatorNote(`Live Talk error: ${result.error}`)
      return
    }
    setOperatorNote(`Voice stopped`)
    setVoiceState('interrupted')
  }

  return (
    <div>
      <div className="row">
        <span className={`badge badge-${voiceState === 'idle' || voiceState === 'interrupted' ? 'success' : 'running'}`}>
          {VOICE_LABELS[voiceState]}
        </span>
        <button type="button" onClick={hardStop}>
          Hard Stop
        </button>
      </div>
      <div className="row">
        <button type="button" onClick={startPtt}>
          Push-to-Talk
        </button>
        <button type="button" onClick={stopPtt}>
          Release
        </button>
        <button type="button" onClick={cycleState}>
          Simulate
        </button>
      </div>
    </div>
  )
}
