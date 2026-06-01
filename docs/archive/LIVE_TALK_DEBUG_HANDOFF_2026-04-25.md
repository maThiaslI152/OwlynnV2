---
status: archived
category: archive
last_updated: 2026-05-31
owner: human
---

# Live Talk Debug Handoff (2026-04-25)

## Scope

This handoff captures the current state of Live Talk after CoreML wake-word integration and post-integration debugging. Work is paused with one remaining blocker: intermittent TTS feedback loop.

## What Is Working

- CoreML wake-word (`Athena`) detection triggers reliably.
- Wake-word -> transcription mode transition is firing.
- WhisperKit model preload pathway exists (`preload_whisper`) to reduce repeated cold starts.
- Helper process lifecycle now keeps process alive during normal start/stop voice listening cycles.
- Raw control tokens are cleaned from transcript output before UI submit.

## Implemented Changes in This Debug Window

### 1) WhisperKit output cleanup and decode guardrails

File: `src-tauri/whisperkit-helper/Sources/WhisperKitEngine.swift`

- Added decode option `skipSpecialTokens: true`.
- Added transcript sanitization for `<|...|>` artifacts via regex stripping.
- Added text normalization before emit.

### 2) Audio normalization toward Whisper expected input

File: `src-tauri/whisperkit-helper/Sources/WhisperKitEngine.swift`

- Added normalization/downsampling path toward 16k input windows before transcribe calls.
- Kept 3s/1s window-step streaming behavior.

### 3) Helper preload + lifecycle stability

Files:
- `src-tauri/src/voice/mod.rs`
- `src-tauri/whisperkit-helper/Sources/main.swift`
- `src-tauri/whisperkit-helper/Sources/WhisperKitEngine.swift`

- Added `preload_whisper` command support in helper main loop.
- Rust pipeline sends preload on fresh helper spawn.
- Normal stop path keeps helper alive; hard stop still kills process.

### 4) Frontend feedback-loop suppression (partial mitigation)

File: `frontend-v2/src/App.tsx`

- Added suppression guard to ignore `voice.transcript` while TTS is speaking.
- Added short cooldown (~1200ms) after TTS ends before accepting voice transcript.
- Applied to both WS runtime path and Tauri runtime-event listener path.

## Remaining Blocker

- **Intermittent feedback loop remains**:
  - Assistant TTS is sometimes still captured and re-submitted as user message.
  - Current frontend-only suppression is not sufficient under all timing paths.

## Most Likely Root Cause

Multiple transcript ingestion paths and race timing around TTS end can still admit assistant audio into final transcript handling. Frontend gating helps but cannot guarantee suppression if transcript is already finalized upstream before the gate or if timing crosses suppression boundary.

## Recommended Next Fixes (Priority Order)

1. **Backend-side hard gate (required)**
   - Drop `voice.transcript` forwarding while `tts_speaking` flag is true (+ cooldown).
   - Enforce this in one canonical ingestion point, not only UI layer.

2. **Helper-side gate (strongly recommended)**
   - On TTS start: issue `transcribe_stop` immediately or mute transcript emits.
   - Resume transcribe only after explicit post-TTS delay.

3. **Single source-of-truth voice state machine**
   - Consolidate wake-word, recording, and tts_speaking transitions in Rust.
   - Avoid dual-path final transcript submission race.

4. **Optional acoustic echo control**
   - Prefer headset mode when available.
   - Consider platform AEC configuration if/when AVAudioSession/IO unit path is introduced.

## Validation Checklist for Next Session

- [ ] Say wake-word + command while silent room; verify single user message only.
- [ ] Let assistant speak long TTS; verify no self-transcribed follow-up user messages.
- [ ] Repeat 10 cycles wake-word -> ask -> assistant speak -> idle; ensure zero loop events.
- [ ] Verify transcript preview matches spoken user audio only.
- [ ] Verify no `<|...|>` artifacts appear in UI messages.

## Related

- [`docs/README.md`](../README.md) — project documentation map

## Last updated

2026-05-31 — `docs-standards-timeline` added frontmatter
