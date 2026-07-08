import SwiftUI

/// Rich card for a recommended meal: title, quick stats, why-bullets, ingredients,
/// and informational flags.
struct MealCardView: View {
    let meal: Meal

    var body: some View {
        KitchenCard {
            VStack(alignment: .leading, spacing: 14) {
                header
                statsRow
                if !meal.why.isEmpty { whySection }
                if !meal.ingredients.isEmpty { ingredientsSection }
                if !meal.flags.isEmpty { flagsSection }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Meal suggestion: \(meal.name)")
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(meal.name)
                .font(.title3.weight(.semibold))
            Text(meal.cuisine.capitalized)
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
    }

    private var statsRow: some View {
        // Wraps naturally at larger Dynamic Type sizes.
        HStack(alignment: .top, spacing: 18) {
            stat(icon: "clock", value: "\(meal.timeMin) min", label: "Time")
            stat(icon: "person.2", value: "\(meal.servings)", label: "Servings")
            stat(icon: "dollarsign.circle",
                 value: Format.money(meal.costPerServingUSD), label: "Per serving")
            Spacer(minLength: 0)
        }
        .padding(.vertical, 4)
    }

    private func stat(icon: String, value: String, label: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Label(value, systemImage: icon)
                .font(.subheadline.weight(.semibold))
                .labelStyle(.titleAndIcon)
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(label): \(value)")
    }

    private var whySection: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Why this")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(KitchenTheme.accent)
            ForEach(Array(meal.why.enumerated()), id: \.offset) { _, reason in
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Image(systemName: "checkmark.seal.fill")
                        .font(.caption)
                        .foregroundStyle(KitchenTheme.safe)
                    Text(reason)
                        .font(.subheadline)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private var ingredientsSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            Divider()
            Label(nutritionSummary, systemImage: "flame")
                .font(.footnote)
                .foregroundStyle(.secondary)
                .accessibilityLabel(nutritionSummary)

            Text("Ingredients")
                .font(.subheadline.weight(.semibold))
                .padding(.top, 2)
            ForEach(meal.ingredients) { ingredient in
                HStack {
                    Text(ingredient.item.capitalized)
                        .font(.subheadline)
                    Spacer()
                    Text(Format.grams(ingredient.grams))
                        .font(.subheadline.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
                .accessibilityElement(children: .combine)
                .accessibilityLabel("\(ingredient.item), \(Format.grams(ingredient.grams))")
            }
        }
    }

    private var flagsSection: some View {
        FlowRow(spacing: 8) {
            ForEach(Array(meal.flags.enumerated()), id: \.offset) { _, flag in
                TagPill(text: flag, tint: KitchenTheme.info)
            }
        }
        .padding(.top, 2)
    }

    private var nutritionSummary: String {
        let cals = Int(meal.caloriesPerServing.rounded())
        let protein = Int(meal.proteinPerServingG.rounded())
        return "\(cals) kcal · \(protein) g protein per serving"
    }
}
