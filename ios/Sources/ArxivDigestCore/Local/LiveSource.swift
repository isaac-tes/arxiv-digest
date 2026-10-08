import Foundation

/// Standalone mode's papers: fetched from arXiv and scored on the device with
/// the current config on every request, so config edits re-rank (ADR 0009).
/// Raw fetches are cached for an hour like the server's `cached_fetch`.
public actor LiveSource: DigestSource {
    /// Raw papers of one fetch, before scoring.
    public struct RawFetch: Codable, Sendable {
        public var papers: [RawPaper]
        public var notices: [String]
        public var fetchedAt: Date

        public init(papers: [RawPaper], notices: [String] = [], fetchedAt: Date = Date()) {
            self.papers = papers
            self.notices = notices
            self.fetchedAt = fetchedAt
        }
    }

    /// Fetch `timeframe` ("today" / "pastweek") for these feed names.
    public typealias Fetcher = @Sendable (_ timeframe: String, _ feeds: [String], _ config: DigestConfig) async throws -> RawFetch
    /// One paper by id with its `published` timestamp, or nil if arXiv has none.
    public typealias PaperFetcher = @Sendable (_ id: String) async throws -> (paper: RawPaper, published: String)?

    static let ttl: TimeInterval = 60 * 60

    public nonisolated var mode: String { "standalone" }
    // No Zotero key on the device; Share to Zotero covers saving.
    public nonisolated var zoteroWebAvailable: Bool { false }

    private let fetcher: Fetcher
    private let fetchPaper: PaperFetcher
    private let now: @Sendable () -> Date
    private let store: LocalStore?
    private var cache: [String: RawFetch] { didSet { store?.save(cache, to: "fetch-cache.json") } }

    /// Distinguishes cached "today" fetches made different ways (`TodaySource`).
    private let todayTag: String

    public init(fetcher: @escaping Fetcher, fetchPaper: @escaping PaperFetcher = { _ in nil },
                now: @escaping @Sendable () -> Date = Date.init, store: LocalStore? = nil, todayTag: String = "") {
        self.todayTag = todayTag
        self.fetcher = fetcher
        self.fetchPaper = fetchPaper
        self.now = now
        self.store = store
        cache = store?.load([String: RawFetch].self, from: "fetch-cache.json") ?? [:]
    }

    private func cacheKey(_ timeframe: String, _ feeds: [String]) -> String {
        (timeframe == "today" ? "today-\(todayTag)" : timeframe) + "|" + feeds.joined(separator: ",")
    }

    private func fresh(_ timeframe: String, _ feeds: [String]) -> RawFetch? {
        guard let hit = cache[cacheKey(timeframe, feeds)], now().timeIntervalSince(hit.fetchedAt) < Self.ttl else { return nil }
        return hit
    }

    public func fetch(timeframe: String, feeds: [String], config: DigestConfig, refresh: Bool) async throws -> SourceFetch {
        var raw = refresh ? nil : fresh(timeframe, feeds)
        if raw == nil {
            do {
                raw = try await fetcher(timeframe, feeds, config)
            } catch let e as RouterError {
                throw e
            } catch {
                throw RouterError(502, "arXiv fetch failed (\(Self.errorName(error))). arXiv may be slow or down; try again in a moment.")
            }
            // Never cache an empty fetch (nothing subscribed / arXiv hiccup).
            if let raw, !raw.papers.isEmpty { cache[cacheKey(timeframe, feeds)] = raw }
        }
        return Self.scored(raw!, config: config)
    }

    public func cached(timeframe: String, feeds: [String], config: DigestConfig) async -> SourceFetch? {
        guard let raw = fresh(timeframe, feeds) else { return nil }
        return Self.scored(raw, config: config)
    }

    /// Like the server's `/score`: a paper in the cached fetch is scored from
    /// it (works while arXiv rate-limits); anything else is fetched by id.
    public func lookup(id: String, timeframe: String, feeds: [String], config: DigestConfig) async throws -> SourceLookup? {
        let fetched = fresh(timeframe, feeds)?.papers ?? []
        var reason = ""
        var paper = fetched.first(where: { $0.id == id })
        if paper == nil {
            let found: (paper: RawPaper, published: String)?
            do {
                found = try await fetchPaper(id)
            } catch {
                guard error is URLError || error is ArxivFetcher.HTTPStatusError else {
                    return nil  // malformed feed etc. -> not found, like the server
                }
                throw RouterError(502, "Could not reach arXiv (\(Self.errorName(error))); it may be rate-limiting. Try again in a moment.")
            }
            guard let found else { return nil }
            paper = found.paper
            reason = Self.notFetchedReason(
                published: found.published,
                categories: found.paper.subjects.components(separatedBy: ", ").filter { !$0.isEmpty },
                fetchedSections: fetched.map(\.section), feedNames: config.feeds.keys.sorted())
        }
        let p = paper!
        return SourceLookup(
            paper: ScoredPaper(id: p.id, title: p.title, authors: p.authors, link: p.link,
                               subjects: p.subjects, section: p.section, abstract: p.abstract),
            breakdown: Scorer.explain(paper: p, config: config),
            notFetchedReason: reason)
    }

    /// The error's kind for messages: `type(of:)` reads `NSError` for a
    /// bridged `URLError` on Apple platforms.
    static func errorName(_ error: Error) -> String {
        switch error {
        case is URLError: return "URLError"
        case is ArxivFetcher.HTTPStatusError: return "HTTPError"
        default: return String(describing: type(of: error))
        }
    }

    /// Port of the server's `score._not_fetched_reason`.
    /// ponytail: `feedNames` arrive sorted; Python lists them in config order.
    static func notFetchedReason(published: String, categories: [String], fetchedSections: [String],
                                 feedNames: [String]) -> String {
        let pubDate = published.isEmpty ? nil : String(published.prefix(10))
        let label = DateFormatter(), iso = DateFormatter()
        for f in [label, iso] {
            f.locale = Locale(identifier: "en_US_POSIX")
            f.timeZone = TimeZone(identifier: "UTC")
        }
        label.dateFormat = "EEE, d MMM yyyy"
        iso.dateFormat = "yyyy-MM-dd"
        let dayDates = Set(DigestRouter.availableDayLabels(fetchedSections).compactMap { label.date(from: $0) }
            .map { iso.string(from: $0) })

        let feeds = feedNames.map { $0.lowercased() }
        let matched = categories.filter { c in feeds.contains { c.lowercased().hasPrefix($0) } }

        var reasons: [String] = []
        if let pubDate, !dayDates.isEmpty {
            if !dayDates.contains(pubDate) {
                reasons.append("it was submitted on **\(pubDate)**, but the fetched feed only covers **\(dayDates.sorted().joined(separator: ", "))**")
            } else {
                reasons.append("it was submitted on **\(pubDate)**, which IS within the fetched days — so it was likely not yet listed in the feed pages when you fetched")
            }
        } else if let pubDate {
            reasons.append("it was submitted on **\(pubDate)**")
        }
        if !matched.isEmpty {
            reasons.append("its categories (**\(matched.joined(separator: ", "))**) overlap your subscribed feeds")
        } else {
            let cats = categories.isEmpty ? "unknown" : categories.joined(separator: ", ")
            let subscribed = feedNames.isEmpty ? "none" : feedNames.joined(separator: ", ")
            reasons.append("its categories (**\(cats)**) are **not among your subscribed feeds** (\(subscribed))")
        }
        return "This paper was **not in the fetched set**. Deterministic check: " + reasons.joined(separator: "; ") + "."
    }

    static func scored(_ raw: RawFetch, config: DigestConfig) -> SourceFetch {
        SourceFetch(papers: raw.papers.map { entry($0, config: config) }, notices: raw.notices, fetchedAt: raw.fetchedAt)
    }

    /// A digest entry like the engine's `build_ranked_entries` + the server's `_paper_out`.
    static func entry(_ p: RawPaper, config: DigestConfig) -> Paper {
        func clean(_ s: String) -> String { s.trimmingCharacters(in: .whitespacesAndNewlines) }
        let b = Scorer.explain(paper: p, config: config)
        return Paper(
            rank: 0, id: p.id,
            title: clean(p.title).isEmpty ? "(Untitled)" : clean(p.title),
            authors: clean(p.authors).isEmpty ? "(No authors listed)" : clean(p.authors),
            link: clean(p.link), subjects: clean(p.subjects), section: clean(p.section),
            summary: Scorer.summarize(p.abstract), score: b.total, abstract: p.abstract, breakdown: b)
    }
}

