---
status: archived
category: archive
last_updated: 2026-05-31
owner: human
---

# Athena CoreML Wake-Word Model — End-to-End Training Guide

This guide explains how to build, validate, compile, and bundle a custom CoreML sound classification model that detects the wake word "Athena" for use with the SoundAnalysis framework in the Owlynn desktop helper.

## Why a Custom Model?

The SoundAnalysis framework can use:

- Apple's built-in classifier (`SNClassifierIdentifier.version1`), which recognizes generic sounds (speech, music, dog bark, etc.) but **cannot** detect a specific wake word.
- A **custom CoreML model** trained via CreateML that recognizes only "Athena" versus everything else.

The helper scaffold currently uses a text-matching fallback. This guide walks you through swapping in a real acoustic model.

## 1. Recording Audio Samples

A high-quality training dataset is the single most important factor for model accuracy.

### Requirements

- mono (single channel), 16 kHz sample rate
- `.wav` (preferred) or `.m4a` format
- Clips should be ~0.5–2.0 seconds
- At least **50 positive examples** of "Athena" (ideally 200+)
- At least **100 negative examples** (non-wake-word speech, silence, background noise)

### Positive Class: "Athena"

Record multiple speakers if possible. Vary:

- Tone (questioning, commanding, cheerful)
- Pitch
- Speed (fast "Athena" vs drawn-out)
- Distance from microphone
- Background noise levels (quiet room, fan, street noise)

**Pro tip (macOS):** Use the built-in `say` command or `Audio Recorder` app. For automation, a simple script can batch-record:

```bash
# Record one positive sample via sox (install: brew install sox)
rec -r 16000 -b 16 -c 1 athena_001.wav trim 0 1.5
```

### Negative Class: "Other"

Collect three sub-types:

1. **Other speech**: Random conversation, other wake words, reading text aloud
2. **Silence/noise**: Room tone, typing, mouse clicks, fan noise, music
3. **Near-misses**: Words that sound like "Athena" — "a theme", "Atheena", "theena", "athena?" in different contexts

### Folder Layout

```
TrainingData/
  Athena/
    athena_001.wav
    athena_002.wav
    ...
  Other/
    speech_001.wav
    noise_001.wav
    near_miss_001.wav
    ...
```

## 2. Training in Create ML

### Step-by-step

1. Open **Create ML** (bundled with Xcode — in `/Applications/Xcode.app/Contents/Applications/Create ML.app` if not in Applications).
2. Click **New Document** -> **Sound Classification** template.
3. **Data Source**: Drag the `TrainingData/` folder into the data source area. Create ML auto-detects class labels from subfolder names.
4. **Training Parameters**:

  | Parameter       | Recommended Value                       | Notes                                                      |
  | --------------- | --------------------------------------- | ---------------------------------------------------------- |
  | Window Duration | `1.0 seconds`                           | Long enough to capture "A-the-na" (~3 syllables ~0.6–0.9s) |
  | Overlap Factor  | `0.5`                                   | 50% overlap between windows for smoother predictions       |
  | Algorithm       | `Transfer Learning (SqueezeNet)`        | Default, works well for small audio datasets               |
  | Validation      | Leave `Automatic` checked               | Create ML reserves ~20% of data for validation             |
  | Testing         | Set aside 5–10 separate files per class | Manual test set for final validation                       |

5. Click the **play** button (top-left) to start training. This takes 2–10 minutes depending on dataset size.
6. **Evaluate**: After training, inspect the **Validation Accuracy** and **Testing Accuracy** on the evaluation tab:
  - Target: 95%+ accuracy on validation
  - Check the confusion matrix — false positives (Other predicted as Athena) and false negatives should both be < 5%.
  - If accuracy is poor (< 80%), add more training samples and retrain.
7. **Export**: Click **Get** on the model output card. Save as `AthenaSoundClassifier.mlmodel`.

## 3. Compiling the Model

CoreML models must be compiled (to `.mlmodelc`) for distribution.

```bash
# Compile the model
xcrun coremlcompiler compile AthenaSoundClassifier.mlmodel .

# Verify output
ls -la AthenaSoundClassifier.mlmodelc/
# Should contain: model.mil, coreml.mil, weights/ directory, etc.
```

The compiled output is a **directory** (`AthenaSoundClassifier.mlmodelc/`), not a single file. This is important for bundling.

## 4. Bundling into the Swift Helper

The compiled model directory must be present in the project at build time so the Swift Package Manager copies it as a resource.

### Steps

```bash
# Create the Resources directory if it doesn't exist
mkdir -p src-tauri/whisperkit-helper/Sources/Resources

# Copy the compiled model bundle into place
cp -r AthenaSoundClassifier.mlmodelc src-tauri/whisperkit-helper/Sources/Resources/AthenaSoundClassifier.mlmodelc
```

The `Package.swift` is already configured to copy resources:

