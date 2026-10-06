import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

/// Demo mode (CONTEXT.md): an in-memory stand-in for the digest service,
/// serving the bundled sample digest so the app runs without a server (for
/// trying the UI and for screenshots).
///
/// The view logic is a port of the server's `digest_view` (ADR 0008): filter
/// replacements, keep the picked day, skip removed papers while ranking, stop
/// at top-N. Scores are the engine's, precomputed by
/// `ios/scripts/make_demo_fixture.py`; they do not react to config edits.
public final class DemoBackend: @unchecked Sendable {
    public static let shared = DemoBackend()

    private struct Fixture: Decodable {
        let config: [String: JSONValue]
        let pastweek: [Paper]
        let today: [Paper]
        let days: [String]
        let presets: [String: PresetFixture]
    }

    private struct PresetFixture: Decodable {
        let description: String
        let config: [String: JSONValue]
    }

    private let lock = NSLock()
    private let fixture: Fixture
    private var config: [String: JSONValue]
    private var removed: [String] = []

    public init() {
        // The fixture is generated and checked by a unit test; a decode
        // failure here is a build-time bug, not a runtime condition.
        fixture = try! JSONDecoder().decode(Fixture.self, from: Data(DemoFixture.json.utf8))
        config = fixture.config
    }

    /// Back to the bundled state (used by tests and "Reset demo").
    public func reset() {
        lock.withLock {
            config = fixture.config
            removed = []
        }
    }

    // MARK: - Routing

    public struct Response {
        public let status: Int
        public let body: Data
    }

    /// Handle one request. Paths and shapes match the FastAPI service.
    public func handle(method: String, url: URL, body: Data?) -> Response {
        let path = url.path.split(separator: "/").map(String.init)
        let query = Dictionary(
            (URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? [])
                .map { ($0.name, $0.value ?? "") },
            uniquingKeysWith: { _, last in last })
        let json = body.flatMap { try? JSONSerialization.jsonObject(with: $0) } as? [String: Any]

        return lock.withLock {
            switch (method, path) {
            case ("GET", ["health"]):
                return ok(["status": "ok", "mode": "demo"])
            case ("GET", ["digest"]):
                return digest(query)
            case ("POST", ["digest", "refresh"]):
                return digest(query)
            case ("GET", ["removed"]):
                return ok(removed)
            case ("POST", ["removed"]):
                if let id = json?["arxiv_id"] as? String, !removed.contains(id) { removed.append(id) }
                return Response(status: 204, body: Data())
            case ("POST", ["removed", "restore"]):
                let ids = Set(json?["arxiv_ids"] as? [String] ?? [])
                removed.removeAll { ids.contains($0) }
                return Response(status: 204, body: Data())
            case ("GET", ["config"]), ("GET", ["config", "defaults"]):
                // Demo defaults are the demo config (the engine's defaults
                // name real people; the demo stays invented).
                return configResponse(path.count == 1 ? config : fixture.config)
            case ("PUT", ["config"]):
                config = decodeConfig(body) ?? config
                return configResponse(config)
            case ("PATCH", ["config"]):
                config.merge(decodeConfig(body) ?? [:]) { _, new in new }
                return configResponse(config)
            case ("GET", ["config", "presets"]):
                return ok(fixture.presets.keys.sorted())
            case ("GET", ["config", "presets", "info"]):
                return ok(fixture.presets.keys.sorted().map {
                    ["name": $0, "description": fixture.presets[$0]!.description]
                })
            case ("POST", let p) where p.count == 4 && p[0] == "config" && p[1] == "presets":
                return preset(name: p[2], action: p[3], save: query["save"] != "false", body: body)
            case ("POST", ["score"]):
                return score(json ?? [:])
            case ("GET", ["zotero", "status"]):
                return ok(["web_api_available": true])
            case ("POST", ["zotero", "save"]):
                return ok(["ok": true, "mode": "web", "message": "Saved to Zotero (demo: nothing was written)."])
            default:
                return error(404, "Not found")
            }
        }
    }

    // MARK: - Handlers

    private var cfg: DigestConfig { DigestConfig(data: config) }

