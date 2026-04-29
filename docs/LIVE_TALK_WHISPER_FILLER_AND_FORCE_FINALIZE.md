# Live Talk Whisper Filler Hallucination & Forced Finalization (2026-04-25)

## Problem: Valid user transcript never reaches LLM

### User report

> "Is said "what is one plus one" and it does prescribe correctly but not go into prompt instead if just thank you again Voice stopped"

### Observed behavior

1. User says "what is one plus one"
2. Frontend interim transcript shows the correct phrase
3. WhisperKit **never emits `is_final: true`** for the user's speech
4. After ~1–3 seconds of silence, WhisperKit hallucinates "Thank you."
5. "Thank you." is emitted as `is_final: true` and sent to the LLM
6. Assistant responds to "Thank you." → echo loop begins
7. "Voice stopped" appears (user clicks Hard Stop to break loop)

### Root cause

WhisperKit's `transcribeChunk` works on **sliding ~3-second windows with ~1-second stride**. The finalization logic (lines 306–318 of WhisperKitEngine.swift) emits `is_final: true` only when two consecutive windows produce the **same text**. The sequence is:

```
Window 1: user speech + trailing silence
  → "what is one plus one" (new text)
  → emitted as is_final: false, lastEmittedText = "what is one plus one"

Window 2: trailing silence (user stopped speaking)
  → "what is one plus one" (repeats)
  → emitted as is_final: true ✅

Window 3: pure silence
  → Whisper hallucinates "Thank you." (different text)
  → emitted as is_final: false, lastEmittedText = "Thank you."

Window 4: silence
  → "Thank you." (repeats)
  → isHallucinatedFiller() returns true → SUPPRESSED
```

**The problem:** Under certain acoustic conditions (especially with `AVAudioEngine.setVoiceProcessingEnabled(true)` which applies AEC/noise suppression), window 2 might not produce the same text as window 1. The acoustic processing can shift audio characteristics enough that Whisper's output changes between windows, preventing the finalization logic from matching.

When window 2 doesn't match, Whisper slides into silence windows and hallucinates filler text (most commonly "Thank you.") which then matches across windows and becomes the first finalized transcript.

### Secondary issue: "when activated it doesn't record my voice"

After `AVAudioEngine.inputNode.setVoiceProcessingEnabled(true)` was applied to both engines (WhisperKitEngine and SoundAnalysisEngine), the user reported that the wake word activates but **no voice is captured afterward**.

Probable cause: The voice processing AEC reference path may be muting the microphone when it detects its own output as "echo" to cancel. When `voiceProcessingEnabled` is true on macOS, the audio system applies aggressive echo cancellation that can suppress microphone input when it correlates with system audio output — even when no TTS is actively playing. The wake word classifier may trigger on residual audio, but the transcription engine's voice-processed input may be heavily suppressed.

## Changes made (this session)

### 1. Rust-side anti-filler forced-finalization ([`src-tauri/src/voice/mod.rs`](../src-tauri/src/voice/mod.rs))

The Rust `run_helper_pipeline` now tracks the **last meaningful transcript** text. When a short (<10 chars) filler-like transcript arrives that is different from the current meaningful one, Rust:

