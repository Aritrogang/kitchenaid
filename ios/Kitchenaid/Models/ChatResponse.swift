import Foundation

/// The intent the Concierge routed the query to. Decoded leniently so an unknown
/// future intent from the backend never breaks decoding.
enum Intent: String, Codable {
    case quickDinner = "quick_dinner"
    case useFridge = "use_fridge"
    case shopping
    case feedback
    case planWeek = "plan_week"
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = Intent(rawValue: raw) ?? .unknown
    }

    var label: String {
        switch self {
        case .quickDinner: return "Quick dinner"
        case .useFridge: return "Use the fridge"
        case .shopping: return "Shopping"
        case .feedback: return "Feedback"
        case .planWeek: return "Weekly plan"
        case .unknown: return "Response"
        }
    }
}

/// One ingredient line inside a `Meal`.
struct MealIngredient: Codable, Hashable, Identifiable {
    let item: String
    let grams: Double

    // Stable identity for SwiftUI lists; the backend has no id here.
    var id: String { "\(item)-\(grams)" }
}

/// A recommended meal. Present only when the response actually chose one.
struct Meal: Codable, Hashable {
    let name: String
    let cuisine: String
    let timeMin: Int
    let servings: Int
    let costPerServingUSD: Double
    let caloriesPerServing: Double
    let proteinPerServingG: Double
    let flags: [String]
    let why: [String]
    let ingredients: [MealIngredient]

    enum CodingKeys: String, CodingKey {
        case name
        case cuisine
        case timeMin = "time_min"
        case servings
        case costPerServingUSD = "cost_per_serving_usd"
        case caloriesPerServing = "calories_per_serving"
        case proteinPerServingG = "protein_per_serving_g"
        case flags
        case why
        case ingredients
    }
}

/// One line item on a grocery list.
struct GroceryItem: Codable, Hashable, Identifiable {
    let item: String
    let grams: Double
    let estCostUSD: Double

    var id: String { "\(item)-\(grams)" }

    enum CodingKeys: String, CodingKey {
        case item
        case grams
        case estCostUSD = "est_cost_usd"
    }
}

/// A safe-swap the Shopper made when building the list.
struct Substitution: Codable, Hashable, Identifiable {
    let original: String
    let replacement: String
    let reason: String

    var id: String { "\(original)->\(replacement)" }
}

/// A grocery list. Present only when the query asked to buy something.
struct GroceryList: Codable, Hashable {
    let totalCostUSD: Double
    let costPerServingUSD: Double
    let items: [GroceryItem]
    let substitutions: [Substitution]

    enum CodingKeys: String, CodingKey {
        case totalCostUSD = "total_cost_usd"
        case costPerServingUSD = "cost_per_serving_usd"
        case items
        case substitutions
    }
}

/// One step in the agent handoff trace. This is what powers the TraceView and
/// showcases the multi-agent system.
struct TraceEvent: Codable, Hashable, Identifiable {
    let agent: String
    let action: String
    let detail: String
    let ms: Double

    // The backend has no id; synthesize one from the fields plus position at decode.
    var id: String { "\(agent)-\(action)-\(detail)-\(ms)" }
}

/// The full `/chat` response.
///
/// `meal` and `grocery` are nullable in the API and are therefore optional here.
/// The default synthesized `Decodable` conformance treats a missing OR explicit-null
/// key as `nil`, which matches the backend exactly.
struct ChatResponse: Codable {
    let intent: Intent
    let message: String
    let agentsUsed: Int
    let usedLLM: Bool
    let trace: [TraceEvent]
    let meal: Meal?
    let grocery: GroceryList?

    enum CodingKeys: String, CodingKey {
        case intent
        case message
        case agentsUsed = "agents_used"
        case usedLLM = "used_llm"
        case trace
        case meal
        case grocery
    }
}

/// The `/health` response.
struct HealthResponse: Codable {
    let status: String
    let agents: [String]
}
