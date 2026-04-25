import Foundation
import AVFoundation
import WhisperKit

/// Stage 2 Real-Time Transcriber
///
/// Loads WhisperKit's `openai_whisper-large-v3-v20240930_turbo` model once (on first `start()` or
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
/// The model auto-downloads (~632 MB) on first launch to
/// `~/Documents/huggingface/`.
final class WhisperKitEngine {
    /// Persisted WhisperKit instance — created once, reused across on/off cycles.
    private static var sharedKit: WhisperKit?
    private static var kitLoadError: String?
    private static let loadLock = NSLock()
    private static var loadAttempted = false

    private var audioEngine: AVAudioEngine?
    private var isTranscribing = false
    private var isMuted = false
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
            Self.log("[WhisperKit] Preloading model openai_whisper-large-v3-v20240930_turbo from cache...")
            Task {
                do {
                    let newKit = try await WhisperKit(
                        model: "openai_whisper-large-v3-v20240930_turbo",
                        verbose: false,
                        prewarm: true,
                        load: true,
                        download: true
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
            Self.log("[WhisperKit] Loading model openai_whisper-large-v3-v20240930_turbo from cache...")
            Self.loadAttempted = true
            Task {
                do {
                    let newKit = try await WhisperKit(
                        model: "openai_whisper-large-v3-v20240930_turbo",
                        verbose: false,
                        prewarm: true,
                        load: true,
                        download: true
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

    /// Cooldown timestamp (wall clock) after which audio processing resumes post-unmute.
    /// While Date() < postUnmuteCooldownUntil, all audio chunks are dropped.
    private var postUnmuteCooldownUntil: Date = .distantPast

    func setMuted(_ muted: Bool) {
        let now = Date()
        isMuted = muted
        sampleAccumulatorLock.lock()
        sampleAccumulator.removeAll()
        sampleAccumulatorLock.unlock()
        if muted {
            // Reset transcription state so residual pre-mute results don't leak.
            lastEmittedText = ""
            lastEmittedIsFinal = false
        } else {
            // Enforce a 3-second cooldown after unmute so any lingering
            // TTS echo in the room has time to decay before audio processing
            // is re-enabled.
            postUnmuteCooldownUntil = now.addingTimeInterval(3.0)
        }
    }

    deinit {
        stop()
    }

    // MARK: - Microphone capture

    private func startMicCapture(ipc: IPC) {
        let engine = AVAudioEngine()
        do {
            try engine.inputNode.setVoiceProcessingEnabled(true)
        } catch {
            Self.log("[Mic] Failed to enable voice processing: \(error)")
        }
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

            if self.isMuted || Date() < self.postUnmuteCooldownUntil {
                return
            }

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

            // Filter out WhisperKit hallucinated filler/continuation phrases
            // that the model emits from silence, noise, or trailing audio.
            guard !isHallucinatedFiller(cleanedText) else {
                Self.log("[Transcribe] Suppressed hallucinated filler: \"\(cleanedText)\"")
                return
            }

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

    // MARK: - Hallucination filter

    /// Common WhisperKit hallucinated filler phrases emitted from silence or
    /// very low-energy audio. These are almost never what the user actually said.
    private static let fillerPhrases: Set<String> = {
        let raw: [String] = [
            "Thank you.",
            "Thank you",
            "Thank",
            "Thanks.",
            "Thanks",
            "Thanks for watching.",
            "Thank you for watching.",
            "Thank you for your question.",
            "Thank you for the question.",
            "Thank you for asking.",
            "Thank you for listening.",
            "You",
            "Yeah.",
            "Yeah",
            "Mm-hmm.",
            "Uh-huh.",
            "Mhm.",
            "Mhm",
            "Hmm.",
            "Hmm",
            "Um.",
            "Um",
            "Ah.",
            "Ah",
            "Oh.",
            "Oh",
            "Okay.",
            "Okay",
            "OK.",
            "OK",
            "So",
            "So.",
            "And",
            "And.",
            "But",
            "But.",
            "The",
            "The.",
            "A",
            "A.",
            "I",
            "I.",
            "You know.",
            "You know",
            "I mean.",
            "I mean",
            "Right.",
            "Right",
            "Sure.",
            "Sure",
            "Great.",
            "Great",
            "No problem.",
            "No problem",
            "You're welcome.",
            "You are welcome.",
            "Welcome.",
            "You're welcome",
            "You are welcome",
            "I think.",
            "I think",
            "I see.",
            "I see",
        ]
        return Set(raw)
    }()

    private func isHallucinatedFiller(_ text: String) -> Bool {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
        if Self.fillerPhrases.contains(trimmed) {
            return true
        }
        // Single-word utterances that aren't actual questions/statements
        let wordCount = trimmed.split(separator: " ").count
        if wordCount <= 3 {
            let lower = trimmed.lowercased()
            // Allow short question words and common short replies
            let allowedShort = Set([
                "hi", "hello", "hey", "bye", "yes", "no", "ok", "okay",
                "why", "how", "what", "when", "where", "who", "which",
                "go", "stop", "run", "help", "test", "rust", "go",
                "python", "js", "ts", "java", "c", "c++",
            ])
            if wordCount == 1 && allowedShort.contains(lower) {
                return false
            }
            // Allow 2-3 word phrases that look like real questions
            let questionWords = Set(["what", "why", "how", "when", "where", "who", "which", "is", "are", "can", "does", "do", "did", "will", "would", "could", "should"])
            let words = lower.split(separator: " ").map(String.init)
            if words.contains(where: { questionWords.contains($0) }) {
                return false
            }
            // Also allow phrases with numbers
            if words.contains(where: { $0.rangeOfCharacter(from: .decimalDigits) != nil }) {
                return false
            }
            return true
        }
        return false
    }
}
