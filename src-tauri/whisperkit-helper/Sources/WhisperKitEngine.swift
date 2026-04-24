import Foundation
import AVFoundation
import WhisperKit

/// Stage 2 Real-Time Transcriber
///
/// Loads WhisperKit's `distil-large-v3` model once (on first `start()` or
/// `preload()` call), captures microphone audio via AVAudioEngine, feeds
/// buffers to WhisperKit for streaming transcription, and emits `transcript`
/// events.
///
/// Key behaviors:
/// - WhisperKit model is loaded **once** and kept alive across on/off toggles
///   via the static `sharedKit` singleton.
/// - On re-enable, no HuggingFace connection attempt — the model is already in
///   memory.
/// - Accumulates ~3s audio windows, transcribes, emits interim then confirmed
///   results.
/// - Stderr logging for debugging.
///
/// The model auto-downloads (~800 MB) on first launch to
/// `~/Documents/huggingface/`.
final class WhisperKitEngine {
    /// Persisted WhisperKit instance — created once, reused across on/off cycles.
    private static var sharedKit: WhisperKit?
    private static var kitLoadError: String?
    private static let loadLock = NSLock()
    private static var loadAttempted = false

    private var audioEngine: AVAudioEngine?
    private var isTranscribing = false
    private let decoderQueue = DispatchQueue(label: "com.owlynn.whisperkit.decoder")
    private var lastEmittedText: String = ""
    private var lastEmittedIsFinal: Bool = false

    /// Number of samples per transcription window at 16kHz (~3 seconds).
    private let windowSamples = 48_000
    /// Sliding step (~1 second).
    private let stepSamples = 16_000
    private let targetSampleRate: Double = 16_000
    private var inputSampleRate: Double = 16_000

    // MARK: - Preload (silent, no mic)

    /// Preloads WhisperKit model without starting microphone capture.
    /// Call this early (e.g. on app start or wake-word enable) so the model
    /// is ready when `start()` is called after wake-word detection.
    func preload(ipc: IPC) {
        guard Self.sharedKit == nil, !Self.loadAttempted else {
            Self.log("[WhisperKit] Already loaded or loading, skipping preload")
            return
        }
        Self.loadAttempted = true

        decoderQueue.async {
            Self.log("[WhisperKit] Preloading model distil-whisper_distil-large-v3 from cache...")
            Task {
                do {
                    let modelPath = "/Users/tim/Documents/huggingface/models/argmaxinc/whisperkit-coreml/distil-whisper_distil-large-v3"
                    let newKit = try await WhisperKit(
                        model: "distil-whisper_distil-large-v3",
                        modelFolder: modelPath,
                        verbose: false,
                        prewarm: true,
                        load: true,
                        download: false
                    )
                    Self.sharedKit = newKit
                    Self.log("[WhisperKit] Preloaded successfully")
                } catch {
                    Self.kitLoadError = error.localizedDescription
                    Self.log("[WhisperKit] Preload failed: \(error)")
                    print("{\"event\":\"error\",\"message\":\"WhisperKit preload: \(error.localizedDescription)\"}")
                    fflush(stdout)
                }
            }
        }
    }

    // MARK: - Public API

    func start(ipc: IPC) {
        guard !isTranscribing else { return }
        isTranscribing = true

        decoderQueue.async { [weak self] in
            guard let self = self else { return }

            // Check if a previous load attempt failed
            if let error = Self.kitLoadError {
                Self.log("[WhisperKit] Previous load failed: \(error)")
                ipc.emit(OutgoingEvent(
                    event: "error", message: "WhisperKit previously failed to load: \(error)"
                ))
                self.isTranscribing = false
                return
            }

            // If WhisperKit is already loaded (via preload or prior start()),
            // just start mic capture and emit transcriber_started immediately.
            if let _ = Self.sharedKit {
                Self.log("[WhisperKit] Using existing model instance")
                ipc.emit(OutgoingEvent(event: "transcriber_started"))
                self.startMicCapture(ipc: ipc)
                return
            }

            // First load — do it on this queue
            Self.log("[WhisperKit] Loading model distil-whisper_distil-large-v3 from cache...")
            Self.loadAttempted = true
            Task {
                do {
                    let modelPath = "/Users/tim/Documents/huggingface/models/argmaxinc/whisperkit-coreml/distil-whisper_distil-large-v3"
                    let newKit = try await WhisperKit(
                        model: "distil-whisper_distil-large-v3",
                        modelFolder: modelPath,
                        verbose: false,
                        prewarm: true,
                        load: true,
                        download: false
                    )
                    Self.sharedKit = newKit
                    Self.log("[WhisperKit] Model loaded successfully")

                    ipc.emit(OutgoingEvent(event: "transcriber_started"))
                    self.startMicCapture(ipc: ipc)
                } catch {
                    Self.kitLoadError = error.localizedDescription
                    Self.log("[WhisperKit] Load failed: \(error)")
                    ipc.emit(OutgoingEvent(
                        event: "error",
                        message: "WhisperKit load failed: \(error.localizedDescription)"
                    ))
                    self.isTranscribing = false
                }
            }
        }
    }

    func stop() {
        isTranscribing = false
        stopMicCapture()
        lastEmittedText = ""
        lastEmittedIsFinal = false
    }

    deinit {
        stop()
    }

    // MARK: - Microphone capture

