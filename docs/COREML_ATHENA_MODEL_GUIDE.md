# Athena CoreML Wake-Word Model Guide

This guide explains how to build the custom SoundAnalysis/CoreML wake-word model for `Athena`.

## 1) Collect Training Audio

- Positive class: record 50-200 clips of people saying `Athena`.
- Negative class: record 100+ clips of non-wake speech and ambient noise.
- Target format: mono, 16 kHz, short clips (~1s).

Suggested folder layout:

```text
TrainingData/
  Athena/
    athena_001.wav
    athena_002.wav
  Other/
    speech_001.wav
    noise_001.wav
```

## 2) Train in Create ML

1. Open Create ML.
2. Create new `Sound Classification` project.
3. Point training input to `TrainingData`.
4. Start with:
   - window duration: `1.0s`
   - overlap factor: `0.5`
5. Train and export `AthenaSoundClassifier.mlmodel`.

## 3) Compile the Model

```bash
xcrun coremlcompiler compile AthenaSoundClassifier.mlmodel .
```

This produces `AthenaSoundClassifier.mlmodelc`.

## 4) Bundle Into Helper

- Place the compiled model in:
  - `src-tauri/whisperkit-helper/Sources/Resources/AthenaSoundClassifier.mlmodelc`
- Ensure `Package.swift` copies that resource.

## 5) Runtime Tuning

- Start threshold at `0.30`.
- If false positives are high, increase to `0.40-0.55`.
- If misses are high, decrease to `0.20-0.25`.

## 6) MVP Fallback

If the custom model is not ready, keep helper protocol and UI flow in place, and run a temporary
placeholder detection strategy so app integration can still be validated end-to-end.
