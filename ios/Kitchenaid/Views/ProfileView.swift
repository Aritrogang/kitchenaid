import SwiftUI

/// Profile editor: name, allergies (multi-select), diet, budget, skill, dislikes,
/// plus the backend server address. Everything is bound to `ChatViewModel.profile`
/// / `baseURL`, which persist to UserDefaults on every change.
struct ProfileView: View {
    @EnvironmentObject private var viewModel: ChatViewModel
    @State private var newDislike: String = ""

    var body: some View {
        NavigationStack {
            Form {
                identitySection
                allergiesSection
                dietSection
                budgetSkillSection
                dislikesSection
                serverSection
                aboutSection
            }
            .navigationTitle("Profile")
        }
    }

    // MARK: - Sections

    private var identitySection: some View {
        Section("You") {
            TextField("Name", text: $viewModel.profile.name)
                .textInputAutocapitalization(.words)
                .accessibilityLabel("Your name")
        }
    }

    private var allergiesSection: some View {
        Section {
            ForEach(Allergen.allCases) { allergen in
                Toggle(allergen.label, isOn: binding(for: allergen))
                    .tint(KitchenTheme.accent)
                    .accessibilityHint("Allergen. When on, meals avoid \(allergen.label).")
            }
        } header: {
            Text("Allergies")
        } footer: {
            Text("Hard rule: the Dietitian blocks any meal containing these.")
        }
    }

    private var dietSection: some View {
        Section("Diet") {
            Picker("Diet", selection: $viewModel.profile.diet) {
                ForEach(Diet.allCases) { diet in
                    Text(diet.label).tag(diet)
                }
            }
            .accessibilityLabel("Diet")
        }
    }

    private var budgetSkillSection: some View {
        Section("Cooking") {
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text("Budget per meal")
                    Spacer()
                    Text(Format.money(viewModel.profile.budgetPerMealUSD))
                        .foregroundStyle(.secondary)
                        .monospacedDigit()
                }
                Slider(
                    value: $viewModel.profile.budgetPerMealUSD,
                    in: 1...30,
                    step: 0.5
                )
                .tint(KitchenTheme.accent)
                .accessibilityLabel("Budget per meal in dollars")
                .accessibilityValue(Format.money(viewModel.profile.budgetPerMealUSD))
            }

            Picker("Skill", selection: $viewModel.profile.skill) {
                ForEach(Skill.allCases) { skill in
                    Text(skill.label).tag(skill)
                }
            }
            .accessibilityLabel("Cooking skill")
        }
    }

    private var dislikesSection: some View {
        Section {
            ForEach(viewModel.profile.dislikes, id: \.self) { dislike in
                Text(dislike.capitalized)
            }
            .onDelete { indexSet in
                viewModel.profile.dislikes.remove(atOffsets: indexSet)
            }

            HStack {
                TextField("Add a dislike (e.g. mushroom)", text: $newDislike)
                    .textInputAutocapitalization(.never)
                    .onSubmit(addDislike)
                    .accessibilityLabel("New dislike")
                Button("Add", action: addDislike)
                    .disabled(trimmedNewDislike.isEmpty)
            }
        } header: {
            Text("Dislikes")
        } footer: {
            Text("Soft preference: the assistant steers away from these when it can.")
        }
    }

    private var serverSection: some View {
        Section {
            TextField("http://localhost:8000", text: $viewModel.baseURL)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .keyboardType(.URL)
                .accessibilityLabel("Backend server address")
            Button {
                Task { await viewModel.checkHealth() }
            } label: {
                Label("Test connection", systemImage: "antenna.radiowaves.left.and.right")
            }
            connectionStatusRow
        } header: {
            Text("Server")
        } footer: {
            Text("Point this at your running FastAPI backend. On the iOS Simulator, localhost reaches your Mac. On a physical device, use your Mac's LAN IP (e.g. http://192.168.1.20:8000).")
        }
    }

    @ViewBuilder
    private var connectionStatusRow: some View {
        switch viewModel.connection {
        case .unknown:
            EmptyView()
        case .checking:
            HStack { ProgressView().scaleEffect(0.8); Text("Checking…").foregroundStyle(.secondary) }
        case .online(let agents):
            Label(
                agents.isEmpty ? "Online" : "Online · \(agents.joined(separator: ", "))",
                systemImage: "checkmark.circle.fill"
            )
            .foregroundStyle(KitchenTheme.safe)
            .font(.footnote)
        case .offline(let reason):
            Label(reason, systemImage: "xmark.octagon.fill")
                .foregroundStyle(.orange)
                .font(.footnote)
        }
    }

    private var aboutSection: some View {
        Section {
            LabeledContent("User ID", value: shortID)
                .font(.footnote)
                .foregroundStyle(.secondary)
                .accessibilityLabel("User ID \(viewModel.profile.userID)")
        } footer: {
            Text("A stable, on-device ID. The backend uses it to remember your taste and last meal across sessions.")
        }
    }

    // MARK: - Helpers

    private func binding(for allergen: Allergen) -> Binding<Bool> {
        Binding(
            get: { viewModel.profile.allergies.contains(allergen) },
            set: { isOn in
                if isOn {
                    if !viewModel.profile.allergies.contains(allergen) {
                        viewModel.profile.allergies.append(allergen)
                    }
                } else {
                    viewModel.profile.allergies.removeAll { $0 == allergen }
                }
            }
        )
    }

    private var trimmedNewDislike: String {
        newDislike.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }

    private func addDislike() {
        let value = trimmedNewDislike
        guard !value.isEmpty, !viewModel.profile.dislikes.contains(value) else {
            newDislike = ""
            return
        }
        viewModel.profile.dislikes.append(value)
        newDislike = ""
    }

    private var shortID: String {
        String(viewModel.profile.userID.prefix(8)) + "…"
    }
}
