import Foundation

/// The nine top-8+sesame allergens the backend recognizes. Raw values are the exact
/// lowercase strings the API expects in `profile.allergies`.
enum Allergen: String, CaseIterable, Codable, Identifiable, Hashable {
    case peanut
    case treeNut = "tree_nut"
    case milk
    case egg
    case soy
    case wheat
    case fish
    case shellfish
    case sesame

    var id: String { rawValue }

    /// Human-readable label for the UI.
    var label: String {
        switch self {
        case .peanut: return "Peanut"
        case .treeNut: return "Tree nut"
        case .milk: return "Milk"
        case .egg: return "Egg"
        case .soy: return "Soy"
        case .wheat: return "Wheat"
        case .fish: return "Fish"
        case .shellfish: return "Shellfish"
        case .sesame: return "Sesame"
        }
    }
}

/// Diets the backend recognizes. Raw values match `profile.diet` exactly.
enum Diet: String, CaseIterable, Codable, Identifiable, Hashable {
    case none
    case vegetarian
    case vegan
    case pescatarian
    case halal
    case kosher

    var id: String { rawValue }

    var label: String {
        switch self {
        case .none: return "No restriction"
        case .vegetarian: return "Vegetarian"
        case .vegan: return "Vegan"
        case .pescatarian: return "Pescatarian"
        case .halal: return "Halal"
        case .kosher: return "Kosher"
        }
    }
}

/// Cooking skill levels the backend recognizes. Raw values match `profile.skill`.
enum Skill: String, CaseIterable, Codable, Identifiable, Hashable {
    case beginner
    case intermediate
    case advanced

    var id: String { rawValue }

    var label: String { rawValue.capitalized }
}

/// The user's persistent profile. This is the subset of the backend `Profile` the
/// iOS client owns; the backend fills in the rest with defaults.
///
/// Sent as the `profile` object of every `/chat` request.
struct Profile: Codable, Equatable {
    var userID: String
    var name: String
    var allergies: [Allergen]
    var diet: Diet
    var budgetPerMealUSD: Double
    var skill: Skill
    var dislikes: [String]

    enum CodingKeys: String, CodingKey {
        case userID = "user_id"
        case name
        case allergies
        case diet
        case budgetPerMealUSD = "budget_per_meal_usd"
        case skill
        case dislikes
    }

    /// A sensible starting profile with a freshly minted user id.
    static func makeDefault(userID: String = UUID().uuidString) -> Profile {
        Profile(
            userID: userID,
            name: "",
            allergies: [],
            diet: .none,
            budgetPerMealUSD: 6.0,
            skill: .beginner,
            dislikes: []
        )
    }
}
