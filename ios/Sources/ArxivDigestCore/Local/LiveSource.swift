import Foundation

/// Standalone mode's papers: fetched from arXiv and scored on the device with
/// the current config on every request, so config edits re-rank (ADR 0009).
///
/// Raw fetches are cached on the device until arXiv announces new papers, so
/// opening the app again does not refetch. Past the next announcement, a cached
/// past week is topped up: only the last few days are asked for, merged in, and
/// papers that left the seven-day window are dropped.
public actor LiveSource: DigestSource {
    /// Raw papers of one fetch, before scoring.
    public struct RawFetch: Codable, Sendable {
        public var papers: [RawPaper]
        public var notices: [String]
        public var fetchedAt: Date
        /// Submission time per paper id (past-week fetches), to keep the window exact when topping up.
        public var submitted: [String: Date]?

        public init(papers: [RawPaper], notices: [String] = [], fetchedAt: Date = Date(),
                    submitted: [String: Date]? = nil) {
            self.papers = papers
            self.notices = notices
            self.fetchedAt = fetchedAt
            self.submitted = submitted
        }
    }

    /// Fetch `timeframe` ("today" / "pastweek") for these feed names.
    public typealias Fetcher = @Sendable (_ timeframe: String, _ feeds: [String], _ config: DigestConfig) async throws -> RawFetch
    /// The past week's papers submitted since `since` (to top up a cached week).
    public typealias Updater = @Sendable (_ feeds: [String], _ since: Date) async throws -> RawFetch
    /// One paper by id with its `published` timestamp, or nil if arXiv has none.
    public typealias PaperFetcher = @Sendable (_ id: String) async throws -> (paper: RawPaper, published: String)?

    /// How far back a top-up asks: arXiv announces a paper up to ~3 days after
    /// submission (Friday afternoon → Monday evening), so a day more than that.
    static let announcementLag: TimeInterval = 4 * 86_400
    static let week: TimeInterval = 7 * 86_400

    public nonisolated var mode: String { "standalone" }
    // No Zotero key on the device; Share to Zotero covers saving.
    public nonisolated var zoteroWebAvailable: Bool { false }

    private let fetcher: Fetcher
    private let update: Updater?
    private let fetchPaper: PaperFetcher
    private let now: @Sendable () -> Date
    private let store: LocalStore?
    private var cache: [String: RawFetch] { didSet { store?.save(cache, to: "fetch-cache.json") } }

    public init(fetcher: @escaping Fetcher, update: Updater? = nil, fetchPaper: @escaping PaperFetcher = { _ in nil },
                now: @escaping @Sendable () -> Date = Date.init, store: LocalStore? = nil) {
        self.fetcher = fetcher
        self.update = update
        self.fetchPaper = fetchPaper
        self.now = now
        self.store = store
        cache = store?.load([String: RawFetch].self, from: "fetch-cache.json") ?? [:]
    }

    private func cacheKey(_ timeframe: String, _ feeds: [String]) -> String {
        timeframe + "|" + feeds.joined(separator: ",")
    }

    /// The cached fetch, while arXiv has announced nothing new since it.
    private func fresh(_ timeframe: String, _ feeds: [String]) -> RawFetch? {
        guard let hit = cache[cacheKey(timeframe, feeds)], now() < Self.nextAnnouncement(after: hit.fetchedAt) else {
            return nil
        }
        return hit
    }

    /// arXiv's next announcement after `date`: 20:00 US Eastern, Sunday to Thursday.
    /// ponytail: holidays aren't modelled; a top-up on a skipped day just finds nothing new.
    static func nextAnnouncement(after date: Date) -> Date {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "America/New_York")!
        var day = cal.startOfDay(for: date)
        for _ in 0..<8 {
            let weekday = cal.component(.weekday, from: day)  // 1 = Sunday
            if (1...5).contains(weekday), let at = cal.date(bySettingHour: 20, minute: 0, second: 0, of: day), at > date {
                return at
            }
            day = cal.date(byAdding: .day, value: 1, to: day)!
        }
        return date.addingTimeInterval(86_400)
    }

    /// `old` topped up with `delta`: newer copies replace older ones, and papers
    /// submitted more than a week before `delta` was fetched leave.
    static func merged(_ old: RawFetch, _ delta: RawFetch) -> RawFetch {
        var submitted = old.submitted ?? [:]
        submitted.merge(delta.submitted ?? [:]) { _, new in new }
        let cutoff = delta.fetchedAt.addingTimeInterval(-week)
        let fresh = Set(delta.papers.map(\.id))
        let kept = old.papers.filter { !fresh.contains($0.id) && (submitted[$0.id].map { $0 >= cutoff } ?? false) }
        let papers = delta.papers + kept
        let ids = Set(papers.map(\.id))
        return RawFetch(papers: papers, notices: delta.notices, fetchedAt: delta.fetchedAt,
                        submitted: submitted.filter { ids.contains($0.key) })
    }

    public func fetch(timeframe: String, feeds: [String], config: DigestConfig, refresh: Bool) async throws -> SourceFetch {
        let key = cacheKey(timeframe, feeds)
        var raw = refresh ? nil : fresh(timeframe, feeds)
        if raw == nil {
            do {
                // Top up a complete cached week that is less than a week old (also on a pull to
                // refresh: the latest days are what can have changed); otherwise fetch it all.
                if timeframe == "pastweek", let update, let old = cache[key], old.notices.isEmpty,
                   old.submitted != nil, now().timeIntervalSince(old.fetchedAt) < Self.week {
                    raw = Self.merged(old, try await update(feeds, old.fetchedAt.addingTimeInterval(-Self.announcementLag)))
                } else {
                    raw = try await fetcher(timeframe, feeds, config)
                }
            } catch let e as RouterError {
                throw e
            } catch {
                throw RouterError(502, "arXiv fetch failed (\(Self.errorName(error))). arXiv may be slow or down; try again in a moment.")
            }
            // Never cache an empty fetch (nothing subscribed / arXiv hiccup).
            if let raw, !raw.papers.isEmpty { cache[key] = raw }
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
    private lazy var current = Self.makeRouter(store: .standard)

    public var router: DigestRouter { lock.withLock { current } }

    /// The live router: the past week from the export API, today from arXiv's
    /// `/new` listing pages (as the GUI and server do).
    static func makeRouter(store: LocalStore) -> DigestRouter {
        makeRouter(store: store, fetcher: { timeframe, feeds, config in
            let fetcher = ArxivFetcher()
            return timeframe == "today"
                ? try await fetcher.fetchTodayListing(feeds, config: config)
                : try await fetcher.fetchPastweek(feeds)
        }, update: { feeds, since in try await ArxivFetcher().fetchPastweek(feeds, since: since) },
        fetchPaper: { id in try await ArxivFetcher().fetchPaper(id) })
    }

    /// A router over `store`: the saved config (first run: the engine's
    /// defaults), removed papers and fetch cache, with the engine's presets.
    public static func makeRouter(store: LocalStore, fetcher: @escaping LiveSource.Fetcher,
                                  update: LiveSource.Updater? = nil,
                                  fetchPaper: @escaping LiveSource.PaperFetcher = { _ in nil }) -> DigestRouter {
        DigestRouter(
            source: LiveSource(fetcher: fetcher, update: update, fetchPaper: fetchPaper, store: store),
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
