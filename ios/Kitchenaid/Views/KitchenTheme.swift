import SwiftUI

/// A warm "kitchen" palette and a few shared style helpers.
///
/// Colors are defined in code (no asset catalog needed for the drag-in workflow) and
/// adapt to light/dark via `UIColor` dynamic providers so the app looks right in both.
enum KitchenTheme {
    /// Warm terracotta — primary accent for buttons, tint, highlights.
    static let accent = Color(uiColor: UIColor { trait in
        trait.userInterfaceStyle == .dark
            ? UIColor(red: 0.90, green: 0.45, blue: 0.30, alpha: 1.0)
            : UIColor(red: 0.80, green: 0.33, blue: 0.20, alpha: 1.0)
    })

    /// Soft herb green — used for "safe"/positive accents.
    static let herb = Color(uiColor: UIColor { trait in
        trait.userInterfaceStyle == .dark
            ? UIColor(red: 0.52, green: 0.72, blue: 0.45, alpha: 1.0)
            : UIColor(red: 0.36, green: 0.56, blue: 0.30, alpha: 1.0)
    })

    /// Card background — a warm off-white / deep warm gray.
    static let card = Color(uiColor: UIColor { trait in
        trait.userInterfaceStyle == .dark
            ? UIColor(red: 0.16, green: 0.14, blue: 0.13, alpha: 1.0)
            : UIColor(red: 0.99, green: 0.97, blue: 0.94, alpha: 1.0)
    })

    /// A subtle warm border/hairline.
    static let hairline = Color(uiColor: UIColor { trait in
        trait.userInterfaceStyle == .dark
            ? UIColor(white: 1.0, alpha: 0.10)
            : UIColor(red: 0.85, green: 0.79, blue: 0.72, alpha: 1.0)
    })

    /// Amber — used for informational flags.
    static let amber = Color(uiColor: UIColor { trait in
        trait.userInterfaceStyle == .dark
            ? UIColor(red: 0.92, green: 0.70, blue: 0.28, alpha: 1.0)
            : UIColor(red: 0.78, green: 0.55, blue: 0.10, alpha: 1.0)
    })
}

/// A rounded, warm card container used throughout the app.
struct KitchenCard<Content: View>: View {
    @ViewBuilder let content: Content

    var body: some View {
        content
            .padding(16)
            .background(KitchenTheme.card)
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .stroke(KitchenTheme.hairline, lineWidth: 1)
            )
    }
}

/// A small pill used for flags and tags. Dynamic-Type friendly (scales with text).
struct TagPill: View {
    let text: String
    var tint: Color = KitchenTheme.amber

    var body: some View {
        Text(text)
            .font(.caption)
            .fontWeight(.medium)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(tint.opacity(0.18))
            .foregroundStyle(tint)
            .clipShape(Capsule())
    }
}
