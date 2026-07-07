import Foundation

/// UserDefaults keys for the persisted agent toggles. The same keys back the
/// `@AppStorage` bindings in `AgentsView` / `ChatView` and the read in
/// `ChatOptions.current()`, so the switch the user flips is exactly what ships
/// with the next `/chat` request.
enum AgentOptionKeys {
    static let creativeChef = "kitchenaid.option.creative_chef"
    static let shopper = "kitchenaid.option.shopper"
    static let taster = "kitchenaid.option.taster"

    /// Storage key for a server-declared toggle (`toggle_key` in GET /agents).
    /// Produces the same strings as the constants above, so the roster-driven
    /// switches and `ChatOptions.current()` always read/write the same slots.
    static func storageKey(for toggleKey: String) -> String {
        "kitchenaid.option.\(toggleKey)"
    }
}

/// The optional `options` object sent with every `/chat` request.
/// Field names mirror the API: `creative_chef`, `shopper`, `taster`.
struct ChatOptions: Codable, Equatable {
    var creativeChef: Bool
    var shopper: Bool
    var taster: Bool

    enum CodingKeys: String, CodingKey {
        case creativeChef = "creative_chef"
        case shopper
        case taster
    }

    /// Backend defaults: creative mode off, shopper on, taster on.
    static let standard = ChatOptions(creativeChef: false, shopper: true, taster: true)

    /// Read the current toggles. Uses `object(forKey:)` rather than `bool(forKey:)`
    /// so an untouched key falls back to the real default (true for shopper/taster)
    /// instead of being coerced to false.
    static func current(from defaults: UserDefaults = .standard) -> ChatOptions {
        ChatOptions(
            creativeChef: defaults.object(forKey: AgentOptionKeys.creativeChef) as? Bool
                ?? standard.creativeChef,
            shopper: defaults.object(forKey: AgentOptionKeys.shopper) as? Bool
                ?? standard.shopper,
            taster: defaults.object(forKey: AgentOptionKeys.taster) as? Bool
                ?? standard.taster
        )
    }
}

/// One member of the agent team, as served by `GET /agents`.
///
/// `toggle_key` / `toggle_label` / `default` are only present for toggleable agents,
/// and `always_on_reason` only for the fixed ones; all four decode as optionals so
/// a missing key never breaks decoding.
struct AgentInfo: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let role: String
    let detail: String
    let toggleable: Bool
    let alwaysOnReason: String?
    let toggleKey: String?
    let toggleLabel: String?
    let defaultOn: Bool?

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case role
        case detail
        case toggleable
        case alwaysOnReason = "always_on_reason"
        case toggleKey = "toggle_key"
        case toggleLabel = "toggle_label"
        case defaultOn = "default"
    }

    /// SF Symbol per agent, with a neutral fallback for unknown future agents.
    var symbol: String {
        switch id {
        case "concierge": return "arrow.triangle.branch"
        case "chef": return "flame"
        case "dietitian": return "shield.fill"
        case "shopper": return "cart"
        case "profile_keeper": return "person.text.rectangle"
        case "taster": return "hand.thumbsup"
        default: return "circle.grid.2x2"
        }
    }

    /// The Dietitian gets distinct, prominent treatment: it is the safety gate and
    /// deliberately cannot be switched off.
    var isSafetyGate: Bool { id == "dietitian" }
}

/// `GET /agents` response envelope.
struct AgentsResponse: Codable {
    let agents: [AgentInfo]
}
