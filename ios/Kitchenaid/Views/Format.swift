import Foundation

/// Small, allocation-light formatting helpers shared across the meal and grocery views.
enum Format {
    /// A USD amount, e.g. `2.54` -> "$2.54".
    static func money(_ value: Double) -> String {
        String(format: "$%.2f", value)
    }

    /// A gram weight, integer-rounded, e.g. `300.0` -> "300 g".
    static func grams(_ value: Double) -> String {
        "\(Int(value.rounded())) g"
    }

    /// Milliseconds with one decimal, e.g. `0.0` -> "0.0 ms".
    static func ms(_ value: Double) -> String {
        String(format: "%.1f ms", value)
    }
}
