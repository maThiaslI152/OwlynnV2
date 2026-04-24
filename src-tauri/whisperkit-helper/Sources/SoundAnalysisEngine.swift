import Foundation
import SoundAnalysis
import AVFoundation

/// Stage 1 Wake-Word Detector
///
/// In MVP fallback mode, this just enables/disables a flag.
/// Real CoreML inference (via SNAudioStreamAnalyzer + SNClassifySoundRequest)
/// should replace this when the AthenaSoundClassifier model is bundled.
final class SoundAnalysisEngine {
    private(set) var running = false
    private var threshold: Double = 0.3

    func startWakeWord(threshold: Double) {
        self.threshold = threshold
        self.running = true
    }

    func stopWakeWord() {
        self.running = false
    }

    /// Called by main.swift whenever a new transcript chunk arrives.
    /// Returns true if the chunk contains the wake word.
    func triggerWakeWordIfNeeded(_ text: String) -> Bool {
        guard running else { return false }
        return text.lowercased().contains("athena")
    }
}
