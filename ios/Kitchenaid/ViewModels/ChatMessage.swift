import Foundation

/// One entry in the conversation transcript.
///
/// A user message carries only text. An assistant message carries the full decoded
/// `ChatResponse` so the views can render the message, an optional meal card, an
/// optional grocery list, and the agent trace. An error message carries a string the
/// error banner renders.
struct ChatMessage: Identifiable {
    enum Role {
        case user
        case assistant
        case error
    }

    let id = UUID()
    let role: Role
    let date: Date

    /// Text for user/error rows, and the assistant's `message` for assistant rows.
    let text: String

    /// Only set for assistant rows.
    let response: ChatResponse?

    static func user(_ text: String) -> ChatMessage {
        ChatMessage(role: .user, date: Date(), text: text, response: nil)
    }

    static func assistant(_ response: ChatResponse) -> ChatMessage {
        ChatMessage(role: .assistant, date: Date(), text: response.message, response: response)
    }

    static func error(_ text: String) -> ChatMessage {
        ChatMessage(role: .error, date: Date(), text: text, response: nil)
    }
}
