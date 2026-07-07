import SwiftUI

/// The Agents tab: the team roster from `GET /agents`, with live switches for the
/// toggleable members and a deliberately locked row for the Dietitian.
///
/// This screen is the multi-agent story told directly: what each specialist does,
/// which ones the user can turn on or off for their need, and why the safety gate
/// is not on that list. Nothing here is hardcoded — the roster, roles, toggle keys,
/// and the Dietitian's always-on reason all come from the backend.
struct AgentsView: View {
    @EnvironmentObject private var viewModel: ChatViewModel

    var body: some View {
        NavigationStack {
            content
                .background(KitchenTheme.surfaceMuted.ignoresSafeArea())
                .navigationTitle("Agents")
                .navigationBarTitleDisplayMode(.inline)
        }
        .task { await viewModel.loadAgents() }
    }

    @ViewBuilder
    private var content: some View {
        switch viewModel.teamState {
        case .idle, .loading:
            ProgressView("Meeting the team…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        case .failed(let reason):
            failedState(reason)
        case .loaded(let agents):
            roster(agents)
        }
    }

    // MARK: - Roster

    private func roster(_ agents: [AgentInfo]) -> some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 12) {
                header

                ForEach(agents) { agent in
                    AgentRow(agent: agent)
                }

                Text("Changes apply from your next message.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity)
                    .padding(.top, 4)
            }
            .padding(16)
        }
        .refreshable { await viewModel.loadAgents(force: true) }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Six specialists cooperate on every request.")
                .font(.subheadline.weight(.medium))
            Text("Switch members on or off to fit what you need — more creativity, a leaner turn, no learning. The safety gate is not a switch.")
                .font(.footnote)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.bottom, 4)
        .accessibilityElement(children: .combine)
    }

    private func failedState(_ reason: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "point.3.connected.trianglepath.dotted")
                .font(.system(size: 40))
                .foregroundStyle(.secondary)
            Text("Couldn't load the team")
                .font(.headline)
            Text(reason)
                .font(.footnote)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)
            Button("Try again") {
                Task { await viewModel.loadAgents(force: true) }
            }
            .buttonStyle(.borderedProminent)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - One agent

/// A single roster card. Toggleable agents get a switch persisted straight to the
/// slot `ChatOptions.current()` reads; fixed agents state why they're always on.
/// The Dietitian additionally gets the safety treatment: green, badged, explained.
private struct AgentRow: View {
    let agent: AgentInfo
    @AppStorage private var isOn: Bool

    init(agent: AgentInfo) {
        self.agent = agent
        // Bind to the same UserDefaults slot the chat request reads at send time.
        // Fixed agents never render the switch, so their binding is inert.
        self._isOn = AppStorage(
            wrappedValue: agent.defaultOn ?? true,
            AgentOptionKeys.storageKey(for: agent.toggleKey ?? agent.id)
        )
    }

    private var tint: Color { KitchenTheme.agentColor(agent.id) }

    var body: some View {
        KitchenCard {
            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .center, spacing: 12) {
                    iconSquare

                    VStack(alignment: .leading, spacing: 2) {
                        Text(agent.name)
                            .font(.subheadline.weight(.semibold))
                        Text(agent.role)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    Spacer(minLength: 8)

                    trailing
                }

                Text(agent.detail)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                if let reason = agent.alwaysOnReason {
                    alwaysOnNote(reason)
                }
            }
        }
        .overlay(
            // The safety gate is visually set apart: a green keyline, not a switch.
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(agent.isSafetyGate ? KitchenTheme.safe.opacity(0.45) : .clear,
                        lineWidth: 1.5)
        )
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilitySummary)
    }

    private var iconSquare: some View {
        Image(systemName: agent.symbol)
            .font(.system(size: 16, weight: .semibold))
            .foregroundStyle(tint)
            .frame(width: 36, height: 36)
            .background(tint.opacity(0.12))
            .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
    }

    @ViewBuilder
    private var trailing: some View {
        if agent.toggleable {
            Toggle(agent.toggleLabel ?? agent.name, isOn: $isOn)
                .labelsHidden()
                .tint(tint)
                .accessibilityLabel("\(agent.toggleLabel ?? agent.name), \(isOn ? "on" : "off")")
        } else {
            HStack(spacing: 4) {
                Image(systemName: agent.isSafetyGate ? "lock.fill" : "checkmark")
                    .font(.caption2.weight(.semibold))
                Text("Always on")
                    .font(.caption.weight(.medium))
            }
            .foregroundStyle(agent.isSafetyGate ? KitchenTheme.safe : Color.secondary)
            .padding(.horizontal, 9)
            .padding(.vertical, 4)
            .background((agent.isSafetyGate ? KitchenTheme.safe : Color.secondary).opacity(0.10))
            .clipShape(Capsule())
        }
    }

    private func alwaysOnNote(_ reason: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Image(systemName: agent.isSafetyGate ? "shield.fill" : "info.circle")
                .font(.caption2)
            Text(reason)
                .font(.caption)
                .fixedSize(horizontal: false, vertical: true)
        }
        .foregroundStyle(agent.isSafetyGate ? KitchenTheme.safe : Color.secondary)
    }

    private var accessibilitySummary: String {
        var parts = [agent.name, agent.role, agent.detail]
        if agent.toggleable {
            parts.append(isOn ? "Enabled" : "Disabled")
        } else {
            parts.append("Always on")
            if let reason = agent.alwaysOnReason { parts.append(reason) }
        }
        return parts.joined(separator: ". ")
    }
}
