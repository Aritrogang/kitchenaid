import Foundation

/// Errors surfaced by the API client, with user-friendly descriptions the UI can show
/// directly in its error state.
enum APIError: LocalizedError {
    case invalidBaseURL(String)
    case transport(Error)
    case http(status: Int, body: String)
    case decoding(Error)

    var errorDescription: String? {
        switch self {
        case .invalidBaseURL(let raw):
            return "The server address \"\(raw)\" isn't a valid URL. Fix it in Profile → Server."
        case .transport:
            return "Couldn't reach the kitchen. Is the backend running and is the server address correct?"
        case .http(let status, let body):
            let trimmed = body.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty {
                return "The server returned an error (HTTP \(status))."
            }
            return "The server returned an error (HTTP \(status)): \(trimmed)"
        case .decoding:
            return "The server replied in a format the app didn't understand."
        }
    }
}

/// Async HTTP client for the kitchenaid backend.
///
/// An `actor` so the mutable `baseURL` is isolated: the view model can update the
/// server address from the main actor while a request is in flight without a data race.
actor KitchenaidAPI {
    private var baseURL: URL
    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    /// - Parameter baseURLString: e.g. `http://localhost:8000`. Falls back to that
    ///   default if the supplied string is empty or malformed.
    init(baseURLString: String = "http://localhost:8000", session: URLSession = .shared) {
        self.baseURL = URL(string: baseURLString) ?? URL(string: "http://localhost:8000")!
        self.session = session
        self.decoder = JSONDecoder()
        self.encoder = JSONEncoder()
    }

    /// Point the client at a new backend. Called when the user edits the server address.
    func updateBaseURL(_ string: String) {
        let trimmed = string.trimmingCharacters(in: .whitespacesAndNewlines)
        if let url = URL(string: trimmed), url.scheme != nil, url.host != nil {
            self.baseURL = url
        }
    }

    /// GET /health — throws if the backend is unreachable or unhealthy.
    @discardableResult
    func health() async throws -> HealthResponse {
        let request = URLRequest(url: endpoint("health"))
        return try await send(request)
    }

    /// POST /chat — the single conversational turn.
    func chat(userID: String, query: String, profile: Profile) async throws -> ChatResponse {
        var request = URLRequest(url: endpoint("chat"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let body = ChatRequest(userID: userID, query: query, profile: profile)
        do {
            request.httpBody = try encoder.encode(body)
        } catch {
            throw APIError.decoding(error)
        }
        return try await send(request)
    }

    // MARK: - Plumbing

    private func endpoint(_ path: String) -> URL {
        // `appendingPathComponent` keeps any base path prefix intact.
        baseURL.appendingPathComponent(path)
    }

    private func send<T: Decodable>(_ request: URLRequest) async throws -> T {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.transport(error)
        }

        if let http = response as? HTTPURLResponse, !(200...299).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw APIError.http(status: http.statusCode, body: body)
        }

        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decoding(error)
        }
    }
}