    private func startMicCapture(ipc: IPC) {
        let engine = AVAudioEngine()
        self.audioEngine = engine

        let inputNode = engine.inputNode
        let format = inputNode.outputFormat(forBus: 0)
        inputSampleRate = format.sampleRate

        Self.log("[Mic] Starting capture, format: \(format.sampleRate)Hz, \(format.channelCount)ch")

        inputNode.installTap(
            onBus: 0,
            bufferSize: 8192,
            format: format
        ) { [weak self] buffer, _ in
            guard let self = self, self.isTranscribing else { return }

            // Emit audio level for UI waveform
            let channelData = buffer.floatChannelData
            let frames = Int(buffer.frameLength)
            var sum: Float = 0
            if let data = channelData?[0] {
                for i in 0..<frames {
                    let sample = data[i]
                    sum += sample * sample
                }
            }
            let rms = sqrt(sum / Float(frames))
            let db = 20.0 * log10(Double(rms) + 1e-10)
            print("{\"event\":\"audio_level\",\"level\":\(db),\"rms\":\(rms)}")
            fflush(stdout)

            // Feed audio samples into accumulator
            self.feedBuffer(buffer, ipc: ipc)
        }

        do {
            try engine.start()
            Self.log("[Mic] AVAudioEngine started successfully")
        } catch {
            Self.log("[Mic] AVAudioEngine start failed: \(error)")
            print("{\"event\":\"error\",\"message\":\"AVAudioEngine start failed: \(error.localizedDescription)\"}")
            fflush(stdout)
        }
    }

    private func stopMicCapture() {
        audioEngine?.stop()
        if let engine = audioEngine {
            engine.inputNode.removeTap(onBus: 0)
        }
        audioEngine = nil
    }

    // MARK: - Buffer accumulation & transcription

    private var sampleAccumulator: [Float] = []
    private let sampleAccumulatorLock = NSLock()

    private func feedBuffer(_ buffer: AVAudioPCMBuffer, ipc: IPC) {
        guard let channelData = buffer.floatChannelData?[0] else { return }
        let frames = Int(buffer.frameLength)
        let samples = Array(UnsafeBufferPointer(start: channelData, count: frames))
        let normalized = normalizeTo16k(samples: samples, sourceSampleRate: inputSampleRate)

        sampleAccumulatorLock.lock()
        sampleAccumulator.append(contentsOf: normalized)
        let accumulated = sampleAccumulator.count
        sampleAccumulatorLock.unlock()

        guard accumulated >= windowSamples else { return }

        sampleAccumulatorLock.lock()
        let chunk = Array(sampleAccumulator.prefix(windowSamples))
        let keepStart = stepSamples
        if keepStart < sampleAccumulator.count {
            sampleAccumulator = Array(sampleAccumulator.suffix(from: keepStart))
        } else {
            sampleAccumulator.removeAll()
        }
        sampleAccumulatorLock.unlock()

        guard !chunk.isEmpty else { return }

        decoderQueue.async { [weak self] in
            guard let self = self else { return }
            Task {
                await self.transcribeChunk(chunk, ipc: ipc)
            }
        }
    }

    private func transcribeChunk(_ samples: [Float], ipc: IPC) async {
        guard let kit = Self.sharedKit, isTranscribing else { return }

        do {
            let results = try await kit.transcribe(
                audioArray: samples,
                decodeOptions: DecodingOptions(
                    task: .transcribe,
                    temperature: 0.0,
                    temperatureFallbackCount: 2,
                    skipSpecialTokens: true
                )
            )

            guard let result = results.last else { return }
            let segments = result.segments
            guard !segments.isEmpty else { return }

            let fullText = segments
                .map { $0.text.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }
                .joined(separator: " ")
            let cleanedText = stripSpecialTokens(fullText)

            guard !cleanedText.isEmpty else { return }

            if cleanedText == lastEmittedText {
                if !lastEmittedIsFinal {
                    let confidence = computeConfidence(from: result)
                    ipc.emit(OutgoingEvent(
                        event: "transcript",
                        confidence: confidence,
                        text: cleanedText,
                        is_final: true
                    ))
                    lastEmittedIsFinal = true
                    Self.log("[Transcribe] Final: \"\(cleanedText.prefix(50))...\"")
                }
                return
            }

            let confidence = computeConfidence(from: result)
            ipc.emit(OutgoingEvent(
                event: "transcript",
                confidence: confidence,
                text: cleanedText,
                is_final: false
            ))
            lastEmittedText = cleanedText
            lastEmittedIsFinal = false
            Self.log("[Transcribe] Interim: \"\(cleanedText.prefix(50))...\"")

        } catch {
            Self.log("[Transcribe] Error: \(error)")
            // Don't emit errors for every window — just log them
        }
    }

    private func computeConfidence(from result: TranscriptionResult) -> Double {
        let avgLogprob = result.segments.map { $0.avgLogprob }.reduce(0, +) / max(Float(result.segments.count), 1)
        return max(0.0, min(1.0, Double(-avgLogprob / 10.0)))
    }

    private func normalizeTo16k(samples: [Float], sourceSampleRate: Double) -> [Float] {
        guard !samples.isEmpty else { return [] }
        guard sourceSampleRate > targetSampleRate else { return samples }

        // Cheap downsample for 44.1/48k input -> 16k model input.
        let stride = max(1, Int(round(sourceSampleRate / targetSampleRate)))
        if stride <= 1 {
            return samples
        }
        var out: [Float] = []
        out.reserveCapacity(samples.count / stride + 1)
        var i = 0
        while i < samples.count {
            out.append(samples[i])
            i += stride
        }
        return out
    }

    private func stripSpecialTokens(_ text: String) -> String {
        let pattern = #"<\|[^|]+?\|>"#
        let cleaned = text.replacingOccurrences(
            of: pattern,
            with: " ",
            options: .regularExpression
        )
        return cleaned
            .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    // MARK: - Logging

    private static func log(_ message: String) {
        // Write to stderr so it doesn't interfere with the stdout JSON protocol
        fputs("[WhisperKitEngine] \(message)\n", stderr)
        fflush(stderr)
    }
}