```swift
// In Package.swift — already done:
.executableTarget(
    name: "whisperkit-helper",
    dependencies: ["WhisperKit"],
    path: "Sources",
    resources: [
        .copy("Resources/AthenaSoundClassifier.mlmodelc")
    ]
)
```

### Verify the Bundle

```bash
# Rebuild the helper with the bundled model
cd src-tauri/whisperkit-helper
swift build -c release

# Verify the model is in the built binary's resource path
find .build -name "*.mlmodelc" -type d
# Expected: .build/release/.../AthenaSoundClassifier.mlmodelc/
```

## 5. Updating SoundAnalysisEngine.swift for Real Inference

After bundling the model, update the `SoundAnalysisEngine.swift` to actually load and run it through `SNAudioStreamAnalyzer` instead of doing text matching.

The current placeholder at `src-tauri/whisperkit-helper/Sources/SoundAnalysisEngine.swift` does substring matching as a fallback. When the real model is available, modify the code to:

```swift
final class SoundAnalysisEngine {
    private let analysisQueue = DispatchQueue(label: "com.owlynn.soundanalysis")
    private var audioEngine: AVAudioEngine?
    private var streamAnalyzer: SNAudioStreamAnalyzer?
    private var observer: ResultsObserver?
    private(set) var running = false
    private var threshold: Double = 0.3

    var onWakeWordDetected: ((String, Double) -> Void)?
    var onError: ((String) -> Void)?

    func startWakeWord(threshold: Double, ipc: IPC) throws {
        self.threshold = threshold

        // 1. Load the bundled CoreML model from the SPM resource
        guard let modelURL = Bundle.module.url(
            forResource: "AthenaSoundClassifier",
            withExtension: "mlmodelc"
        ) else {
            ipc.emit(OutgoingEvent(event: "error", message: "Model not found"))
            return
        }
        let compiledModel = try MLModel(contentsOf: modelURL)
        let request = try SNClassifySoundRequest(mlModel: compiledModel)
        request.windowDuration = CMTimeMakeWithSeconds(1.0, preferredTimescale: 48000)
        request.overlapFactor = 0.5

        // 2. Set up audio engine + stream analyzer
        audioEngine = AVAudioEngine()
        guard let inputNode = audioEngine?.inputNode else {
            ipc.emit(OutgoingEvent(event: "error", message: "No input node"))
            return
        }
        let inputFormat = inputNode.outputFormat(forBus: 0)
        streamAnalyzer = SNAudioStreamAnalyzer(format: inputFormat)

        // 3. Create observer
        let observer = ResultsObserver()
        observer.onResult = { [weak self] result in
            guard let self = self, self.running else { return }
            // Find the top classification
            if let top = result.classifications.first,
               top.identifier == "Athena" && top.confidence >= self.threshold {
                ipc.emit(OutgoingEvent(
                    event: "wakeword_detected",
                    label: "Athena",
                    confidence: Double(top.confidence)
                ))
            }
        }
        self.observer = observer

        // 4. Add request + observer to analyzer
        try streamAnalyzer?.add(request, withObserver: observer)

        // 5. Install tap
        inputNode.installTap(
            onBus: 0,
            bufferSize: UInt32(8192),
            format: inputFormat
        ) { [weak self] buffer, time in
            self?.analysisQueue.async {
                self?.streamAnalyzer?.analyze(buffer, atAudioFramePosition: time.sampleTime)
            }
        }

        // 6. Start engine
        try audioEngine?.start()
        self.running = true
        ipc.emit(OutgoingEvent(event: "ready"))
    }

    func stopWakeWord() {
        audioEngine?.stop()
        audioEngine?.inputNode.removeTap(onBus: 0)
        streamAnalyzer?.removeAllRequests()
        audioEngine = nil
        streamAnalyzer = nil
        running = false
    }
}

/// SNResultsObserving implementation
class ResultsObserver: NSObject, SNResultsObserving {
    var onResult: ((SNClassificationResult) -> Void)?
    var onError: ((String) -> Void)?

    func request(_ request: SNRequest, didProduce result: SNResult) {
        guard let classificationResult = result as? SNClassificationResult else { return }
        onResult?(classificationResult)
    }

    func request(_ request: SNRequest, didFailWithError error: Error) {
        onError?(error.localizedDescription)
    }
}
```

**Important design notes:**

- The `ResultsObserver` is a separate class (must be an `NSObject` conforming to `SNResultsObserving` — it cannot be a closure or inline block).
- `Bundle.module` is the SPM-generated resource bundle accessor (no need for hardcoded file paths).
- The tap supplies raw PCM buffers from the mic directly to `streamAnalyzer.analyze(_:atAudioFramePosition:)` — no file writing or intermediary conversion needed.
- When the classifier identifies "Athena" above the confidence threshold, it emits a `wakeword_detected` JSON event over stdout, exactly matching the protocol the Rust side already expects.

## 6. Runtime Tuning

The model's behavior is controlled by two knobs:

### Confidence Threshold


