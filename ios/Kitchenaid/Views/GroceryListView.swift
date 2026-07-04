import SwiftUI

/// Card for a grocery list: line items with grams and cost, a total, and any
/// substitutions the Shopper made.
struct GroceryListView: View {
    let grocery: GroceryList

    var body: some View {
        KitchenCard {
            VStack(alignment: .leading, spacing: 12) {
                header
                Divider()
                itemsSection
                Divider()
                totalsSection
                if !grocery.substitutions.isEmpty {
                    Divider()
                    substitutionsSection
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Grocery list, \(grocery.items.count) items, total \(Format.money(grocery.totalCostUSD))")
    }

    private var header: some View {
        Label("Shopping list", systemImage: "cart")
            .font(.title3.weight(.semibold))
    }

    private var itemsSection: some View {
        VStack(spacing: 8) {
            ForEach(grocery.items) { item in
                HStack(alignment: .firstTextBaseline) {
                    Text(item.item.capitalized)
                        .font(.subheadline)
                    Text(Format.grams(item.grams))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Spacer(minLength: 8)
                    Text(Format.money(item.estCostUSD))
                        .font(.subheadline.monospacedDigit())
                }
                .accessibilityElement(children: .combine)
                .accessibilityLabel("\(item.item), \(Format.grams(item.grams)), \(Format.money(item.estCostUSD))")
            }
        }
    }

    private var totalsSection: some View {
        VStack(spacing: 4) {
            HStack {
                Text("Total")
                    .font(.subheadline.weight(.semibold))
                Spacer()
                Text(Format.money(grocery.totalCostUSD))
                    .font(.subheadline.weight(.semibold).monospacedDigit())
            }
            HStack {
                Text("Per serving")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                Text(Format.money(grocery.costPerServingUSD))
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var substitutionsSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Substitutions", systemImage: "arrow.triangle.2.circlepath")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(KitchenTheme.herb)
            ForEach(grocery.substitutions) { sub in
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(sub.original.capitalized)
                            .strikethrough()
                            .foregroundStyle(.secondary)
                        Image(systemName: "arrow.right")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        Text(sub.replacement.capitalized)
                            .fontWeight(.medium)
                    }
                    .font(.subheadline)
                    Text(sub.reason)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .accessibilityElement(children: .combine)
                .accessibilityLabel("Substituted \(sub.original) with \(sub.replacement). \(sub.reason)")
            }
        }
    }
}
