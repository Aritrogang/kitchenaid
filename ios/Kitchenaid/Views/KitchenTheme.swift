import SwiftUI

/// Design tokens: refined neutrals with a single muted terracotta accent.
///
/// Semantic rules, applied app-wide:
///   - `accent` (terracotta, ~#B85C38) is the only brand color: tint, buttons, highlights.
///   - `safe` (green) is reserved for safety-ok states: the Dietitian's gate, verified
///     substitutions, deterministic results, online status.
///   - `danger` (red) is reserved for allergies, errors, and unreachable states.
///   - `info` (muted amber) marks informational, non-blocking flags (budget, timing).
///
/// Colors are defined in code (no asset catalog needed for the drag-in workflow) and
/// adapt to light/dark via `UIColor` dynamic providers.
enum KitchenTheme {

    // MARK: - Brand

    /// Muted terracotta: #B85C38 in light, lifted slightly for dark backgrounds.
    static let accent = dynamic(
        light: UIColor(red: 0.722, green: 0.361, blue: 0.220, alpha: 1.0),
        dark: UIColor(red: 0.812, green: 0.463, blue: 0.322, alpha: 1.0)
    )

    // MARK: - Semantic

    /// Reserved for safety-ok: the Dietitian gate, verified swaps, online status.
    static let safe = dynamic(
        light: UIColor(red: 0.133, green: 0.475, blue: 0.286, alpha: 1.0),
        dark: UIColor(red: 0.373, green: 0.678, blue: 0.478, alpha: 1.0)
    )

    /// Reserved for allergies, errors, and unreachable states.
    static let danger = dynamic(
        light: UIColor(red: 0.718, green: 0.196, blue: 0.176, alpha: 1.0),
        dark: UIColor(red: 0.878, green: 0.400, blue: 0.373, alpha: 1.0)
    )

    /// Informational, non-blocking flags (over budget, takes longer, skill stretch).
    static let info = dynamic(
        light: UIColor(red: 0.647, green: 0.463, blue: 0.114, alpha: 1.0),
        dark: UIColor(red: 0.855, green: 0.663, blue: 0.302, alpha: 1.0)
    )

    // MARK: - Surfaces

    /// Primary card surface: flat, near-neutral.
    static let surface = dynamic(
        light: UIColor(red: 0.992, green: 0.988, blue: 0.984, alpha: 1.0),
        dark: UIColor(red: 0.118, green: 0.114, blue: 0.110, alpha: 1.0)
    )

    /// Recessed surface for secondary chrome (agent trace, input field).
    static let surfaceMuted = dynamic(
        light: UIColor(red: 0.961, green: 0.955, blue: 0.949, alpha: 1.0),
        dark: UIColor(red: 0.153, green: 0.149, blue: 0.145, alpha: 1.0)
    )

    /// Hairline separators and card strokes.
    static let hairline = dynamic(
        light: UIColor(white: 0.0, alpha: 0.10),
        dark: UIColor(white: 1.0, alpha: 0.12)
    )

    // MARK: - Per-agent accents (trace tags, Agents screen)

    /// Slate blue: the Shopper.
    static let slate = dynamic(
        light: UIColor(red: 0.259, green: 0.400, blue: 0.561, alpha: 1.0),
        dark: UIColor(red: 0.545, green: 0.663, blue: 0.800, alpha: 1.0)
    )

    /// Plum: the Taster.
    static let plum = dynamic(
        light: UIColor(red: 0.475, green: 0.318, blue: 0.573, alpha: 1.0),
        dark: UIColor(red: 0.678, green: 0.553, blue: 0.776, alpha: 1.0)
    )

    /// Neutral gray: the Profile Keeper and unknown future agents.
    static let neutral = dynamic(
        light: UIColor(red: 0.443, green: 0.435, blue: 0.427, alpha: 1.0),
        dark: UIColor(red: 0.635, green: 0.627, blue: 0.616, alpha: 1.0)
    )

    /// Accent color for an agent, keyed by the names the backend uses in the trace
    /// ("Concierge", "Chef", ...) or the roster ids ("profile_keeper", ...).
    static func agentColor(_ agent: String) -> Color {
        let key = agent.lowercased().replacingOccurrences(of: " ", with: "_")
        switch key {
        case "concierge":
            return accent
        case "chef", "creative_chef":
            return info
        case "dietitian":
            return safe
        case "shopper":
            return slate
        case "taster":
            return plum
        default:
            return neutral
        }
    }

    // MARK: - Helpers

    private static func dynamic(light: UIColor, dark: UIColor) -> Color {
        Color(uiColor: UIColor { trait in
            trait.userInterfaceStyle == .dark ? dark : light
        })
    }
}

/// A flat card container: neutral surface, hairline stroke, whisper of depth.
struct KitchenCard<Content: View>: View {
    @ViewBuilder let content: Content

    var body: some View {
        content
            .padding(16)
            .background(KitchenTheme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(KitchenTheme.hairline, lineWidth: 1)
            )
            .shadow(color: Color.black.opacity(0.05), radius: 5, x: 0, y: 2)
    }
}

/// A small pill used for flags and tags. Dynamic-Type friendly (scales with text).
struct TagPill: View {
    let text: String
    var tint: Color = KitchenTheme.info

    var body: some View {
        Text(text)
            .font(.caption)
            .fontWeight(.medium)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(tint.opacity(0.14))
            .foregroundStyle(tint)
            .clipShape(Capsule())
    }
}

/// Uppercase caption used as an in-card section label. One definition so hierarchy
/// stays consistent across the meal card, grocery list, and agents screen.
struct SectionLabel: View {
    let text: String
    var tint: Color = Color.secondary

    var body: some View {
        Text(text)
            .font(.caption.weight(.semibold))
            .kerning(0.8)
            .textCase(.uppercase)
            .foregroundStyle(tint)
    }
}
