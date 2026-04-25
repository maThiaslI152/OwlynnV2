import Foundation
import SoundAnalysis
import AVFoundation

/// Stage 1 Wake-Word Detector
///
/// Uses `SNAudioStreamAnalyzer` + a custom CoreML `AthenaSoundClassifier` model
/// to detect the wake word "Athena" from the live microphone stream via acoustic
/// sound classification.
///
/// When the bundled .mlmodelc is not found, it falls back to the previous
/// text-matching approach (checking transcript text for "athena").
final class SoundAnalysisEngine {
    private let analysisQueue = DispatchQueue(label: "com.owlynn.soundanalysis")
    private var audioEngine: AVAudioEngine?
    private var streamAnalyzer: SNAudioStreamAnalyzer?
    private var observer: ResultsObserver?
    private(set) var running = false
    private var isMuted = false
    private var threshold: Double = 0.3
    private var usingCoreML = false

    /// Start wake-word detection using the bundled CoreML model.
    /// Falls back to text-matching if the model is not available.
    func startWakeWord(threshold: Double, ipc: IPC) {
        self.threshold = threshold
        self.running = true

        // Attempt to load the bundled CoreML model
        if let modelURL = Bundle.module.url(
            forResource: "AthenaSoundClassifier",
            withExtension: "mlmodelc"
        ) {
            do {
                let compiledModel = try MLModel(contentsOf: modelURL)
                let request = try SNClassifySoundRequest(mlModel: compiledModel)
                request.windowDuration = CMTimeMakeWithSeconds(1.0, preferredTimescale: 48000)
                request.overlapFactor = 0.5

                // Set up audio engine + stream analyzer
                let engine = AVAudioEngine()
                self.audioEngine = engine
                let inputNode = engine.inputNode
                let inputFormat = inputNode.outputFormat(forBus: 0)
                let analyzer = SNAudioStreamAnalyzer(format: inputFormat)
                self.streamAnalyzer = analyzer

                // Create observer
                let obs = ResultsObserver()
                obs.onResult = { [weak self] result in
                    guard let self = self, self.running else { return }
                    if let top = result.classifications.first,
                       top.identifier == "Athena" && Double(top.confidence) >= self.threshold {
                        ipc.emit(OutgoingEvent(
                            event: "wakeword_detected",
                            label: "Athena",
                            confidence: Double(top.confidence),
                            text: nil, is_final: nil, message: nil
                        ))
                    }
                }
                obs.onError = { message in
                    ipc.emit(OutgoingEvent(
                        event: "error", label: nil, confidence: nil,
                        text: nil, is_final: nil, message: message
                    ))
                }
                self.observer = obs

                // Add request + observer to analyzer
                try analyzer.add(request, withObserver: obs)

                // Install tap on input node
                inputNode.installTap(
                    onBus: 0,
                    bufferSize: UInt32(8192),
                    format: inputFormat
                ) { [weak self] buffer, time in
                    self?.analysisQueue.async {
                        guard let self = self, !self.isMuted else { return }
                        self.streamAnalyzer?.analyze(buffer, atAudioFramePosition: time.sampleTime)
                    }
                }

                // Start engine
                try engine.start()
                self.usingCoreML = true
                ipc.emit(OutgoingEvent(
                    event: "wakeword_started", label: nil, confidence: nil,
                    text: nil, is_final: nil, message: nil
                ))
                return
            } catch {
                // Model exists but failed to load — fall through to text matching
                ipc.emit(OutgoingEvent(
                    event: "wakeword_started", label: nil, confidence: nil,
                    text: nil, is_final: nil,
                    message: "CoreML model failed to load: \(error.localizedDescription). Falling back to text matching."
                ))
            }
        } else {
            ipc.emit(OutgoingEvent(
                event: "wakeword_started", label: nil, confidence: nil,
                text: nil, is_final: nil,
                message: "CoreML model not found. Using text-matching fallback."
            ))
        }

        // Fallback: text-matching mode (no CoreML model)
        self.usingCoreML = false
    }

    func stopWakeWord() {
        if usingCoreML {
            audioEngine?.stop()
            audioEngine?.inputNode.removeTap(onBus: 0)
            streamAnalyzer?.removeAllRequests()
            audioEngine = nil
            streamAnalyzer = nil
            observer = nil
        }
        running = false
    }

    func setMuted(_ muted: Bool) {
        isMuted = muted
    }

    /// Called by main.swift whenever a new transcript chunk arrives (text-matching fallback).
    /// Returns true if the chunk contains the wake word.
    func triggerWakeWordIfNeeded(_ text: String) -> Bool {
        guard running, !usingCoreML, !isMuted else { return false }
        return text.lowercased().contains("athena")
    }
}

/// SNResultsObserving implementation for receiving classification results.
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

    func requestDidComplete(_ request: SNRequest) {
        // No-op: the analyzer continues indefinitely
    }
}
