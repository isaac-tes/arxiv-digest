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

    /// Fetch the past week for these feed names.
    public typealias Fetcher = @Sendable (_ feeds: [String], _ config: DigestConfig) async throws -> RawFetch

    public static let todayUnavailable =
        "Standalone mode fetches the past week only. Set the timeframe to pastweek, or use a digest server for today's listing."
    static let ttl: TimeInterval = 60 * 60

    public nonisolated var mode: String { "standalone" }
    // No Zotero key on the device; Share to Zotero covers saving.
    public nonisolated var zoteroWebAvailable: Bool { false }

    private let fetcher: Fetcher
    private let now: @Sendable () -> Date
    private var cache: [String: RawFetch] = [:]

    public init(fetcher: @escaping Fetcher, now: @escaping @Sendable () -> Date = Date.init) {
        self.fetcher = fetcher
        self.now = now
    }

    private static func key(_ feeds: [String]) -> String { feeds.joined(separator: ",") }

    private func fresh(_ feeds: [String]) -> RawFetch? {
        guard let hit = cache[Self.key(feeds)], now().timeIntervalSince(hit.fetchedAt) < Self.ttl else { return nil }
        return hit
    }

    public func fetch(timeframe: String, feeds: [String], config: DigestConfig, refresh: Bool) async throws -> SourceFetch {
        guard timeframe == "pastweek" else { throw RouterError(422, Self.todayUnavailable) }
        var raw = refresh ? nil : fresh(feeds)
        if raw == nil {
            do {
                raw = try await fetcher(feeds, config)
            } catch let e as RouterError {
                throw e
            } catch {
                throw RouterError(502, "arXiv fetch failed (\(type(of: error))). arXiv may be slow or down; try again in a moment.")
            }
            // Never cache an empty fetch (nothing subscribed / arXiv hiccup).
            if let raw, !raw.papers.isEmpty { cache[Self.key(feeds)] = raw }
        }
        return Self.scored(raw!, config: config)
    }

    public func cached(timeframe: String, feeds: [String], config: DigestConfig) async -> SourceFetch? {
        guard timeframe == "pastweek", let raw = fresh(feeds) else { return nil }
        return Self.scored(raw, config: config)
    }

    public func lookup(id: String, timeframe: String, config: DigestConfig) async throws -> SourceLookup? {
        // ponytail: cached papers only; fetching by id from arXiv lands in S5.
        guard let p = cache.values.lazy.flatMap(\.papers).first(where: { $0.id == id }) else { return nil }
        return SourceLookup(
            paper: ScoredPaper(id: p.id, title: p.title, authors: p.authors, link: p.link,
                               subjects: p.subjects, section: p.section, abstract: p.abstract),
            breakdown: Scorer.explain(paper: p, config: config),
            notFetchedReason: "This paper was **not in the fetched set**.")
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
    // ponytail: the demo's invented config until on-device storage (S4) lands.
    private var current = DigestRouter(
        source: LiveSource(fetcher: { feeds, _ in try await ArxivFetcher().fetchPastweek(feeds) }),
        config: DemoBackend.fixture.config, defaults: DemoBackend.fixture.config,
        presets: DemoBackend.fixture.presets)

    public var router: DigestRouter { lock.withLock { current } }

    /// Replace the router (tests inject a fetcher this way).
    public func install(_ router: DigestRouter) {
        lock.withLock { current = router }
    }
}

/// Standalone mode's requests → `StandaloneBackend.shared`.
public final class LocalURLProtocol: RouterURLProtocol {
    override class var router: DigestRouter { StandaloneBackend.shared.router }
    override public class var baseURL: URL { URL(string: "https://device.arxiv-digest.invalid")! }
}
