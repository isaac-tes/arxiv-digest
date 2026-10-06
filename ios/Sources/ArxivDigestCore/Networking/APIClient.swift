import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

/// Errors thrown by the API client.
public enum APIError: Error, LocalizedError, Sendable, Equatable {
    case invalidURL
    case invalidResponse
    /// Non-2xx status with the server's message (FastAPI's `detail` when present).
    case http(Int, String)
    case decoding(String)
    case network(String)

    public var errorDescription: String? {
        switch self {
        case .invalidURL: return "Invalid server URL."
        case .invalidResponse: return "Invalid response from server."
        case .http(let code, let message):
            return message.isEmpty ? "Server error (\(code))." : message
        case .decoding(let what): return "Could not read the server response (\(what))."
        case .network(let message): return "Can't reach the digest server: \(message)"
        }
    }

    /// FastAPI error bodies look like `{"detail": "..."}` (or a list of
    /// validation errors). Fall back to the raw body, trimmed.
    public static func message(fromBody data: Data) -> String {
        if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            if let s = obj["detail"] as? String { return s }
            if let list = obj["detail"] as? [[String: Any]] {
                return list.compactMap { $0["msg"] as? String }.joined(separator: "; ")
            }
        }
        let text = String(data: data, encoding: .utf8) ?? ""
        return String(text.trimmingCharacters(in: .whitespacesAndNewlines).prefix(300))
    }
}

/// A minimal async/await HTTP client for the digest service.
///
/// Uses `URLSession` + `Codable` (no third-party dependency). The FastAPI
/// OpenAPI spec is the contract this client implements.
public struct APIClient: Sendable {
    public let baseURL: URL
    public var authToken: String?
    private let session: URLSession

    /// - Parameter session: inject a custom session (tests, demo mode). When
    ///   nil, a session with generous timeouts is created: a cold past-week
    ///   fetch queries the arXiv export API per category with rate-limit pauses.
    public init(baseURL: URL, authToken: String? = nil, session: URLSession? = nil) {
        self.baseURL = baseURL
        self.authToken = authToken
        if let session {
            self.session = session
        } else {
            let config = URLSessionConfiguration.default
            config.timeoutIntervalForRequest = 180   // per-request inactivity
            config.timeoutIntervalForResource = 300  // whole-transfer ceiling
            #if !canImport(FoundationNetworking)
            config.waitsForConnectivity = true  // unavailable on Linux Foundation
            #endif
            self.session = URLSession(configuration: config)
        }
    }

    // MARK: - Core request

