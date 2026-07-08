import Foundation
import SwiftUI

/// The single observable source of truth for the UI.
///
/// Holds the conversation transcript and the persisted profile, and drives the API
/// with async/await. Marked `@MainActor` so every published mutation happens on the
/// main thread — the `await` on the network call hops off and back automatically.
@MainActor
final class ChatViewModel: ObservableObject {
    // Conversation
    @Published var messages: [ChatMessage] = []
    @Published var draft: String = ""
    @Published var isSending: Bool = false

    // Connection status, surfaced as a small banner / dot.
    enum Connection: Equatable {
        case unknown
        case checking
        case online(agents: [String])
        case offline(reason: String)
    }
    @Published var connection: Connection = .unknown

    // The agent roster for the Agents tab, fetched from GET /agents.
    enum TeamState: Equatable {
        case idle
        case loading
        case loaded([AgentInfo])
        case failed(String)
    }
    @Published var teamState: TeamState = .idle

    // Profile + server address, mirrored from the store and re-persisted on change.
    @Published var profile: Profile {
        didSet { ProfileStore.saveProfile(profile) }
    }
    @Published var baseURL: String {
        didSet {
            ProfileStore.saveBaseURL(baseURL)
            let value = baseURL
            Task { await api.updateBaseURL(value) }
            // The roster may differ on another backend; refetch on next visit.
            teamState = .idle
        }
    }

    private let api: KitchenaidAPI

    init() {
        let storedProfile = ProfileStore.loadProfile()
        let storedURL = ProfileStore.loadBaseURL()
        self.profile = storedProfile
        self.baseURL = storedURL
        self.api = KitchenaidAPI(baseURLString: storedURL)
    }

    // MARK: - Health

    /// Ping the backend and update the connection banner. Safe to call repeatedly
    /// (e.g. `.task` on ChatView, and after the user edits the server address).
    func checkHealth() async {
        connection = .checking
        do {
            let health = try await api.health()
            connection = .online(agents: health.agents)
        } catch {
            let reason = (error as? APIError)?.errorDescription ?? error.localizedDescription
            connection = .offline(reason: reason)
        }
    }

    // MARK: - Sending

    /// Send the current draft as a turn.
    func sendDraft() async {
        let query = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return }
        draft = ""
        await send(query)
    }

    /// Send an arbitrary query (used by the quick-suggestion buttons).
    func send(_ query: String) async {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !isSending else { return }

        messages.append(.user(trimmed))
        isSending = true
        defer { isSending = false }

        do {
            let response = try await api.chat(
                userID: profile.userID,
                query: trimmed,
                profile: profile,
                options: ChatOptions.current()
            )
            messages.append(.assistant(response))
            // A successful round-trip means we're online.
            connection = .online(agents: agentsFromTrace(response))
        } catch {
            let reason = (error as? APIError)?.errorDescription ?? error.localizedDescription
            messages.append(.error(reason))
            connection = .offline(reason: reason)
        }
    }

    /// Clear the transcript (keeps profile and connection).
    func clearConversation() {
        messages.removeAll()
    }

    // MARK: - Agent roster

    /// Fetch the team from GET /agents. Cached after the first success; pass
    /// `force: true` (pull-to-refresh, retry button) to refetch.
    func loadAgents(force: Bool = false) async {
        if !force {
            if case .loaded = teamState { return }
            if case .loading = teamState { return }
        }
        teamState = .loading
        do {
            let response = try await api.agents()
            teamState = .loaded(response.agents)
        } catch {
            let reason = (error as? APIError)?.errorDescription ?? error.localizedDescription
            teamState = .failed(reason)
        }
    }

    // Derive a best-effort agent list from a response's trace, for the banner.
    private func agentsFromTrace(_ response: ChatResponse) -> [String] {
        var seen: [String] = []
        for event in response.trace where !seen.contains(event.agent) {
            seen.append(event.agent)
        }
        return seen
    }

    // MARK: - Quick suggestions

    /// Common queries surfaced as one-tap buttons above the input field.
    let quickSuggestions: [QuickSuggestion] = [
        QuickSuggestion(icon: "fork.knife", label: "Dinner idea",
                        query: "what should I make for dinner?"),
        QuickSuggestion(icon: "cart", label: "Shopping list",
                        query: "what do I need to buy for dinner with rice?"),
        QuickSuggestion(icon: "refrigerator", label: "Use the fridge",
                        query: "use up the fridge — I have lentils and carrots"),
        QuickSuggestion(icon: "calendar", label: "Plan my week",
                        query: "plan my week"),
        QuickSuggestion(icon: "hand.thumbsup", label: "Loved it",
                        query: "loved it")
    ]
}

/// A one-tap query shortcut.
struct QuickSuggestion: Identifiable, Hashable {
    let id = UUID()
    let icon: String
    let label: String
    let query: String
}
