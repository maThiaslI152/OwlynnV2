# Live Talk — Deferred

**Status:** Placeholder / deferred to a future phase  
**Date:** 2026-04-29

## What happened

Live Talk (wake-word → WhisperKit transcription → LLM → TTS) was developed over several sessions but ultimately **placed on hold** due to persistent echo/filler issues that could not be resolved with the current architecture.

## What remains

- **UI (`LiveTalkControls` component):** Stays in the frontend as a visual placeholder. Wake-word **no longer auto-starts** on mount.
- **Swift helper binaries:** The Rust `WhisperKitHelper` and Swift `whisperkit-helper` code remain in the repo. Builds via `swift build -c release` in `src-tauri/whisperkit-helper/`.
- **Rust orchestration (`voice/mod.rs`):** All commands (`start_voice_listening`, `stop_voice_listening`, `hard_stop_voice`, `speak_text`) remain registered as Tauri commands.
- **TTS (`speak_text`):** The `say` command and `VoiceEngineState` are preserved. Currently only fires when `wakeWordListening` is true (which it isn't by default). Could be re-enabled independently.
- **Anti-filler forced-finalization:** The Rust-side forced-finalization logic in `run_helper_pipeline` remains in place for future use.
- **Hallucination filter (`isHallucinatedFiller`):** The expanded Swift filter remains in `WhisperKitEngine.swift`.
- **Frontend echo guards:** The 3s cooldown, `isTtsEcho()`, and echo window guards remain in `App.tsx`.

## What was removed / reverted

| Change | Reason |
|--------|--------|
| Wake-word auto-start on mount | Prevents unwanted mic activation |
| `engine.inputNode.setVoiceProcessingEnabled(true)` | Aggressive AEC suppressed mic input entirely |

## Known issues (for future re-activation)

1. **Whisper filler hallucinations:** WhisperKit hallucinates "Thank you." etc. from silence. Mitigated with Swift filter + Rust anti-filler layer but not fully solved.
2. **Finalization race:** WhisperKit's sliding-window finalization requires consecutive matching windows. Under some acoustic conditions windows differ, preventing `is_final: true` emission for real user speech.
3. **No auto-stop:** After wake-word → transcript, the pipeline stays in transcribe mode indefinitely (auto-stop VAD was removed due to echo loops). User must manually stop.
4. **Echo loop:** TTS playback re-captured by microphone. Mitigated via mute/unmute + cooldowns + frontend guards, but residual cases remain.

## Repo artifacts

All implementation history is preserved in these docs for future reference:

- [`docs/LIVE_TALK_VOICE_PROCESSING_AND_VAD.md`](LIVE_TALK_VOICE_PROCESSING_AND_VAD.md) — Voice pipeline architecture, anti-filler layer
- [`docs/LIVE_TALK_WHISPER_FILLER_AND_FORCE_FINALIZE.md`](LIVE_TALK_WHISPER_FILLER_AND_FORCE_FINALIZE.md) — Filler hallucination debug analysis and all changes
- [`docs/LIVE_TALK_PHASE1_TTS_LOOP_FIX_2026-04-25.md`](LIVE_TALK_PHASE1_TTS_LOOP_FIX_2026-04-25.md) — Phase 1 mute/unmute implementation
- [`docs/SOUNDANALYSIS_WAKEWORD_ARCHITECTURE.md`](SOUNDANALYSIS_WAKEWORD_ARCHITECTURE.md) — Two-stage pipeline architecture
- `src-tauri/src/voice/mod.rs` — Rust orchestration
- `src-tauri/whisperkit-helper/Sources/` — Swift helper (WhisperKit + SoundAnalysis engines)
- `frontend-v2/src/components/LiveTalkControls.tsx` — Placeholder UI
