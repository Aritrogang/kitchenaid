import Foundation

/// UserDefaults-backed persistence for the profile and server address.
///
/// The profile is stored as a single JSON blob under one key so adding fields later
/// doesn't require new keys. A stable `user_id` is generated once and reused so the
/// backend's per-user session memory (last meal, learned taste) works across launches.
enum ProfileStore {
    private static let profileKey = "kitchenaid.profile.v1"
    private static let baseURLKey = "kitchenaid.baseURL.v1"

    static let defaultBaseURL = "http://localhost:8000"

    // MARK: Profile

    static func loadProfile() -> Profile {
        guard
            let data = UserDefaults.standard.data(forKey: profileKey),
            let profile = try? JSONDecoder().decode(Profile.self, from: data)
        else {
            // First launch: mint and persist a stable id immediately.
            let fresh = Profile.makeDefault()
            saveProfile(fresh)
            return fresh
        }
        return profile
    }

    static func saveProfile(_ profile: Profile) {
        if let data = try? JSONEncoder().encode(profile) {
            UserDefaults.standard.set(data, forKey: profileKey)
        }
    }

    // MARK: Server address

    static func loadBaseURL() -> String {
        UserDefaults.standard.string(forKey: baseURLKey) ?? defaultBaseURL
    }

    static func saveBaseURL(_ url: String) {
        UserDefaults.standard.set(url, forKey: baseURLKey)
    }
}
