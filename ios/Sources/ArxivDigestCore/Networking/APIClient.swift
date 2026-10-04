import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

/// Errors thrown by the API client.
public enum APIError: Error, LocalizedError, Sendable {
    case invalidURL
    case invalidResponse
    case http(Int, String)
    case decoding(Error)
    case network(Error)

    public var errorDescription: String? {
        switch self {
        case .invalidURL: return "Invalid URL"
        case .invalidResponse: return "Invalid response from server"
        case .http(let code, let body): return "Server error (\(code)): \(body)"
        case .decoding: return "Could not decode the server response"
        case .network(let err): return "Network error: \(err.localizedDescription)"
        }
    }
}

/// A minimal async/await HTTP client for the digest service.
///
/// Uses `URLSession` + `Codable` (no third-party dependency). The OpenAPI spec
/// from the backend is the contract this client implements.
public struct APIClient: Sendable {
    public let baseURL: URL
    public var authToken: String?
    private let session: URLSession

    /// - Parameter session: inject a custom session (used by tests). When nil,
    ///   a session with generous timeouts is created — the digest endpoint
    ///   scrapes several arXiv list pages and can take 30s+, which exceeds
    ///   `URLSession.shared`'s default 60s request timeout on a slow network.
    public init(baseURL: URL, authToken: String? = nil, session: URLSession? = nil) {
        self.baseURL = baseURL
        self.authToken = authToken
        if let session {
            self.session = session
        } else {
            let config = URLSessionConfiguration.default
            config.timeoutIntervalForRequest = 120   // per-request inactivity
            config.timeoutIntervalForResource = 300  // whole-transfer ceiling
            #if !canImport(FoundationNetworking)
            config.waitsForConnectivity = true  // unavailable on Linux Foundation
            #endif
            self.session = URLSession(configuration: config)
        }
    }

    // MARK: - Core request

    private func request<T: Decodable>(
        _ method: String,
        _ path: String,
        query: [URLQueryItem]? = nil,
        body: (any Encodable)? = nil
    ) async throws -> T {
        var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false)
        components?.queryItems = query
        guard let url = components?.url else { throw APIError.invalidURL }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let authToken {
            request.setValue("Bearer \(authToken)", forHTTPHeaderField: "Authorization")
        }
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(body)
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.network(error)
        }

        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard (200..<300).contains(http.statusCode) else {
            let bodyText = String(data: data, encoding: .utf8) ?? ""
            throw APIError.http(http.statusCode, bodyText)
        }

        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw APIError.decoding(error)
        }
    }

    // MARK: - Endpoints

    public func health() async throws -> [String: String] {
        try await request("GET", "health")
    }

    /// Fetch the ranked digest. `refresh: true` bypasses the server's 1h cache
    /// (used by pull-to-refresh); the default served-from-cache path keeps
    /// repeat loads instant since the arXiv scrape is slow.
    public func fetchDigest(timeframe: String = "pastweek", topN: Int? = nil, feeds: [String]? = nil, refresh: Bool = false) async throws -> Digest {
        var query: [URLQueryItem] = [URLQueryItem(name: "timeframe", value: timeframe)]
        if let topN { query.append(URLQueryItem(name: "top_n", value: String(topN))) }
        if let feeds, !feeds.isEmpty {
            query.append(URLQueryItem(name: "feeds", value: feeds.joined(separator: ",")))
        }
        if refresh { query.append(URLQueryItem(name: "refresh", value: "true")) }
        return try await request("GET", "digest", query: query)
    }

    public func getConfig() async throws -> DigestConfig {
        struct ConfigResponse: Codable { let data: [String: JSONValue] }
        let resp: ConfigResponse = try await request("GET", "config")
        return DigestConfig(data: resp.data)
    }

    public func putConfig(_ config: DigestConfig) async throws -> DigestConfig {
        struct ConfigBody: Codable { let data: [String: JSONValue] }
        struct ConfigResponse: Codable { let data: [String: JSONValue] }
        let resp: ConfigResponse = try await request("PUT", "config", body: ConfigBody(data: config.data))
        return DigestConfig(data: resp.data)
    }

    public func listPresets() async throws -> [String] {
        try await request("GET", "config/presets")
    }

    public func mergePreset(named name: String) async throws -> DigestConfig {
        struct ConfigResponse: Codable { let data: [String: JSONValue] }
        let resp: ConfigResponse = try await request("POST", "config/presets/\(name)/merge")
        return DigestConfig(data: resp.data)
    }

    public func fetchLists() async throws -> [SavedList] {
        try await request("GET", "lists")
    }

    public func createList(name: String) async throws -> SavedList {
        struct Body: Codable { let name: String }
        return try await request("POST", "lists", body: Body(name: name))
    }

    public func addPaperToList(listID: Int, paper: Paper) async throws -> ListPaper {
        struct Body: Codable {
            let arxivId: String
            let title: String
            let authors: String
            let link: String
            enum CodingKeys: String, CodingKey {
                case arxivId = "arxiv_id"
                case title, authors, link
            }
        }
        let body = Body(arxivId: paper.id, title: paper.title, authors: paper.authors, link: paper.link)
        return try await request("POST", "lists/\(listID)/papers", body: body)
    }

    public func removePaperFromList(listID: Int, arxivId: String) async throws {
        let _: EmptyResponse = try await request("DELETE", "lists/\(listID)/papers/\(arxivId)")
    }

    public func recordFeedback(arxivId: String, action: String, signal: String = "keyword") async throws {
        struct Body: Codable {
            let arxivId: String
            let action: String
            let signal: String
            enum CodingKeys: String, CodingKey {
                case arxivId = "arxiv_id"
                case action, signal
            }
        }
        let _: EmptyResponse = try await request("POST", "feedback", body: Body(arxivId: arxivId, action: action, signal: signal))
    }

    /// Score a single paper by arXiv id (or URL). Returns the fetched paper,
    /// its per-signal breakdown, and — when the paper isn't in the current
    /// digest — an `absenceReason`. Backs the Score-a-paper tab.
    public func score(arxivId: String) async throws -> ScoreResult {
        struct Body: Codable {
            let arxivId: String
            enum CodingKeys: String, CodingKey { case arxivId = "arxiv_id" }
        }
        return try await request("POST", "score", body: Body(arxivId: arxivId))
    }

    public func zoteroStatus() async throws -> [String: Bool] {
        try await request("GET", "zotero/status")
    }

    public func saveToZotero(arxivId: String, mode: ZoteroMode, collectionKey: String? = nil) async throws -> ZoteroSaveResult {
        struct Body: Codable {
            let arxivId: String
            let mode: String
            let collectionKey: String?
            enum CodingKeys: String, CodingKey {
                case arxivId = "arxiv_id"
                case mode
                case collectionKey = "collection_key"
            }
        }
        return try await request("POST", "zotero/save",
                                 body: Body(arxivId: arxivId, mode: mode.rawValue, collectionKey: collectionKey))
    }
}

/// Used for endpoints that return an empty body (e.g. 204).
struct EmptyResponse: Codable {}
