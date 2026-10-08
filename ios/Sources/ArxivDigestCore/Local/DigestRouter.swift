import Foundation

/// Scored papers from one fetch, as the router's view consumes them.
public struct SourceFetch: Sendable {
    public var papers: [Paper]
    public var notices: [String]
    public var fetchedAt: Date

    public init(papers: [Paper], notices: [String] = [], fetchedAt: Date = Date()) {
        self.papers = papers
        self.notices = notices
        self.fetchedAt = fetchedAt
    }
}

/// A paper found for Score-a-paper, with the reason to show if it is not in
/// the fetched set.
public struct SourceLookup: Sendable {
    public var paper: ScoredPaper
    public var breakdown: ScoreBreakdown
    public var notFetchedReason: String
}

/// An HTTP error the router answers with (`{"detail": …}`), like the server's
/// `HTTPException`.
public struct RouterError: Error, Sendable {
    public let status: Int
    public let detail: String

    public init(_ status: Int, _ detail: String) {
        self.status = status
        self.detail = detail
    }
}

/// Where the router's papers come from: Demo's fixture or Standalone's live
/// arXiv fetch (ADR 0009).
public protocol DigestSource: Sendable {
    /// Reported by `/health` ("demo" / "standalone").
    var mode: String { get }
    /// Whether `/zotero/save` can write through the Web API.
    var zoteroWebAvailable: Bool { get }
    /// Papers for `timeframe` and `feeds`, scored with `config`.
    func fetch(timeframe: String, feeds: [String], config: DigestConfig, refresh: Bool) async throws -> SourceFetch
    /// The current fetch without fetching (the server's `peek_cache`).
    func cached(timeframe: String, feeds: [String], config: DigestConfig) async -> SourceFetch?
    /// The paper for Score-a-paper: from the current fetch, else looked up.
    func lookup(id: String, timeframe: String, feeds: [String], config: DigestConfig) async throws -> SourceLookup?
}

