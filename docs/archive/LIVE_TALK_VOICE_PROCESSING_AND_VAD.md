---
status: archived
category: archive
last_updated: 2026-05-31
owner: human
---

# Live Talk: Voice processing, VAD, and roadmap

**Last updated:** 2026-04-25 v2 (post filler-forced-finalization debug session)  
**Scope:** Turn-based Live Talk (wake word → transcribe → LLM → TTS), aligned with Owlynn's local-first Tauri + Swift helper architecture.

---

## 1. Current state: hallucinations and silence

Whisper-class models can emit **plausible filler** ("Thank you.", "Thanks for watching.") when fed **silence, tail noise, or very low-energy audio**. That is not unique to distilled weights; it improves with better models and cleaner input, but **turn-based pipelines** still need explicit **end-of-utterance** behavior so decoding stops before the model invents continuations.

**Production Whisper model (helper):** `openai_whisper-large-v3-v20240930_turbo` (~632 MB CoreML bundle via WhisperKit `download: true`). Earlier `distil-whisper_distil-large-v3` is no longer the default.

**Root cause (operational):** If the mic path stays "hot" into Whisper while the user is silent, windows of near-silence still get decoded → filler text. Mitigations are layered: **mute during TTS**, **post-TTS cooldown**, **Rust anti-filler forced-finalization** on `audio_level` events, **Swift phrase filter**, and **frontend echo guards**.

---

## 2. Anti-filler layer (Rust)

The previous Rust VAD constants (`VOICE_ACTIVE_DB_THRESHOLD`, `SILENCE_STOP_MS`, etc.) were **removed** because they caused premature transcription-stop and re-arm-of-wake-word mid-TTS, creating new echo loops.

They are replaced by a **non-destructive anti-filler layer** in `run_helper_pipeline` ([`src-tauri/src/voice/mod.rs`](../src-tauri/src/voice/mod.rs)):

**How it works:**

1. Rust tracks `last_meaningful_text` — the last transcript with substantive content
2. When a short (<10 chars) filler-like transcript arrives that differs from the meaningful text, Rust **force-finalizes** the meaningful text as `is_final: true` and **drops** the filler entirely
3. When a transcript matches the last meaningful text but WhisperKit hasn't confirmed it as final yet, Rust overrides `is_final = true`
4. When the pipeline exits (user stops listening), any pending meaningful text is force-finalized

This ensures the user's actual query always reaches the frontend (and LLM) before any hallucinated filler.

See [`docs/LIVE_TALK_WHISPER_FILLER_AND_FORCE_FINALIZE.md`](LIVE_TALK_WHISPER_FILLER_AND_FORCE_FINALIZE.md) for the full debug analysis.

---

## 3. Swift helper mitigations

Implemented in [`src-tauri/whisperkit-helper/Sources/`](../src-tauri/whisperkit-helper/Sources/):

| Mechanism | Files | Purpose |
|-----------|--------|---------|
| `mute` / `unmute` IPC | `main.swift`, engines | Drop taps / analysis while TTS runs (`say` in Rust). |
| Post-unmute cooldown | `WhisperKitEngine.swift`, `SoundAnalysisEngine.swift` | Block processing briefly after unmute to shed room echo. |
| `isHallucinatedFiller()` | `WhisperKitEngine.swift` | Drop known junk phrases from STT output before stdout. Expanded set (50+ variants), 1–3 word filtering with question-word / digit passthrough. |
| Whisper decoding options | `WhisperKitEngine.swift` | e.g. `skipSpecialTokens`, token stripping helpers. |

---

## 4. Frontend mitigations

In [`frontend-v2/src/App.tsx`](../../frontend-v2/src/App.tsx) (and related store):

- Tauri-native path is canonical for `voice.*` in Tauri builds (avoid duplicate WS handling).
- TTS state + 3s cooldown (increased from 1.2s) + 15s echo window with `isTtsEcho()` (bidirectional containment + >50% word overlap) reduce **assistant text** being re-ingested as **user** voice.
- Clear `interimTranscript` on `voice.state` transitions (`recording` / `idle`) so the UI does not show stale lines.

---

## 5. Apple built-in voice processing — TRIED, REVERTED

### What was done

`setVoiceProcessingEnabled(true)` was applied to both `AVAudioEngine` instances (WhisperKitEngine.swift + SoundAnalysisEngine.swift) in this session.

### Result

The user reported **worse** behavior — the wake word activated but **no voice was captured afterward**. The platform AEC path was too aggressive, suppressing microphone input even when no TTS was playing.

### Current recommendation

**Revert** `setVoiceProcessingEnabled(true)` from both engines. The combination of:
- Helper mute/unmute during TTS (Phase 1)
- Post-unmute cooldowns (3s)
- Rust anti-filler forced-finalization
- Swift hallucination filter (expanded)
- Frontend echo guards (3s cooldown + content matching)

provides sufficient echo suppression without hardware AEC side effects.

If voice processing is revisited in the future:
- Make it **opt-in** via a config flag or env var (`VOICE_PROCESSING=true`)
- Test with a headset (where AEC is typically less aggressive) vs. built-in speakers/mic
- Consider per-engine enable/disable (enable on WhisperKit but not SoundAnalysis, or vice versa)

---

## 6. Future options

### End-of-utterance detection

The pipeline currently stays in transcribe mode indefinitely after wake-word → transcript. No auto-stop/re-arm-wake-word logic is active (removed due to echo loops in earlier session). User must manually stop.

Options for turn-boundary detection without echo:
- **Silero VAD** (ONNX): Per-frame speech probability in Rust — cleaner than RMS/dB gating and less prone to false triggers.
- **Confidence-based stop**: If WhisperKit outputs very low confidence (e.g. `confidence < 0.1`) for N consecutive windows, auto-stop.
- **Configurable auto-stop**: A simple timeout from last meaningful transcript (e.g. 5 seconds of silence after a finalized transcript).

### Hardware / room considerations
- Built-in speakers + mic on a laptop is the worst-case scenario for echo. Headphones or an external mic improve results dramatically.
- The current software-only approach works well with headsets; on-board speakers require more aggressive gating.

---

## 7. Alignment with Owlynn goals

- **Local-first:** All processing is on-device; no cloud STT required.
- **M4 / Apple Silicon:** Fits existing Neural Engine + CoreML story documented in [`docs/SOUNDANALYSIS_WAKEWORD_ARCHITECTURE.md`](SOUNDANALYSIS_WAKEWORD_ARCHITECTURE.md).
- **Turn-based product:** This doc scopes **wake → bounded capture → stop → wake** rather than bidirectional streaming (lighter than frontier "live" stacks).

---

## Related docs

- [`docs/STATUS.md`](STATUS.md) — project status and risks.
- [`docs/LIVE_TALK_WHISPER_FILLER_AND_FORCE_FINALIZE.md`](LIVE_TALK_WHISPER_FILLER_AND_FORCE_FINALIZE.md) — debug analysis, root cause, all changes in this session.
- [`docs/SOUNDANALYSIS_WAKEWORD_ARCHITECTURE.md`](SOUNDANALYSIS_WAKEWORD_ARCHITECTURE.md) — two-stage pipeline diagram.
- [`docs/LIVE_TALK_PHASE1_TTS_LOOP_FIX_2026-04-25.md`](LIVE_TALK_PHASE1_TTS_LOOP_FIX_2026-04-25.md) — Phase 1 TTS mute / IPC notes.

## Last updated

2026-05-31 — `docs-standards-timeline` added frontmatter
