# Live Talk — Removed

**Status:** Fully removed from the codebase (2026-04-29 v2)  
**TTS retained:** Assistant responses are read aloud via macOS `say` (`speak_text` Tauri command)

## What happened

Live Talk (wake-word → WhisperKit transcription → LLM → TTS) was developed over several sessions but ultimately **removed** due to persistent echo/filler issues that could not be resolved with the current architecture.

## What was removed

| Component | Details |
|-----------|---------|
| **Swift helper** (`src-tauri/whisperkit-helper/`) | Entire directory deleted — WhisperKitEngine.swift, SoundAnalysisEngine.swift, main.swift, Package.swift |
| **Rust voice orchestration** (`voice/mod.rs`) | Stripped to just `speak_text` — removed `WhisperKitHelper`, `run_helper_pipeline`, `start_wake_listen`, `hard_stop_voice`, JSON extractors, `VoiceEvent` enum, all pipeline threading |
| **Rust Tauri commands** (`main.rs`) | Removed `hard_stop_voice`, `start_voice_listening`, `stop_voice_listening`, `get_wake_word_phrase`, `emit_voice_state`, `emit_voice_error`, `VoiceStartedPayload`, `WhisperKitHelper` from state |
| **Frontend `LiveTalkControls`** | Entire component file deleted |
| **Frontend store state** | Removed `voiceState`, `interimTranscript`, `voiceError`, `wakeWordListening`, `wakeWordPhrase` and all their setters |
| **Frontend voice event handlers** (`App.tsx`) | Removed all `voice.state`, `voice.transcript`, `voice.wake_word`, `voice.error`, `voice.started` handlers from both WS listener and Tauri event listener |
| **Frontend `tauriBridge`** | Removed `startVoiceListening`, `stopVoiceListening`, `hardStopVoice`, `getWakeWordPhrase` |
| **Frontend echo guards** | Removed `shouldSuppressVoiceTranscript`, `isTtsEcho`, `ttsSuppressionUntilRef`, `lastSpokenTextRef`, `ttsEchoWindowRef` |
| **Test file** | Removed LiveTalkControls test cases from `components.extended.test.tsx` |
| **Tauri config** | Removed `whisperkit-helper` resource bundling from `tauri.conf.json` |
| **AppShell** | Removed LiveTalk section and LiveTalkControls import |

## What remains

| Component | Details |
|-----------|---------|
| **TTS (`speak_text`)** | macOS `say` command. Fires automatically when `assistant.message` is received in Tauri runtime. Emits `voice.tts_state` events (`speaking: true/false`). |
| **`voice.tts_state` handler** | Frontend still listens for `voice.tts_state` events and updates `ttsSpeaking` store |
| **`VoiceEngineState`** | Kept in Rust for `tts_speaking` flag management |

## Documentation artifacts

The following docs record the implementation history for future reference:

- [`docs/LIVE_TALK_VOICE_PROCESSING_AND_VAD.md`](LIVE_TALK_VOICE_PROCESSING_AND_VAD.md) — Voice pipeline architecture, anti-filler layer
- [`docs/LIVE_TALK_WHISPER_FILLER_AND_FORCE_FINALIZE.md`](LIVE_TALK_WHISPER_FILLER_AND_FORCE_FINALIZE.md) — Filler hallucination debug analysis and all changes
- [`docs/LIVE_TALK_PHASE1_TTS_LOOP_FIX_2026-04-25.md`](LIVE_TALK_PHASE1_TTS_LOOP_FIX_2026-04-25.md) — Phase 1 mute/unmute implementation
- [`docs/SOUNDANALYSIS_WAKEWORD_ARCHITECTURE.md`](SOUNDANALYSIS_WAKEWORD_ARCHITECTURE.md) — Two-stage pipeline architecture