/// The digest service's endpoints answered in-process (Demo and Standalone
/// modes). Paths and JSON shapes match the FastAPI service; the view is a port
/// of the server's `digest_view` (ADR 0008).
public actor DigestRouter {
    public struct Preset: Codable, Sendable {
        public let description: String
        public let config: [String: JSONValue]

        public init(description: String, config: [String: JSONValue]) {
            self.description = description
            self.config = config
        }
    }

    public struct Response: Sendable {
        public let status: Int
        public let body: Data
    }

    /// Validates and fills a config like the server's `_hydrate` (nil: store as sent).
    public typealias Hydrate = @Sendable ([String: JSONValue]) throws -> [String: JSONValue]

    private let source: any DigestSource
    private let defaults: [String: JSONValue]
    private let presets: [String: Preset]
    private let hydrate: Hydrate?
    private let store: LocalStore?
    private var config: [String: JSONValue] { didSet { store?.save(config, to: "config.json") } }
    private var removed: [String] { didSet { store?.save(removed, to: "removed.json") } }

    public init(source: any DigestSource, config: [String: JSONValue], defaults: [String: JSONValue],
                presets: [String: Preset], removed: [String] = [], hydrate: Hydrate? = nil, store: LocalStore? = nil) {
        self.source = source
        self.config = config
        self.defaults = defaults
        self.presets = presets
        self.removed = removed
        self.hydrate = hydrate
        self.store = store
    }

    private func hydrated(_ data: [String: JSONValue]) throws -> [String: JSONValue] {
        guard let hydrate else { return data }
        do {
            return try hydrate(data)
        } catch {
            throw RouterError(422, "Invalid config: \(error)")
        }
    }

    // MARK: - Routing

    /// Handle one request. Paths and shapes match the FastAPI service.
    public func handle(method: String, url: URL, body: Data?) async -> Response {
        let path = url.path.split(separator: "/").map(String.init)
        let query = Dictionary(
            (URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? [])
                .map { ($0.name, $0.value ?? "") },
            uniquingKeysWith: { _, last in last })
        let json = body.flatMap { try? JSONSerialization.jsonObject(with: $0) } as? [String: Any]

        do {
            switch (method, path) {
            case ("GET", ["health"]):
                return ok(["status": "ok", "mode": source.mode])
            case ("GET", ["digest"]):
                return try await digest(query, refresh: query["refresh"] == "true")
            case ("POST", ["digest", "refresh"]):
                return try await digest(query, refresh: true)
            case ("GET", ["removed"]):
                return ok(removed)
            case ("POST", ["removed"]):
                if let id = json?["arxiv_id"] as? String, !removed.contains(id) { removed.append(id) }
                return Response(status: 204, body: Data())
            case ("POST", ["removed", "restore"]):
                let ids = Set(json?["arxiv_ids"] as? [String] ?? [])
                removed.removeAll { ids.contains($0) }
                return Response(status: 204, body: Data())
            case ("GET", ["config"]):
                return configResponse(config)
            case ("GET", ["config", "defaults"]):
                return configResponse(defaults)
            case ("PUT", ["config"]):
                config = try hydrated(decodeConfig(body) ?? config)
                return configResponse(config)
            case ("PATCH", ["config"]):
                config = try hydrated(config.merging(decodeConfig(body) ?? [:]) { _, new in new })
                return configResponse(config)
            case ("GET", ["config", "presets"]):
                return ok(presets.keys.sorted())
            case ("GET", ["config", "presets", "info"]):
                return ok(presets.keys.sorted().map { ["name": $0, "description": presets[$0]!.description] })
            case ("POST", let p) where p.count == 4 && p[0] == "config" && p[1] == "presets":
                return try preset(name: p[2], action: p[3], save: query["save"] != "false", body: body)
            case ("POST", ["score"]):
                return try await score(json ?? [:])
            case ("GET", ["zotero", "status"]):
                return ok(["web_api_available": source.zoteroWebAvailable])
            case ("POST", ["zotero", "save"]):
                guard source.zoteroWebAvailable else {
                    throw RouterError(503, "Zotero Web API not configured. Set ZOTERO_API_KEY and ZOTERO_LIBRARY_ID.")
                }
                return ok(["ok": true, "mode": "web", "message": "Saved to Zotero (demo: nothing was written)."])
            default:
                throw RouterError(404, "Not found")
            }
        } catch let e as RouterError {
            return error(e.status, e.detail)
        } catch {
            return self.error(500, "\(error)")
        }
    }

    // MARK: - View

    private var cfg: DigestConfig { DigestConfig(data: config) }

    /// The server's `resolve_feed_names`: requested feeds (or the subscribed
    /// ones), known names or URLs only.
    private func feedNames(_ requested: String?) -> [String] {
        let asked = (requested ?? "").split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        let names = asked.isEmpty ? cfg.defaultFeeds : asked
        let known = cfg.feeds
        return names.filter { known[$0] != nil || $0.hasPrefix("http://") || $0.hasPrefix("https://") }
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
    func view(_ all: [Paper], day: String?, topN: Int) -> View {
        let days = Self.availableDayLabels(all.map(\.section))
        let day = day.flatMap { days.contains($0) ? $0 : nil }
        let includeReplacements = cfg.includeReplacements
        let filtered = all.filter { p in
            if !includeReplacements && Self.isReplacement(p.section) { return false }
            if let day, Self.dayLabel(p.section) != day { return false }
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

    static func isReplacement(_ section: String) -> Bool { section.lowercased().contains("replacement") }

    private static let dayLabelRegex = try! NSRegularExpression(pattern: "^[A-Z][a-z]{2}, \\d{1,2} [A-Z][a-z]{2} \\d{4}")

    /// The engine's `section_day_label`: "Fri, 19 Jun 2026 (showing …)" → "Fri, 19 Jun 2026".
    static func dayLabel(_ section: String) -> String? {
        guard let m = dayLabelRegex.firstMatch(in: section, range: NSRange(section.startIndex..., in: section)),
              let r = Range(m.range, in: section) else { return nil }
        return String(section[r])
    }

    /// The engine's `available_day_labels`: distinct day labels, chronological.
    static func availableDayLabels(_ sections: [String]) -> [String] {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(identifier: "UTC")
        f.dateFormat = "EEE, d MMM yyyy"
        let labels = Set(sections.compactMap(dayLabel))
        return labels.sorted { (f.date(from: $0) ?? .distantFuture, $0) < (f.date(from: $1) ?? .distantFuture, $1) }
    }

    // MARK: - Handlers

    private func digest(_ q: [String: String], refresh: Bool) async throws -> Response {
        let cfg = self.cfg
        let timeframe = q["timeframe"] ?? cfg.timeframe
        guard timeframe == "today" || timeframe == "pastweek" else {
            throw RouterError(422, "timeframe must be 'today' or 'pastweek'")
        }
        let topN = q["top_n"].flatMap(Int.init) ?? cfg.topN
        let names = feedNames(q["feeds"])
        let fetch = try await source.fetch(timeframe: timeframe, feeds: names, config: cfg, refresh: refresh)
        let v = view(fetch.papers, day: q["day"], topN: topN)
        let all = fetch.papers
        let digest = Digest(
            papers: v.entries, totalPapers: v.visible.count, requestedTop: topN,
            fetchedPapers: all.count, hiddenByFilters: all.count - v.filtered.count,
            removed: v.removed, availableDays: v.days, day: v.day, timeframe: timeframe,
            feeds: names, notices: fetch.notices,
            fetchedAt: ISO8601DateFormatter().string(from: fetch.fetchedAt))
        return encode(digest)
    }

    private func score(_ body: [String: Any]) async throws -> Response {
        let cfg = self.cfg
        let raw = (body["arxiv_id"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let id = ArxivID.parse(raw) ?? raw
        let timeframe = body["timeframe"] as? String ?? cfg.timeframe
        let topN = body["top_n"] as? Int ?? cfg.topN
        let names = feedNames(nil)
        guard let found = try await source.lookup(id: id, timeframe: timeframe, feeds: names, config: cfg) else {
            return encode(ScoreResult(paper: nil, breakdown: ScoreBreakdown(signals: [:], total: 0),
                                      absenceReason: "Paper not found"))
        }
        let (scored, breakdown) = (found.paper, found.breakdown)
        guard let fetched = await source.cached(timeframe: timeframe, feeds: names, config: cfg)?.papers else {
            return encode(ScoreResult(paper: scored, breakdown: breakdown,
                                      absenceReason: "Load the digest first to compare this paper against it."))
        }
        let v = view(fetched, day: body["day"] as? String, topN: topN)
        if let entry = v.entries.first(where: { $0.id == scored.id }) {
            return encode(ScoreResult(paper: scored, breakdown: breakdown, rank: entry.rank))
        }
        let id2 = scored.id
        let reason: String
        if !fetched.contains(where: { $0.id == id2 }) {
            reason = found.notFetchedReason
        } else if removed.contains(id2) {
            reason = v.removed.contains(where: { $0.id == id2 })
                ? "You **removed** this paper from the digest, so it is not ranked. Restore it from *Removed papers* in the **Papers** tab."
                : "You **removed** this paper, but the current filters or top-N hide it. Change the day or increase Top N until it appears under *Removed papers*, then restore it."
        } else if !fetched.contains(where: {
            $0.id == id2 && (cfg.includeReplacements || !Self.isReplacement($0.section))
        }) {
            reason = "This paper was fetched but is a **replacement** submission, which the digest hides. Turn on *Include replacement submissions* to rank it."
        } else if !v.visible.contains(where: { $0.id == id2 }) {
            reason = "This paper was fetched but is not from the picked day (\(v.day ?? "")). Pick *All days* to rank it."
        } else {
            reason = "This paper **was** fetched but ranked below your top-\(topN) cutoff."
        }
        return encode(ScoreResult(paper: scored, breakdown: breakdown, absenceReason: reason))
    }

    private func preset(name: String, action: String, save: Bool, body: Data?) throws -> Response {
        guard let preset = presets[name] else { return error(404, "Unknown preset '\(name)'") }
        let result: [String: JSONValue]
        switch action {
        case "load":
            result = preset.config
        case "merge":
            result = EngineConfig.merge(try decodeConfig(body).map(hydrated) ?? config, preset: preset.config)
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
