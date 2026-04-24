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
        // Treat plain lines as simulated transcript chunks
        whisper.pushTranscriptChunk(line, ipc: ipc)
        soundAnalysis.triggerWakeWordIfNeeded(line, ipc: ipc)
        continue
    }

    switch command.command {
    case "start_wakeword":
        soundAnalysis.startWakeWord(threshold: command.threshold ?? 0.3)
    case "stop_wakeword":
        soundAnalysis.stopWakeWord()
    case "transcribe_start":
        whisper.start()
    case "transcribe_stop":
        whisper.emitFinal(ipc: ipc)
    case "shutdown":
        ipc.emit(OutgoingEvent(event: "shutdown", label: nil, confidence: nil, text: nil, is_final: nil, message: nil))
        exit(0)
    default:
        ipc.emit(OutgoingEvent(event: "error", label: nil, confidence: nil, text: nil, is_final: nil, message: "unknown command"))
    }
}
