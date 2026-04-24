import Foundation

struct IncomingCommand: Decodable {
    let command: String
    let model: String?
    let threshold: Double?
}

struct OutgoingEvent: Encodable {
    let event: String
    let label: String?
    let confidence: Double?
    let text: String?
    let is_final: Bool?
    let message: String?
}

final class IPC {
    private let encoder = JSONEncoder()

    func emit(_ event: OutgoingEvent) {
        do {
            let data = try encoder.encode(event)
            if let line = String(data: data, encoding: .utf8) {
                print(line)
                fflush(stdout)
            }
        } catch {
            print("{\"event\":\"error\",\"message\":\"ipc encode error\"}")
            fflush(stdout)
        }
    }
}
