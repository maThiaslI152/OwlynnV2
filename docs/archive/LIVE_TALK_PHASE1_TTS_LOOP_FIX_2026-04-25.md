# Live Talk Phase 1 Implementation (2026-04-25)

This document records the implementation work completed for the Live Talk
TTS feedback-loop blocker plan.

## Scope Implemented

Phase 1 tasks from `live_talk_feedback_loop_and_polish_02c392f2.plan.md` were implemented:

1. Helper-side mute/unmute gate
2. Rust-side mute/unmute orchestration around TTS
3. Korean voice detection bug fix
4. WhisperKit model path portability fix
5. WS/Tauri voice-listener guard
6. Wake-word auto-start on app launch

## File Changes

### Swift helper

- `src-tauri/whisperkit-helper/Sources/WhisperKitEngine.swift`
  - Added helper-local mute state (`isMuted`)
  - Added `setMuted(_:)`
  - Drops transcription buffers while muted
  - Keeps `audio_level` emission active while muted
  - Clears in-memory sample accumulator on mute
  - Removed hardcoded user path for model folder
  - Switched WhisperKit loading to `download: true` in both `preload()` and `start()`

- `src-tauri/whisperkit-helper/Sources/SoundAnalysisEngine.swift`
  - Added helper-local mute state (`isMuted`)
  - Added `setMuted(_:)`
  - Skips SoundAnalysis classification while muted
  - Text fallback wake-word trigger now respects mute

- `src-tauri/whisperkit-helper/Sources/main.swift`
  - Added command handling:
    - `mute` -> mutes WhisperKit + SoundAnalysis engines
    - `unmute` -> unmutes WhisperKit + SoundAnalysis engines

### Rust backend

- `src-tauri/src/voice/mod.rs`
  - Updated `speak_text(...)` signature to accept helper state
  - Sends `{"command":"mute"}` before launching `say`
  - Sends `{"command":"unmute"}` after `say` exits
  - Fixed inverted Korean Yuna voice availability check

- `src-tauri/src/main.rs`
  - Updated Tauri `speak_text` command handler to pass `state.helper.clone()`
  - Removed unused `Ordering` import

### Frontend

- `frontend-v2/src/App.tsx`
  - Added Tauri-runtime guard to prevent duplicate processing of `voice.*` events from WS path when native runtime events are available

- `frontend-v2/src/components/LiveTalkControls.tsx`
  - Added one-time auto-start effect for wake-word listening on mount
  - Preserves browser-preview compatibility by safely catching bridge absence

## Validation Performed

- `cargo build` in `src-tauri`: pass
- `npm run build` in `frontend-v2`: pass
- `swift build -c release` in `src-tauri/whisperkit-helper`: pass
- Helper protocol smoke test:
  - Sent commands: `mute`, `unmute`, `shutdown`
  - Verified no unknown-command errors after rebuild

## Remaining Validation (Manual Runtime)

The following manual checks are still recommended in an interactive Tauri run:

1. Start app and confirm wake-word auto-starts
2. Say "Athena" and confirm wake-word detection
3. Trigger assistant TTS and verify no transcript/wake-word events are emitted during playback
4. Confirm normal transcription resumes after TTS ends
5. Confirm Korean TTS selects Yuna when available

## Deferred (unchanged)

- Shared-tap architecture (single AVAudioEngine ownership)
- Full WS voice path removal for Tauri builds
- TTS engine quality upgrade
- Acoustic echo cancellation strategy

