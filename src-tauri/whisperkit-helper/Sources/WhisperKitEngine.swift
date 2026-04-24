import Foundation
import WhisperKit

final class WhisperKitEngine {
    private(set) var running = false
    private var buffer: [String] = []

    func start() {
        running = true
        buffer.removeAll()
    }

    func stop() -> String {
        running = false
        return buffer.joined(separator: " ").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    func pushTranscriptChunk(_ chunk: String, ipc: IPC) {
        guard running else { return }
        let clean = chunk.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { return }
        buffer.append(clean)
        ipc.emit(OutgoingEvent(event: "transcript", label: nil, confidence: 0.8, text: clean, is_final: false, message: nil))
    }

    func emitFinal(ipc: IPC) {
        let finalText = stop()
        ipc.emit(OutgoingEvent(event: "transcript", label: nil, confidence: 0.9, text: finalText, is_final: true, message: nil))
    }
}