| Setting   | Behavior                                                | Use Case                                           |
| --------- | ------------------------------------------------------- | -------------------------------------------------- |
| 0.15–0.25 | Very sensitive — catches almost all real wake words     | Quiet environment, high false-positive tolerance   |
| 0.30–0.45 | Balanced — catches most wake words, few false positives | Default starting point                             |
| 0.50–0.70 | Conservative — only fires on clear utterances           | Noisy environments, low false-positive requirement |


Adjust by changing the `threshold` parameter in the `start_wakeword` command sent from the Rust side:

```json
{"command":"start_wakeword","model":"AthenaSoundClassifier","threshold":0.35}
```

### Window Duration & Overlap

These are set in the `SoundAnalysisEngine.swift` code:

- **Window Duration**: `CMTimeMakeWithSeconds(seconds, preferredTimescale: 48000)`
  - Shorter windows (0.5s): Faster response, may miss partial utterances
  - Longer windows (1.5s): More context, slower response
  - Athena is ~~3 syllables (~~0.6–0.9s), so 1.0s is appropriate
- **Overlap Factor** (0.0–1.0):
  - Higher overlap (0.75): Smoother, more predictions per second, higher CPU
  - Lower overlap (0.25): Less CPU, may miss brief wake words
  - 0.5 is a good default

### Real-time Performance on M4

On an M4 MacBook Air:

- The built-in classifier and custom CreateML models run well below the audio processing threshold (< 10% CPU per inference)
- No perceptible latency — the classifier typically responds within the first 100ms of the user saying "Athena"
- The lightweight SqueezeNet-based transfer learning model from CreateML is highly optimized for the Apple Neural Engine

## 7. Validating the Model

Before deploying to production, validate the model end-to-end:

### A. Command-line test

Create a small Swift test script that loads the model, runs it against a known test file, and prints the result:

```bash
# Quick validation using coremltools (Python)
pip install coremltools
python3 -c "
import coremltools as ct
model = ct.models.model.MLModel('AthenaSoundClassifier.mlmodel')
print(model.get_spec())
"
```

### B. Build and Run the Helper

```bash
cd src-tauri/whisperkit-helper
swift build -c release

# Test manually (the helper reads commands + simulated audio from stdin)
echo '{"command":"start_wakeword","model":"AthenaSoundClassifier","threshold":0.3}' | \
  .build/release/whisperkit-helper

# Expected output:
# {"event":"ready"}
# ... (further events as audio arrives)
```

### C. Full App Integration Test

Build the Tauri app and launch:

```bash
./start.sh
```

Expected flow:

1. Toggle "Enable Wake-word" in the Live Talk panel
2. Rust spawns the helper with `{"command":"start_wakeword",...}`
3. Helper replies `{"event":"ready"}`
4. Speak "Athena" into the microphone
5. Helper emits `{"event":"wakeword_detected","label":"Athena","confidence":0.90}`
6. Rust receives this, emits `voice.wake_word` Tauri event
7. Frontend shows "Wake-word detected: Athena"
8. Helper then runs WhisperKit transcription of the follow-on command

## 8. Troubleshooting


| Symptom                          | Likely Cause                                | Fix                                                                                                         |
| -------------------------------- | ------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Helper exits immediately         | Model not found at bundled path             | Verify `AthenaSoundClassifier.mlmodelc/` exists in `.build/release/.../Resources/`                          |
| "Model not found" error          | Resource not copied                         | Run `swift build -c release`; check `Package.swift` has `.copy("Resources/AthenaSoundClassifier.mlmodelc")` |
| Low confidence on real wake word | Training data doesn't match user's voice    | Add more speaker variety to training set                                                                    |
| High false positive rate         | Overlap too high or threshold too low       | Increase threshold to 0.40–0.50; reduce overlap to 0.25                                                     |
| No wake word detected at all     | Audio input not running                     | Verify microphone permissions: `Settings.app > Privacy > Microphone > Owlynn`                               |
| Observer never fires             | Tap not installed or analyzer not receiving | Check the `installTap` call uses the same format as `SNAudioStreamAnalyzer`                                 |
| Crashes on AVAudioEngine start   | Device has no input or wrong format         | Verify mic is connected; the helper catches errors from `audioEngine?.start()`                              |


## 9. MVP Fallback Path

If the custom CoreML model is not yet trained, the helper falls back to a **text-based matching** strategy (already implemented in `SoundAnalysisEngine.swift`):

```swift
func triggerWakeWordIfNeeded(_ text: String, ipc: IPC) {
    guard running else { return }
    if text.lowercased().contains("athena") {
        ipc.emit(OutgoingEvent(event: "wakeword_detected", label: "Athena", ...))
    }
}
```

This is fed plain text lines from stdin. For MVP validation, the Rust side can send textual representations of audio (or just type "Athena" into stdin during testing). The app integration (UI, Tauri events, transcription routing) can be fully validated without a trained model.

## Related

- [`docs/README.md`](../README.md) — project documentation map

## Last updated

2026-05-31 — `docs-standards-timeline` added frontmatter
