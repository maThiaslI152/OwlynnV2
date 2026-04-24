import Foundation

let ipc = IPC()
let soundAnalysis = SoundAnalysisEngine()
let whisper = WhisperKitEngine()

ipc.emit(OutgoingEvent(event: "ready", label: nil, confidence: nil, text: nil, is_final: nil, message: nil))

while let line = readLine() {
    guard let data = line.data(using: .utf8) else { continue }

    let command: IncomingCommand
    do {
        command = try JSONDecoder().decode(IncomingCommand.self, from: data)
    } catch {
        // Treat non-JSON lines as transcript chunks (MVP text-matching fallback)
        whisper.start(ipc: ipc)
        defer { whisper.stop() }
        if soundAnalysis.triggerWakeWordIfNeeded(line) {
            ipc.emit(OutgoingEvent(
                event: "wakeword_detected",
                label: "Athena",
                confidence: 0.9,
                text: nil, is_final: nil, message: nil
            ))
        }
        ipc.emit(OutgoingEvent(
            event: "transcript",
            label: nil, confidence: 0.8,
            text: line, is_final: false, message: nil
        ))
        ipc.emit(OutgoingEvent(
            event: "transcript",
            label: nil, confidence: 0.9,
            text: line, is_final: true, message: nil
        ))
        continue
    }

    switch command.command {
    case "start_wakeword":
        soundAnalysis.startWakeWord(threshold: command.threshold ?? 0.3)
        ipc.emit(OutgoingEvent(
            event: "wakeword_started",
            label: nil, confidence: nil, text: nil, is_final: nil, message: nil
        ))
    case "stop_wakeword":
        soundAnalysis.stopWakeWord()
    case "transcribe_start":
        whisper.start(ipc: ipc)
    case "transcribe_stop":
        whisper.stop()
    case "shutdown":
        whisper.stop()
        ipc.emit(OutgoingEvent(
            event: "shutdown", label: nil, confidence: nil,
            text: nil, is_final: nil, message: nil
        ))
        exit(0)
    default:
        ipc.emit(OutgoingEvent(
            event: "error", label: nil, confidence: nil,
            text: nil, is_final: nil,
            message: "unknown command: \(command.command)"
        ))
    }
}
