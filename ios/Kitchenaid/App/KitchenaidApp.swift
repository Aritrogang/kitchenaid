import SwiftUI

/// App entry point.
///
/// A single window that switches between the chat surface and the profile editor.
/// The `ChatViewModel` is created once here and injected so the conversation and
/// the user's profile survive tab switches.
@main
struct KitchenaidApp: App {
    @StateObject private var viewModel = ChatViewModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(viewModel)
                .tint(KitchenTheme.accent)
        }
    }
}

/// Top-level container: chat, the agent team, and the profile editor.
struct RootView: View {
    @EnvironmentObject private var viewModel: ChatViewModel

    var body: some View {
        TabView {
            ChatView()
                .tabItem {
                    Label("Kitchen", systemImage: "fork.knife")
                }

            AgentsView()
                .tabItem {
                    Label("Agents", systemImage: "point.3.connected.trianglepath.dotted")
                }

            ProfileView()
                .tabItem {
                    Label("Profile", systemImage: "person.crop.circle")
                }
        }
    }
}