    private func fetched(_ timeframe: String) -> [Paper] {
        timeframe == "today" ? fixture.today : fixture.pastweek
    }

    struct View {
        var entries: [Paper]
        var removed: [Paper]
        var visible: [Paper]
        var filtered: [Paper]
        var day: String?
        var days: [String]
    }

    /// Port of the server's `digest_view`.
    func view(timeframe: String, day: String?, topN: Int) -> View {
        let all = fetched(timeframe)
        let days = fixture.days.filter { d in all.contains { $0.section == d } }
        let day = day.flatMap { days.contains($0) ? $0 : nil }
        let filtered = all.filter { p in
            if !cfg.includeReplacements && p.section.lowercased().contains("replacement") { return false }
            if let day, p.section != day { return false }
            return true
        }
        let ranked = filtered.sorted { ($0.score, $1.title) > ($1.score, $0.title) }
        var entries: [Paper] = [], removedEntries: [Paper] = []
        for (i, p) in ranked.enumerated() {
            if entries.count == max(topN, 1) { break }
            if removed.contains(p.id) {
                // Like the server: a removed entry keeps its full-ranking position.
                removedEntries.append(p.withRank(i + 1))
            } else {
                entries.append(p.withRank(entries.count + 1))
            }
        }
        let visible = filtered.filter { !removed.contains($0.id) }
        return View(entries: entries, removed: removedEntries, visible: visible,
                    filtered: filtered, day: day, days: days)
    }

    private func digest(_ q: [String: String]) -> Response {
        let timeframe = q["timeframe"] ?? cfg.timeframe
        guard timeframe == "today" || timeframe == "pastweek" else {
            return error(422, "timeframe must be 'today' or 'pastweek'")
        }
        let topN = q["top_n"].flatMap(Int.init) ?? cfg.topN
        let v = view(timeframe: timeframe, day: q["day"], topN: topN)
        let all = fetched(timeframe)
        let digest = Digest(
            papers: v.entries, totalPapers: v.visible.count, requestedTop: topN,
            fetchedPapers: all.count, hiddenByFilters: all.count - v.filtered.count,
            removed: v.removed, availableDays: v.days, day: v.day, timeframe: timeframe,
            feeds: cfg.defaultFeeds, notices: [],
            fetchedAt: ISO8601DateFormatter().string(from: Date().addingTimeInterval(-12 * 60)))
        return encode(digest)
    }

