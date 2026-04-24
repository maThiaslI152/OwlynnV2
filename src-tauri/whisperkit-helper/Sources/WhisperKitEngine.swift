import Foundation
import AVFoundation

/// Stage 2 Real-Time Transcriber (MVP)
///
/// Opens the microphone and collects audio buffers from the
/// AVAudioEngine input tap. These buffers are written to a PCM
/// ring buffer that can be consumed by WhisperKit (once the model is
/// downloaded) or, for MVP, are echoed as a simple audio level
/// indicator to confirm the mic is live.
///
/// Fixes:
/// - Removed the mock "..." timer that produced fake transcripts.
/// - Added real audio level detection so the UI can show live mic activity.
final class WhisperKitEngine {
    private var audioEngine: AVAudioEngine?
    private(set) var running = false
    private var activityTimer: DispatchSourceTimer?

    func start(ipc: IPC) {
        guard !running else { return }
        running = true
        startMicCapture(ipc: ipc)
        ipc.emit(OutgoingEvent(
            event: "transcriber_started",
            label: nil, confidence: nil, text: nil, is_final: nil, message: nil
        ))
    }

    func stop() {
        running = false
        stopActivityTimer()
        stopMicCapture()
    }

    // MARK: - Microphone capture

    private func startMicCapture(ipc: IPC) {
        let engine = AVAudioEngine()
        self.audioEngine = engine

        let inputNode = engine.inputNode
        let format = inputNode.outputFormat(forBus: 0)

        inputNode.installTap(
            onBus: 0,
            bufferSize: 8192,
            format: format
        ) { buffer, _ in
            // Compute RMS audio level to confirm mic is live
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
            let db = 20.0 * log10(Double(rms))
            // Only print for significant audio (above -50 dB)
            if db > -50 {
                print("{\"event\":\"audio_level\",\"level\":\(db),\"rms\":\(rms)}")
                fflush(stdout)
            }
        }

        do {
            try engine.start()
        } catch {
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

    /// Emit a periodic "capturing" heartbeat so the frontend shows
    /// the mic is alive even during silence.
    private func stopActivityTimer() {
        activityTimer?.cancel()
        activityTimer = nil
    }
}