- **Force-finalizes** the meaningful text (emits `VoiceEvent::Transcript(text, true, confidence)`)
- **Drops** the filler entirely (doesn't forward to frontend)

Additionally, when a transcript matches the last meaningful text but hasn't been confirmed as final by WhisperKit yet, Rust overrides `is_final = true`.

```
Rust transcript handler logic:

1. Receive transcript {"text": "what is one plus one", "is_final": false}
   → last_meaningful_text = "what is one plus one"
   → Forward to frontend (as interim)

2. Receive transcript {"text": "Thank you.", "is_final": false}
   → is_filler? text.len() < 10 && last.len() > text.len() * 2 → YES
   → Force-finalize last_meaningful_text "what is one plus one" as is_final: true
   → Drop "Thank you." entirely
```

**Constants used:**
- Filler detection: `text.len() < 10` (very short)
- Must be significantly shorter: `last.len() > text.len() * 2` (meaningful text at least 2x longer)
- Case-insensitive comparison prevents matching the same text

Also: when the pipeline exits via `stop_flag`, any pending meaningful transcript is force-finalized before cleanup.

### 2. Enhanced Swift hallucination filter ([`WhisperKitEngine.swift`](../src-tauri/whisperkit-helper/Sources/WhisperKitEngine.swift))

- Added more filler variants: "Thank", "Thanks", "You're welcome", "Thank you for the question.", "Thank you for asking.", "Thank you for listening."
- Changed word-count threshold from `<=2` to `<=3` (more aggressive filtering)
- For 2–3 word phrases: only pass through if they look like real questions (contain "what", "how", "why", etc.) or contain digits
- Single-word `allowedShort` list preserved (hi, hello, yes, no, rust, go, etc.)

### 3. Post-unmute cooldown in SoundAnalysisEngine ([`SoundAnalysisEngine.swift`](../src-tauri/whisperkit-helper/Sources/SoundAnalysisEngine.swift))

- Added `postUnmuteCooldownUntil` property (3-second cooldown after unmute)
- Audio tap callback now checks `!isMuted && Date() >= postUnmuteCooldownUntil`
- Prevents wake-word re-triggering from residual room echo after TTS

### 4. Frontend echo guard improvements ([`App.tsx`](../../frontend-v2/src/App.tsx))

- Increased post-TTS suppression from 1200ms → **3000ms**
- Added `lastSpokenTextRef` and `ttsEchoWindowRef` for content-aware echo filtering
- `isTtsEcho()` function: checks bidirectional containment and >50% word overlap
- TTS echo window set to 15 seconds from TTS start
- Clears `interimTranscript` on `voice.state` transitions to `recording`/`idle` to avoid stale preview

### 5. Apple voice processing enabled ([`WhisperKitEngine.swift`](../src-tauri/whisperkit-helper/Sources/WhisperKitEngine.swift), [`SoundAnalysisEngine.swift`](../src-tauri/whisperkit-helper/Sources/SoundAnalysisEngine.swift))

Both engines now call `engine.inputNode.setVoiceProcessingEnabled(true)`. This enables AEC + noise suppression + AGC from the OS audio pipeline.

**Result:** The user reported "it doesn't record my voice" after this change — the voice processing was too aggressive. The fix should be to **remove** this flag (revert to software-only muting) since the combination of:
- Helper mute/unmute during TTS
- Post-unmute cooldowns
- Rust anti-filler finalization
- Frontend echo guards

provide sufficient echo suppression without hardware AEC side effects.

## File-by-file change summary

| File | Changes |
|------|---------|
| `src-tauri/src/voice/mod.rs` | Force-finalize meaningful transcripts when hallucinated filler arrives; drop filler; finalize pending text on shutdown |
| `src-tauri/whisperkit-helper/Sources/WhisperKitEngine.swift` | Hallucination filter (expanded set + 3-word threshold), `postUnmuteCooldownUntil`, `voiceProcessingEnabled`, sample accumulator clear on mute |
| `src-tauri/whisperkit-helper/Sources/SoundAnalysisEngine.swift` | `postUnmuteCooldownUntil` + `voiceProcessingEnabled` |
| `src-tauri/src/main.rs` | Pass `engine_state` to `start_wake_listen` |
| `frontend-v2/src/App.tsx` | 3s post-TTS cooldown, content-aware echo guard (`isTtsEcho`), clear interim on state change |
| `docs/LIVE_TALK_VOICE_PROCESSING_AND_VAD.md` | Updated to reflect anti-filler layer in Rust |
| `docs/STATUS.md` | Updated status + latest debug notes |
| `docs/ADR.md`, `README.md`, `docs/AI_AGENT_INDEX.md`, `docs/SOUNDANALYSIS_WAKEWORD_ARCHITECTURE.md` | Model name update from `distil-large-v3` → `openai_whisper-large-v3-v20240930_turbo` |

## Current known issues (as of 2026-04-25)

1. **Voice processing mutes mic**: `setVoiceProcessingEnabled(true)` appears to suppress microphone input too aggressively on this setup. Recommended: revert it, or make it configurable.
2. **Finalization race**: Even with Rust anti-filler, if meaningful text never gets to `last_meaningful_text` before filler arrives (e.g. first window is already filler), the forced-finalization can't help. Current Swift hallucination filter should catch those cases.
3. **Continuous transcription**: After wake-word → transcript, the pipeline stays in transcribe mode indefinitely. No auto-stop/re-arm-wake-word logic is active (removed in earlier session due to echo loops). User must manually stop.
