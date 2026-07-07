import Foundation

/// The `/chat` request body.
///
/// Mirrors the FastAPI `ChatRequest` model. `pantry` is supported by the backend but
/// optional; we omit it here (the "use up the fridge" flow is driven purely by the
/// natural-language `query`, which the backend parses). `options` carries the agent
/// toggles from the Agents screen: creative_chef / shopper / taster.
struct ChatRequest: Codable {
    let userID: String
    let query: String
    let profile: Profile
    let options: ChatOptions?

    enum CodingKeys: String, CodingKey {
        case userID = "user_id"
        case query
        case profile
        case options
    }
}
