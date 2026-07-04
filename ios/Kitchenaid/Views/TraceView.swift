import SwiftUI

/// A collapsible view of the agent handoff trace. This is the multi-agent
/// showcase: each row is `agent → action → detail` with its timing.
struct TraceView: View {
    let trace: [TraceEvent]
    let agentsUsed: Int
    let usedLLM: Bool

    @State private var expanded: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            disclosureButton
            if expanded {
                traceBody
                    .padding(.top, 10)
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .padding(12)
        .background(KitchenTheme.card.opacity(0.6))
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(KitchenTheme.hairline, lineWidth: 1)
        )
    }

    private var disclosureButton: some View {
        Button {
            withAnimation(.easeInOut(duration: 0.2)) { expanded.toggle() }
        } label: {
            HStack(spacing: 8) {
                Image(systemName: "point.3.connected.trianglepath.dotted")
                    .foregroundStyle(KitchenTheme.accent)
                Text(summary)
                    .font(.footnote.weight(.medium))
                    .foregroundStyle(.secondary)
                Spacer()
                Image(systemName: expanded ? "chevron.up" : "chevron.down")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Agent trace. \(summary). Double tap to \(expanded ? "collapse" : "expand").")
    }

    private var summary: String {
        let agentWord = agentsUsed == 1 ? "agent" : "agents"
        let llm = usedLLM ? " · used LLM" : ""
        return "\(agentsUsed) \(agentWord) · \(trace.count) steps\(llm)"
    }

    private var traceBody: some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(Array(trace.enumerated()), id: \.offset) { index, event in
                HStack(alignment: .top, spacing: 10) {
                    stepMarker(index: index)
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 6) {
                            Text(event.agent)
                                .font(.footnote.weight(.semibold))
                            Text(event.action)
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                        }
                        if !event.detail.isEmpty {
                            Text(event.detail)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    Spacer(minLength: 8)
                    Text(Format.ms(event.ms))
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(.tertiary)
                }
                .accessibilityElement(children: .combine)
                .accessibilityLabel(
                    "Step \(index + 1): \(event.agent) \(event.action) \(event.detail), \(Format.ms(event.ms))"
                )
            }
        }
    }

    private func stepMarker(index: Int) -> some View {
        Text("\(index + 1)")
            .font(.caption2.weight(.bold).monospacedDigit())
            .foregroundStyle(.white)
            .frame(width: 20, height: 20)
            .background(KitchenTheme.accent)
            .clipShape(Circle())
    }
}
