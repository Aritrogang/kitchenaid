import SwiftUI

/// The main chat surface: a connection banner, a scrollable transcript, the
/// quick-suggestion buttons, and the input bar.
struct ChatView: View {
    @EnvironmentObject private var viewModel: ChatViewModel
    @FocusState private var inputFocused: Bool

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ConnectionBanner(connection: viewModel.connection)
                transcript
                inputArea
            }
            .background(backgroundGradient.ignoresSafeArea())
            .navigationTitle("kitchenaid")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        viewModel.clearConversation()
                    } label: {
                        Image(systemName: "trash")
                    }
                    .disabled(viewModel.messages.isEmpty)
                    .accessibilityLabel("Clear conversation")
                }
            }
        }
        .task {
            // Ping the backend once when the chat first appears.
            await viewModel.checkHealth()
        }
    }

    // MARK: - Transcript

    private var transcript: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 16) {
                    if viewModel.messages.isEmpty {
                        EmptyStateView()
                            .padding(.top, 40)
                    }
                    ForEach(viewModel.messages) { message in
                        MessageRow(message: message)
                            .id(message.id)
                    }
                    if viewModel.isSending {
                        TypingIndicator()
                            .id("typing-indicator")
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 16)
            }
            .onChange(of: viewModel.messages.count) { _ in
                scrollToBottom(proxy)
            }
            .onChange(of: viewModel.isSending) { _ in
                scrollToBottom(proxy)
            }
        }
    }

    private func scrollToBottom(_ proxy: ScrollViewProxy) {
        withAnimation(.easeOut(duration: 0.2)) {
            if viewModel.isSending {
                proxy.scrollTo("typing-indicator", anchor: .bottom)
            } else if let last = viewModel.messages.last {
                proxy.scrollTo(last.id, anchor: .bottom)
            }
        }
    }

    // MARK: - Input

    private var inputArea: some View {
        VStack(spacing: 10) {
            quickSuggestions
            HStack(spacing: 10) {
                TextField("Ask about dinner…", text: $viewModel.draft, axis: .vertical)
                    .lineLimit(1...4)
                    .textFieldStyle(.plain)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(KitchenTheme.card)
                    .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 20, style: .continuous)
                            .stroke(KitchenTheme.hairline, lineWidth: 1)
                    )
                    .focused($inputFocused)
                    .submitLabel(.send)
                    .onSubmit(send)
                    .accessibilityLabel("Message")

                Button(action: send) {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.system(size: 32))
                        .foregroundStyle(canSend ? KitchenTheme.accent : Color.secondary)
                }
                .disabled(!canSend)
                .accessibilityLabel("Send message")
            }
        }
        .padding(.horizontal, 16)
        .padding(.top, 8)
        .padding(.bottom, 12)
        .background(.ultraThinMaterial)
    }

    private var quickSuggestions: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(viewModel.quickSuggestions) { suggestion in
                    Button {
                        Task { await viewModel.send(suggestion.query) }
                    } label: {
                        Label(suggestion.label, systemImage: suggestion.icon)
                            .font(.footnote.weight(.medium))
                            .padding(.horizontal, 12)
                            .padding(.vertical, 7)
                            .background(KitchenTheme.accent.opacity(0.12))
                            .foregroundStyle(KitchenTheme.accent)
                            .clipShape(Capsule())
                    }
                    .disabled(viewModel.isSending)
                    .accessibilityHint("Sends: \(suggestion.query)")
                }
            }
            .padding(.horizontal, 2)
        }
    }

    private var canSend: Bool {
        !viewModel.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !viewModel.isSending
    }

    private func send() {
        Task { await viewModel.sendDraft() }
    }

    private var backgroundGradient: LinearGradient {
        LinearGradient(
            colors: [KitchenTheme.accent.opacity(0.06), Color.clear],
            startPoint: .top,
            endPoint: .center
        )
    }
}

// MARK: - Supporting views

/// A thin status strip that reflects backend reachability.
private struct ConnectionBanner: View {
    let connection: ChatViewModel.Connection

    var body: some View {
        switch connection {
        case .unknown, .checking:
            banner(color: .secondary, text: "Connecting to the kitchen…", showSpinner: true)
        case .online(let agents):
            banner(color: KitchenTheme.herb,
                   text: agents.isEmpty ? "Online" : "Online · \(agents.count) agents ready")
        case .offline(let reason):
            banner(color: .orange, text: reason)
        }
    }

    @ViewBuilder
    private func banner(color: Color, text: String, showSpinner: Bool = false) -> some View {
        HStack(spacing: 8) {
            if showSpinner {
                ProgressView().scaleEffect(0.7)
            } else {
                Circle().fill(color).frame(width: 8, height: 8)
            }
            Text(text)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(2)
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 6)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(color.opacity(0.08))
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Connection status: \(text)")
    }
}

/// Friendly empty state before the first message.
private struct EmptyStateView: View {
    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "fork.knife.circle.fill")
                .font(.system(size: 56))
                .foregroundStyle(KitchenTheme.accent.opacity(0.8))
            Text("What's for dinner?")
                .font(.title2.weight(.semibold))
            Text("Ask for a quick meal, build a shopping list, use up what's in your fridge, or plan your week. Tap a suggestion below to start.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 24)
        }
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .combine)
    }
}

/// A small animated "…" while a turn is in flight.
private struct TypingIndicator: View {
    @State private var phase = 0.0

    var body: some View {
        HStack(spacing: 6) {
            ForEach(0..<3, id: \.self) { i in
                Circle()
                    .fill(KitchenTheme.accent.opacity(0.6))
                    .frame(width: 8, height: 8)
                    .scaleEffect(scale(for: i))
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .background(KitchenTheme.card)
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .onAppear {
            withAnimation(.easeInOut(duration: 0.6).repeatForever(autoreverses: true)) {
                phase = 1.0
            }
        }
        .accessibilityLabel("Thinking")
    }

    private func scale(for index: Int) -> CGFloat {
        let offset = Double(index) * 0.2
        return 0.6 + 0.4 * abs(sin((phase + offset) * .pi))
    }
}