    private func makeRequest(
        _ method: String, _ path: String, query: [URLQueryItem]?, body: (any Encodable)?
    ) throws -> URLRequest {
        var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false)
        if let query, !query.isEmpty { components?.queryItems = query }
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
        return request
    }

    private func send(
        _ method: String, _ path: String, query: [URLQueryItem]? = nil, body: (any Encodable)? = nil
    ) async throws -> Data {
        let request = try makeRequest(method, path, query: query, body: body)
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.network(error.localizedDescription)
        }
        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard (200..<300).contains(http.statusCode) else {
            throw APIError.http(http.statusCode, APIError.message(fromBody: data))
        }
        return data
    }

    private func request<T: Decodable>(
        _ method: String, _ path: String, query: [URLQueryItem]? = nil, body: (any Encodable)? = nil
    ) async throws -> T {
        let data = try await send(method, path, query: query, body: body)
        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw APIError.decoding(String(describing: T.self))
        }
    }

    /// For endpoints that answer 204 No Content.
    private func requestNoContent(
        _ method: String, _ path: String, query: [URLQueryItem]? = nil, body: (any Encodable)? = nil
    ) async throws {
        _ = try await send(method, path, query: query, body: body)
    }

    private struct ConfigBody: Codable { let data: [String: JSONValue] }

    // MARK: - Health

    public func health() async throws -> [String: String] {
        try await request("GET", "health")
    }

    // MARK: - Digest

    /// The ranked digest view (ADR 0008). `nil` parameters fall back to the
    /// saved config on the server; `day` restricts to one announcement day;
    /// `refresh: true` bypasses the server's 1 h fetch cache.
    public func fetchDigest(
        timeframe: String? = nil,
        topN: Int? = nil,
        day: String? = nil,
        feeds: [String]? = nil,
        refresh: Bool = false
    ) async throws -> Digest {
        try await request("GET", "digest", query: Self.digestQuery(
            timeframe: timeframe, topN: topN, day: day, feeds: feeds, refresh: refresh))
    }

    static func digestQuery(
        timeframe: String?, topN: Int?, day: String?, feeds: [String]?, refresh: Bool
    ) -> [URLQueryItem] {
        var q: [URLQueryItem] = []
        if let timeframe { q.append(URLQueryItem(name: "timeframe", value: timeframe)) }
        if let topN { q.append(URLQueryItem(name: "top_n", value: String(topN))) }
        if let day { q.append(URLQueryItem(name: "day", value: day)) }
        if let feeds, !feeds.isEmpty { q.append(URLQueryItem(name: "feeds", value: feeds.joined(separator: ","))) }
        if refresh { q.append(URLQueryItem(name: "refresh", value: "true")) }
        return q
    }

    // MARK: - Removed papers

    public func removedPapers() async throws -> [String] {
        try await request("GET", "removed")
    }

    public func removePaper(arxivId: String) async throws {
        struct Body: Codable { let arxiv_id: String }
        try await requestNoContent("POST", "removed", body: Body(arxiv_id: arxivId))
    }

    public func restorePapers(arxivIds: [String]) async throws {
        struct Body: Codable { let arxiv_ids: [String] }
        try await requestNoContent("POST", "removed/restore", body: Body(arxiv_ids: arxivIds))
    }

    // MARK: - Config

    public func getConfig() async throws -> DigestConfig {
        let resp: ConfigBody = try await request("GET", "config")
        return DigestConfig(data: resp.data)
    }

    public func putConfig(_ config: DigestConfig) async throws -> DigestConfig {
        let resp: ConfigBody = try await request("PUT", "config", body: ConfigBody(data: config.data))
        return DigestConfig(data: resp.data)
    }

    /// Merge only the given fields into the stored config.
    public func patchConfig(_ fields: [String: JSONValue]) async throws -> DigestConfig {
        let resp: ConfigBody = try await request("PATCH", "config", body: ConfigBody(data: fields))
        return DigestConfig(data: resp.data)
    }

    /// The engine's built-in defaults (for "Reset to defaults").
    public func defaultConfig() async throws -> DigestConfig {
        let resp: ConfigBody = try await request("GET", "config/defaults")
        return DigestConfig(data: resp.data)
    }

    public func listPresets() async throws -> [String] {
        try await request("GET", "config/presets")
    }

    public func presetInfo() async throws -> [PresetInfo] {
        try await request("GET", "config/presets/info")
    }

    /// GUI "Add preset": union preset `name` into `base` (the working config).
    /// With `save: false` the server stores nothing.
    public func mergePreset(named name: String, into base: DigestConfig? = nil, save: Bool = true) async throws -> DigestConfig {
        let resp: ConfigBody = try await request(
            "POST", "config/presets/\(name)/merge",
            query: [URLQueryItem(name: "save", value: save ? "true" : "false")],
            body: base.map { ConfigBody(data: $0.data) })
        return DigestConfig(data: resp.data)
    }

    /// GUI "Load preset": the preset's config (defaults elsewhere).
    public func loadPreset(named name: String, save: Bool = true) async throws -> DigestConfig {
        let resp: ConfigBody = try await request(
            "POST", "config/presets/\(name)/load",
            query: [URLQueryItem(name: "save", value: save ? "true" : "false")])
        return DigestConfig(data: resp.data)
    }

    // MARK: - Lists / feedback (server endpoints kept; not used by the current UI)

    public func fetchLists() async throws -> [SavedList] {
        try await request("GET", "lists")
    }

    public func createList(name: String) async throws -> SavedList {
        struct Body: Codable { let name: String }
        return try await request("POST", "lists", body: Body(name: name))
    }

    public func addPaperToList(listID: Int, paper: Paper) async throws -> ListPaper {
        struct Body: Codable {
            let arxiv_id: String
            let title: String
            let authors: String
            let link: String
        }
        return try await request("POST", "lists/\(listID)/papers",
                                 body: Body(arxiv_id: paper.id, title: paper.title, authors: paper.authors, link: paper.link))
    }

    public func removePaperFromList(listID: Int, arxivId: String) async throws {
        try await requestNoContent("DELETE", "lists/\(listID)/papers/\(arxivId)")
    }

    public func recordFeedback(arxivId: String, action: String, signal: String = "keyword") async throws {
        struct Body: Codable { let arxiv_id: String; let action: String; let signal: String }
        try await requestNoContent("POST", "feedback", body: Body(arxiv_id: arxivId, action: action, signal: signal))
    }

    // MARK: - Score a paper

    /// Score one paper (id or URL) and place it against the digest view given
    /// by `timeframe` / `topN` / `day` (the Papers tab's current view).
    public func score(arxivId: String, timeframe: String? = nil, topN: Int? = nil, day: String? = nil) async throws -> ScoreResult {
        struct Body: Codable {
            let arxiv_id: String
            let timeframe: String?
            let top_n: Int?
            let day: String?
        }
        return try await request("POST", "score",
                                 body: Body(arxiv_id: arxivId, timeframe: timeframe, top_n: topN, day: day))
    }

    // MARK: - Zotero

    public func zoteroStatus() async throws -> [String: Bool] {
        try await request("GET", "zotero/status")
    }

    public func saveToZotero(arxivId: String, mode: ZoteroMode = .web, collectionKey: String? = nil) async throws -> ZoteroSaveResult {
        struct Body: Codable {
            let arxiv_id: String
            let mode: String
            let collection_key: String?
        }
        return try await request("POST", "zotero/save",
                                 body: Body(arxiv_id: arxivId, mode: mode.rawValue, collection_key: collectionKey))
    }
}