/// Standalone mode's router, shared by every `LocalURLProtocol` session.
public final class StandaloneBackend: @unchecked Sendable {
    public static let shared = StandaloneBackend()

    private let lock = NSLock()
    private var todaySource = TodaySource.listing
    private lazy var current = Self.makeRouter(store: .standard, today: todaySource)

    public var router: DigestRouter { lock.withLock { current } }

    /// Switch how "today" is fetched (S7 comparison). Rebuilds the router from
    /// disk, so config, removals and cached fetches carry over.
    public func setTodaySource(_ source: TodaySource) {
        lock.withLock {
            guard source != todaySource else { return }
            todaySource = source
            current = Self.makeRouter(store: .standard, today: source)
        }
    }

    /// The live router: the past week from the export API, today per `today`.
    static func makeRouter(store: LocalStore, today: TodaySource) -> DigestRouter {
        makeRouter(store: store, todayTag: today.rawValue, fetcher: { timeframe, feeds, config in
            let fetcher = ArxivFetcher()
            guard timeframe == "today" else { return try await fetcher.fetchPastweek(feeds) }
            switch today {
            case .listing: return try await fetcher.fetchTodayListing(feeds, config: config)
            case .api: return try await fetcher.fetchTodayAPI(feeds)
            }
        }, fetchPaper: { id in try await ArxivFetcher().fetchPaper(id) })
    }

    /// A router over `store`: the saved config (first run: the engine's
    /// defaults), removed papers and fetch cache, with the engine's presets.
    public static func makeRouter(store: LocalStore, todayTag: String = "", fetcher: @escaping LiveSource.Fetcher,
                                  fetchPaper: @escaping LiveSource.PaperFetcher = { _ in nil }) -> DigestRouter {
        DigestRouter(
            source: LiveSource(fetcher: fetcher, fetchPaper: fetchPaper, store: store, todayTag: todayTag),
            config: store.load([String: JSONValue].self, from: "config.json") ?? EngineConfig.defaults,
            defaults: EngineConfig.defaults, presets: EngineConfig.presets,
            removed: store.load([String].self, from: "removed.json") ?? [],
            hydrate: EngineConfig.hydrate, store: store)
    }

    /// Replace the router (tests inject a fetcher this way).
    public func install(_ router: DigestRouter) {
        lock.withLock { current = router }
    }
}

/// Standalone mode's requests → `StandaloneBackend.shared`.
public final class LocalURLProtocol: RouterURLProtocol, @unchecked Sendable {
    override class var router: DigestRouter { StandaloneBackend.shared.router }
    override public class var baseURL: URL { URL(string: "https://device.arxiv-digest.invalid")! }
}
