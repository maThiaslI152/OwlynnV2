import Foundation
import SoundAnalysis
import AVFoundation

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

    func triggerWakeWordIfNeeded(_ text: String, ipc: IPC) {
        guard running else { return }
        if text.lowercased().contains("athena") {
            ipc.emit(OutgoingEvent(event: "wakeword_detected", label: "Athena", confidence: max(threshold, 0.9), text: nil, is_final: nil, message: nil))
        }
    }
}
