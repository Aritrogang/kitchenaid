import SwiftUI

/// Renders one transcript entry. User messages are right-aligned bubbles; assistant
/// messages are a left-aligned bubble plus optional meal card, grocery list, and trace;
/// errors render as an inline banner.
struct MessageRow: View {
    let message: ChatMessage

    var body: some View {
        switch message.role {
        case .user:
            userBubble
        case .assistant:
            assistantContent
        case .error:
            ErrorBanner(text: message.text)
        }
    }

    private var userBubble: some View {
        HStack {
            Spacer(minLength: 40)
            Text(message.text)
                .font(.body)
                .foregroundStyle(.white)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(KitchenTheme.accent)
                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                .frame(maxWidth: .infinity, alignment: .trailing)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("You said: \(message.text)")
    }

    @ViewBuilder
    private var assistantContent: some View {
        VStack(alignment: .leading, spacing: 12) {
            // The human-readable message.
            if !message.text.isEmpty {
                HStack {
                    Text(message.text)
                        .font(.body)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 10)
                        .background(KitchenTheme.surface)
                        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: 18, style: .continuous)
                                .stroke(KitchenTheme.hairline, lineWidth: 1)
                        )
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 40)
                }
                .accessibilityElement(children: .combine)
                .accessibilityLabel("Assistant: \(message.text)")
            }

            if let response = message.response {
                if let meal = response.meal {
                    MealCardView(meal: meal)
                }
                if let grocery = response.grocery {
                    GroceryListView(grocery: grocery)
                }
                if !response.trace.isEmpty {
                    TraceView(
                        trace: response.trace,
                        agentsUsed: response.agentsUsed,
                        usedLLM: response.usedLLM
                    )
                }
            }
        }
    }
}

/// The graceful error state shown when the API is unreachable or returns an error.
struct ErrorBanner: View {
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.orange)
            Text(text)
                .font(.footnote)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(12)
        .background(Color.orange.opacity(0.12))
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Color.orange.opacity(0.4), lineWidth: 1)
        )
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Error: \(text)")
    }
}
