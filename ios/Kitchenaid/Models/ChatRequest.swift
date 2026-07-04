import Foundation

/// The `/chat` request body.
///
/// Mirrors the FastAPI `ChatRequest` model. `pantry` is supported by the backend but
/// optional; we omit it here (the "use up the fridge" flow is driven purely by the
/// natural-language `query`, which the backend parses).
struct ChatRequest: Codable {
    let userID: String
    let query: String
    let profile: Profile

    enum CodingKeys: String, CodingKey {
        case userID = "user_id"
        case query
        case profile
    }
}
