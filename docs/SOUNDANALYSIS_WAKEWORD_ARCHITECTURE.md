# SoundAnalysis + Tauri v2 + Swift Wake-Word Architecture Plan

## Status: Plan

Date: 2026-04-24

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    Tauri v2 Desktop App                       │
│                                                               │
│  ┌─────────────────┐          ┌──────────────────────────┐   │
│  │ Frontend (React) │          │   Rust Backend (main.rs)  │   │
│  │                  │◀──Tauri──│  Tauri v2 commands        │   │
│  │ @tauri-apps/api  │  events  │  + event emission         │   │
│  │ v2               │          │  + state (Arc<RwLock>)     │   │
│  └─────────────────┘          └──────────┬───────────────┘   │
│                                          │ stdio (JSON)      │
│                                          ▼                   │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │          WhisperKit Helper (Swift subprocess)            │ │
│  │                                                          │ │
│  │  Stage 1: SNAudioStreamAnalyzer + CoreML .mlmodelc       │ │
│  │    ->  "Athena" classification > 0.3?                    │ │
│  │    ->  stdout: {"event":"wakeword_detected",...}         │ │
│  │                                                          │ │
│  │  Stage 2: WhisperKit distil-large-v3 (ANE)               │ │
│  │    ->  receives raw PCM via stdin                        │ │
│  │    ->  stdout: {"event":"transcript",...}                │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  AVAudioEngine -- Mic input (one session at a time)           │
└──────────────────────────────────────────────────────────────┘
```

## Why the Change

The current voice stack uses a single-stage SFSpeechRecognizer approach:

- Wake-word detection is textual substring matching on interim STT results (fragile)
- SFSpeechRecognizer constrained on-device mode has slow end-of-speech detection
- No acoustic sound classification for the wake word
- SFSpeechRecognizer is Apple's built-in, not optimized for M4 Neural Engine

The new architecture uses:

- **Stage 1 (Passive):** SoundAnalysis + custom CoreML model for acoustic wake-word detection ("Athena"). Low-power, always-listening. No ASR running.
- **Stage 2 (Active):** WhisperKit distil-large-v3 running on Apple Neural Engine (ANE). High-quality streaming transcription, only active after wake word is detected.
- **TTS:** Keeps existing NSSpeechSynthesizer (can be upgraded to WhisperKit's TTSKit later).
- **Push-to-talk:** Removed entirely (wake-word only).

## Target Hardware

Apple Silicon M4 (optimized for Neural Engine accelerator).

## Dependency Audit (Verified 2026-04-24)

### Rust Crates

| Crate | Version | Status | Notes |
|-------|---------|--------|-------|
| `tauri` | `2.10.3` | Latest stable (Mar 4 2026) | MSRV 1.77.2 |
| `tauri-build` | `2.10` | Latest | Build dependency |
| `tauri-plugin-shell` | `2.3.5` | Latest (Feb 3 2026) | Replaces `shell-open` v1 feature |
| `tauri-plugin-opener` | `2.5.3` | Latest (Jan 8 2026) | Replaces `shell.open` v1 allowlist |
| `window-vibrancy` | `0.7.1` | Latest (Nov 12 2025) | Active dev, last push Mar 2026 |
| `serde` (with derive) | `1.0` | Stable | No change |
| `serde_json` | `1.0` | Stable | No change |
| `crossbeam-channel` | `0.5` | Stable | No change |
| `objc` | `0.2` | **REMOVED** | Conflicts with Tauri v2's `objc2` |
| `block` | `0.1` | **REMOVED** | Replaced by `block2` in Tauri v2 |
| `cocoa` | `0.26` | **REMOVED** | Not needed (Swift handles macOS APIs) |
| `core-foundation` | `0.10` | **REMOVED** | Not needed |
| `coreaudio-rs` | `0.11` | **REMOVED** | Not needed |

### Critical Compatibility Issue: `swift-rs` Conflict

`swift-rs` 1.0.7 depends on the old `objc` v0.2 crate, but Tauri v2.10.3 migrated to `objc2`. Cargo may refuse to resolve both in the same dependency graph. This is a known issue (tauri#12964, partially fixed in tauri#10718).

**Resolution:** Use a standalone Swift helper binary communicating with Rust via stdin/stdout JSON (subprocess) instead of in-process FFI via swift-rs.

### JavaScript / TypeScript

| Package | v1 (current) | v2 (target) | Notes |
|---------|-------------|-------------|-------|
| `@tauri-apps/api` | Not in package.json (window.__TAURI__) | `^2.0.0` | New dependency |
| `@tauri-apps/cli` | `^1.6.3` | `^2.10.0` | Upgrade |
| `@tauri-apps/plugin-shell` | Not present | `^2.0.0` | New dependency |
| `@tauri-apps/plugin-opener` | Not present | `^2.0.0` | New dependency |
| React, Zustand, Vite, Vitest | Various | No change | Independent of Tauri |

### macOS Version Requirements

| Component | Minimum macOS | Notes |
|-----------|--------------|-------|
| Tauri v2.10.3 | 10.15 | Official support |
| WhisperKit v0.18 | 13.0 (Ventura) | Package.swift specifies `.macOS(.v13)` |
| ANE-quantized models | 14.0 (Sonoma) | Required for Neural Engine acceleration |
| SoundAnalysis | 13.0 + bundled CoreML | Available since macOS 13.0 |
| **Recommended minimum** | **14.0** | Covers all requirements, M4 ANE needs 14+ |

### Tauri v1 -> v2 Breaking Changes

| v1 API | v2 API | What Changed |
|--------|--------|--------------|
| `window.__TAURI__.invoke(...)` | `import { invoke } from '@tauri-apps/api/core'` | Module import |
| `window.__TAURI__.event.listen(...)` | `import { listen } from '@tauri-apps/api/event'` | Module import |
| `app.emit_all("ch", payload)` | `app.emit("ch", payload)` | Renamed |
| `app.get_window("main")` | `app.get_webview_window("main")` | Renamed |
| `tauri.conf.json > tauri > allowlist` | `src-tauri/capabilities/default.json` | New permission system |
| `build.devPath` | `build.devUrl` | Renamed |
| `@tauri-apps/api` v1.x | `@tauri-apps/api` v2.x | Breaking import changes |

## WhisperKit Model Selection

- **Model:** `distil-whisper_distil-large-v3`
- **Size:** ~800MB download, ~4GB RAM at runtime
- **Accuracy:** ~95% of large-v3
- **Performance:** Real-time on M1+, well within M4 capabilities
- **Model caching:** Auto-downloaded to `~/.cache/whisperkit/` on first launch
- **ANE compute config:** Audio encoder + text decoder on Neural Engine

## Two-Stage Pipeline Detail

### Stage 1: SoundAnalysis Wake-Word Detection

1. Create AVAudioEngine, install tap on input node at 16kHz
2. Create SNAudioStreamAnalyzer with input node format
3. Load bundled CoreML .mlmodelc for "Athena" from app Resources
4. Create SNClassifySoundRequest with the custom model
5. Window duration: 1.0s, overlap: 0.5
6. Add request to analyzer with observation handler
7. Handler checks Athena classification confidence against threshold (0.3)
8. If threshold met -> emit wakeword_detected event to Rust
9. Rust receives event, stops Stage 1, triggers Stage 2

### Stage 2: WhisperKit Transcription

1. Create new AVAudioEngine (Stage 1 fully stopped)
2. Install tap, forward PCM buffers to WhisperKit via pipe
3. WhisperKit streaming transcription (interim + final results)
4. Forward transcripts to Rust via stdout JSON events
5. Rust forwards to frontend via Tauri events
6. On stop signal or end-of-speech -> emit final transcript
7. Cleanup: stop engine, remove tap, keep helper alive for next wake word

### Stage 1 -> Stage 2 Handoff

- Stage 1 fully stops (remove tap, stop engine, remove request from analyzer)
- ~200ms gap while Stage 2 starts its own AVAudioEngine
- The user's utterance is not lost because:
  - SoundAnalysis detection window is ~1s (already buffered)
  - WhisperKit processes from the point the user is still speaking
  - 200ms is negligible for human speech

## Swift Helper Protocol

### Rust -> Swift (stdin, line-delimited JSON)

```
{"command":"start_wakeword","model":"AthenaSoundClassifier","threshold":0.3}
{"command":"stop_wakeword"}
{"command":"transcribe_start","audio_format":{"sample_rate":16000}}
{"command":"transcribe_audio","data":"<base64_pcm_chunk>"}
{"command":"transcribe_stop"}
{"command":"shutdown"}
```

### Swift -> Rust (stdout, line-delimited JSON)

```
{"event":"ready"}
{"event":"wakeword_detected","label":"Athena","confidence":0.85}
{"event":"transcript","text":"hello","is_final":false,"confidence":0.72}
{"event":"transcript","text":"hello Athena","is_final":true,"confidence":0.91}
{"event":"stopped","final_text":"hello Athena what is the weather"}
{"event":"error","message":"Model not loaded"}
```

## Files Changed

### New Files

| File | Description |
|------|-------------|
| `src-tauri/whisperkit-helper/Package.swift` | SPM manifest for Swift helper |
| `src-tauri/whisperkit-helper/Sources/main.swift` | SoundAnalysis + WhisperKit engine (stdin/stdout IPC) |
| `src-tauri/whisperkit-helper/Sources/SoundAnalysisEngine.swift` | Stage 1: SoundAnalysis logic |
| `src-tauri/whisperkit-helper/Sources/WhisperKitEngine.swift` | Stage 2: WhisperKit transcription logic |
| `src-tauri/whisperkit-helper/Sources/IPC.swift` | stdin/stdout JSON protocol handler |
| `src-tauri/capabilities/default.json` | Tauri v2 permission capability file |
| `src-tauri/src/voice/types.rs` | Split payload type definitions from mod.rs |

### Modified Files

| File | Action | Description |
|------|--------|-------------|
| `src-tauri/Cargo.toml` | Rewrite | Tauri v2.10.3 deps, remove objc/block/cocoa, add plugins |
| `src-tauri/build.rs` | Minor update | tauri_build v2, Swift helper build step |
| `src-tauri/tauri.conf.json` | Rewrite | v2 config format |
| `src-tauri/src/main.rs` | Rewrite | v2 API, remove PTT, hardcode Athena, helper lifecycle |
| `src-tauri/src/voice/mod.rs` | Major rewrite | Two-stage via Swift helper subprocess |
| `src-tauri/Info.plist` | Minor update | Mic/speech descriptions |
| `src-tauri/Entitlements.plist` | Minor update | File read for bundled models |
| `frontend-v2/package.json` | Update | @tauri-apps/api/cli v2 + shell + opener |
| `frontend-v2/src/lib/tauriBridge.ts` | Rewrite | v2 imports, remove PTT, hardcode Athena |
| `frontend-v2/src/App.tsx` | Update | v2 event import, keep backward compat |
| `frontend-v2/src/components/LiveTalkControls.tsx` | Simplify | Remove PTT, static "Athena" display |
| `frontend-v2/src/state/useAppStore.ts` | Minor | Default wakeWordPhrase = "Athena" |
| `src/config/settings.py` | Minor | VOICE_WAKE_WORD default = "Athena" |
| `.gitignore` | Update | Swift build artifacts, .mlmodelc |
| `start.sh` | Update | v2 CLI, Swift helper build step, model pre-cache |
| `docs/STATUS.md` | Update | New architecture status |
| `docs/ADR.md` | New entry | ADR for Tauri v2 + Swift + SoundAnalysis |
| `docs/AI_AGENT_INDEX.md` | Update | File mapping for new modules |

## CoreML Model Training Guide

The wake word "Athena" is determined by a custom CoreML sound classification model.

### Training Steps (using CreateML)

1. **Collect audio samples:**
   - ~50-200 recordings of "Athena" spoken by different voices, each ~1 second
   - ~50+ recordings of non-wake-word speech (casual conversation)
   - ~50+ recordings of ambient noise (silence, typing, background chatter)
   - All saved as `.wav` or `.m4a` at 16kHz mono

2. **Organize folders:**
   ```
   TrainingData/
     Athena/
       athena_voice1.wav
       athena_voice2.wav
       ...
     Other/
       background_noise1.wav
       conversation1.wav
       ...
   ```

3. **Train in CreateML:**
   - Open CreateML -> "New Document" -> "Sound Classification"
   - Set training data to the TrainingData/ folder
   - Algorithm: Window Duration 1.0s, Overlap 0.5
   - Train -> Evaluate -> Export as `AthenaSoundClassifier.mlmodel`

4. **Compile for distribution:**
   ```bash
   xcrun coremlcompiler compile AthenaSoundClassifier.mlmodel .
   ```
   Produces `AthenaSoundClassifier.mlmodelc/`

5. **Bundle in the app:**
   - Place `AthenaSoundClassifier.mlmodelc/` in `src-tauri/whisperkit-helper/Sources/Resources/`
   - The Swift package bundles it via `.copy("Resources/AthenaSoundClassifier.mlmodelc")`
   - The helper accesses it via `Bundle.module.url(forResource:...)`

### MVP Alternative

For initial validation (before the custom model is ready), use Apple's built-in sound classifier:
```swift
let request = try SNClassifySoundRequest(classifierIdentifier: .version1)
```
This won't detect "Athena" specifically, but validates the full pipeline. Swap in the custom model when ready.

## Actor Model (Thread Safety)

- Rust side: single main thread per voice session, communicates via crossbeam channels
- Swift helper: single-threaded async, communicates via stdio
- AVAudioEngine runs on its own audio thread (internal to the helper process)
- No shared mutable state between Rust and Swift processes

## Implementation Order

1. Migrate to Tauri v2.10.3 (Cargo.toml, tauri.conf.json, capabilities, build.rs)
2. Update frontend dependencies (package.json, imports)
3. Create Swift helper binary (Package.swift, Engine code)
4. Rewrite Rust voice/mod.rs with helper IPC
5. Rewrite main.rs for v2 API + remove PTT
6. Update frontend (LiveTalkControls: remove PTT, hardcode Athena)
7. Update permissions/plists
8. Guide user through CoreML model training
9. Update docs

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| AVAudioEngine cannot share mic between Stage 1 and Stage 2 | Stage 1 fully stops before Stage 2 starts. ~200ms gap is acceptable. |
| WhisperKit ~800MB model download on first launch | Auto-cached to ~/.cache/whisperkit/. Add pre-cache step in start.sh. |
| Swift helper subprocess adds ~50ms spawn overhead | Helper stays alive for entire session. Init happens once. |
| SoundAnalysis custom model accuracy with few samples | Use built-in classifier for MVP, refine custom model. |
| Tauri v2 permission system complexity | Create capabilities/default.json with minimal permissions. |
| CoreML model for "Athena" not yet trained | Start with built-in classifier, guide user through CreateML. |