    private func score(_ body: [String: Any]) -> Response {
        let raw = (body["arxiv_id"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let id = ArxivID.parse(raw) ?? raw
        let timeframe = body["timeframe"] as? String ?? cfg.timeframe
        guard let p = (fixture.pastweek + fixture.today).first(where: { $0.id == id }) else {
            return encode(ScoreResult(paper: nil, breakdown: ScoreBreakdown(signals: [:], total: 0),
                                      absenceReason: "Paper not found"))
        }
        let scored = ScoredPaper(id: p.id, title: p.title, authors: p.authors, link: p.link,
                                 subjects: p.subjects, section: "", abstract: p.fullAbstract)
        let breakdown = p.breakdown ?? ScoreBreakdown(signals: [:], total: p.score)
        let topN = body["top_n"] as? Int ?? cfg.topN
        let v = view(timeframe: timeframe, day: body["day"] as? String, topN: topN)
        if let entry = v.entries.first(where: { $0.id == id }) {
            return encode(ScoreResult(paper: scored, breakdown: breakdown, rank: entry.rank))
        }
        let reason: String
        if !fetched(timeframe).contains(where: { $0.id == id }) {
            reason = "This paper was **not in the fetched set**. Deterministic check: it is outside the "
                + "\(timeframe == "today" ? "today" : "past-week") listing of your subscribed feeds."
        } else if removed.contains(id) {
            reason = v.removed.contains(where: { $0.id == id })
                ? "You **removed** this paper from the digest, so it is not ranked. Restore it from *Removed papers* in the **Papers** tab."
                : "You **removed** this paper, but the current filters or top-N hide it. Change the day or increase Top N until it appears under *Removed papers*, then restore it."
        } else if !fetched(timeframe).contains(where: {
            $0.id == id && (cfg.includeReplacements || !$0.section.lowercased().contains("replacement"))
        }) {
            reason = "This paper was fetched but is a **replacement** submission, which the digest hides. Turn on *Include replacement submissions* to rank it."
        } else if !v.visible.contains(where: { $0.id == id }) {
            reason = "This paper was fetched but is not from the picked day (\(v.day ?? "")). Pick *All days* to rank it."
        } else {
            reason = "This paper **was** fetched but ranked below your top-\(topN) cutoff."
        }
        return encode(ScoreResult(paper: scored, breakdown: breakdown, absenceReason: reason))
    }

    private func preset(name: String, action: String, save: Bool, body: Data?) -> Response {
        guard let preset = fixture.presets[name] else { return error(404, "Unknown preset '\(name)'") }
        var result: [String: JSONValue]
        switch action {
        case "load":
            result = preset.config
        case "merge":
            var base = DigestConfig(data: decodeConfig(body) ?? config)
            let p = DigestConfig(data: preset.config)
            for kw in p.coreKeywords { DigestConfig.append(kw, to: &base.coreKeywords) }
            for a in p.namedAuthors { DigestConfig.append(a, to: &base.namedAuthors) }
            for f in p.defaultFeeds { DigestConfig.append(f, to: &base.defaultFeeds) }
            base.feeds.merge(p.feeds) { _, new in new }
            base.feedWeights.merge(p.feedWeights) { _, new in new }
            result = base.data
        default:
            return error(404, "Not found")
        }
        if save { config = result }
        return configResponse(result)
    }

    // MARK: - Encoding helpers

    private func decodeConfig(_ body: Data?) -> [String: JSONValue]? {
        struct Body: Decodable { let data: [String: JSONValue] }
        return body.flatMap { try? JSONDecoder().decode(Body.self, from: $0) }?.data
    }

    private func configResponse(_ data: [String: JSONValue]) -> Response {
        struct Body: Encodable { let data: [String: JSONValue] }
        return encode(Body(data: data))
    }

    private func encode<T: Encodable>(_ value: T) -> Response {
        Response(status: 200, body: (try? JSONEncoder().encode(value)) ?? Data())
    }

    private func ok(_ value: Any) -> Response {
        Response(status: 200, body: (try? JSONSerialization.data(withJSONObject: value)) ?? Data())
    }

    private func error(_ status: Int, _ detail: String) -> Response {
        Response(status: status, body: (try? JSONSerialization.data(withJSONObject: ["detail": detail])) ?? Data())
    }
}

/// Routes every request of a session to `DemoBackend.shared`.
public final class DemoURLProtocol: URLProtocol, @unchecked Sendable {
    /// A session whose requests never leave the device.
    public static func makeSession() -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [DemoURLProtocol.self]
        return URLSession(configuration: config)
    }

    /// The base URL demo clients use (never contacted).
    public static let baseURL = URL(string: "https://demo.arxiv-digest.invalid")!

    override public class func canInit(with request: URLRequest) -> Bool { true }
    override public class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override public func startLoading() {
        guard let url = request.url else {
            client?.urlProtocol(self, didFailWithError: URLError(.badURL))
            return
        }
        let r = DemoBackend.shared.handle(method: request.httpMethod ?? "GET", url: url, body: request.bodyData)
        let response = HTTPURLResponse(url: url, statusCode: r.status, httpVersion: "HTTP/1.1",
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: r.body)
        client?.urlProtocolDidFinishLoading(self)
    }

    override public func stopLoading() {}
}

extension URLRequest {
    /// The body even when `URLSession` moved it into `httpBodyStream`.
    var bodyData: Data? {
        if let httpBody { return httpBody }
        guard let stream = httpBodyStream else { return nil }
        stream.open()
        defer { stream.close() }
        var data = Data()
        let size = 4096
        let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: size)
        defer { buffer.deallocate() }
        while stream.hasBytesAvailable {
            let read = stream.read(buffer, maxLength: size)
            if read <= 0 { break }
            data.append(buffer, count: read)
        }
        return data
    }
}
