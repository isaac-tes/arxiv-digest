import XCTest
@testable import ArxivDigestCore
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

/// Standalone mode (ADR 0009): the shared router over a live source, with an
/// injected fetcher so nothing touches the network.
final class StandaloneTests: XCTestCase {
    private var client: APIClient!

    static let papers = [
        RawPaper(id: "2610.00001", title: "Floquet anyons", authors: "Mira Castellanos",
                 abstract: "Driven lattices. Second sentence. Third.", subjects: "Quantum Physics (quant-ph)",
                 link: "https://arxiv.org/abs/2610.00001", section: "Mon, 5 Oct 2026"),
        RawPaper(id: "2610.00002", title: "Kitaev magnets", authors: "Ruth Okafor",
                 abstract: "Thermal Hall.", subjects: "Strongly Correlated Electrons (cond-mat.str-el)",
                 link: "https://arxiv.org/abs/2610.00002", section: "Tue, 6 Oct 2026"),
    ]

    private func install(fetcher: @escaping LiveSource.Fetcher) {
        var cfg = DigestConfig()
        cfg.coreKeywords = ["floquet"]
        cfg.namedAuthors = []
        cfg.lowPriorityKeywords = []
        cfg.feeds = ["quant-ph": DigestConfig.listingURL(for: "quant-ph")]
        cfg.defaultFeeds = ["quant-ph"]
        cfg.feedWeights = [:]
        StandaloneBackend.shared.install(DigestRouter(
            source: LiveSource(fetcher: fetcher), config: cfg.data, defaults: cfg.data, presets: [:]))
        client = APIClient(baseURL: LocalURLProtocol.baseURL, session: LocalURLProtocol.makeSession())
    }

    func testHealthSaysStandalone() async throws {
        install { _, _, _ in .init(papers: Self.papers) }
        let h = try await client.health()
        XCTAssertEqual(h["mode"], "standalone")
    }

    func testScoresReactToConfigEdits() async throws {
        install { _, _, _ in .init(papers: Self.papers) }
        let first = try await client.fetchDigest(topN: 10)
        XCTAssertEqual(first.papers.map(\.id), ["2610.00001", "2610.00002"])
        XCTAssertEqual(first.papers[0].score, 6)
        XCTAssertEqual(first.papers[0].summary, "Driven lattices. Second sentence.")
        XCTAssertEqual(first.availableDays, ["Mon, 5 Oct 2026", "Tue, 6 Oct 2026"])
        XCTAssertEqual(first.feeds, ["quant-ph"])

        var cfg = try await client.getConfig()
        cfg.coreKeywords = ["kitaev"]
        _ = try await client.putConfig(cfg)
        let second = try await client.fetchDigest(topN: 10)
        XCTAssertEqual(second.papers.map(\.id), ["2610.00002", "2610.00001"])
        XCTAssertEqual(second.papers[0].breakdown?.signals["keyword"]?.keywords, [TermHit(term: "kitaev", weight: 6)])
    }

    func testFetchIsCachedUntilRefresh() async throws {
        let calls = Counter()
        install { _, _, _ in calls.bump(); return .init(papers: Self.papers) }
        _ = try await client.fetchDigest()
        _ = try await client.fetchDigest()
        XCTAssertEqual(calls.value, 1)
        _ = try await client.fetchDigest(refresh: true)
        XCTAssertEqual(calls.value, 2)
    }

    func testScoreUsesCachedFetch() async throws {
        install { _, _, _ in .init(papers: Self.papers) }
        let early = try await client.score(arxivId: "2610.00002")
        XCTAssertNil(early.paper)
        _ = try await client.fetchDigest(topN: 1)
        let below = try await client.score(arxivId: "arXiv:2610.00002v3", topN: 1)
        XCTAssertEqual(below.paper?.section, "Tue, 6 Oct 2026")
        XCTAssertEqual(below.absenceReason, "This paper **was** fetched but ranked below your top-1 cutoff.")
    }

    func testTodayIsFetchedAndCachedApartFromPastweek() async throws {
        let timeframes = Recorder<String>()
        install { timeframe, _, _ in
            timeframes.add(timeframe)
            guard timeframe == "today" else { return .init(papers: Self.papers) }
            var replaced = Self.papers[1]
            replaced.section = "Replacement submissions (showing 1 of 1 entries)"
            var new = Self.papers[0]
            new.section = "New submissions (showing 1 of 1 entries)"
            return .init(papers: [new, replaced])
        }
        let today = try await client.fetchDigest(timeframe: "today", topN: 10)
        XCTAssertEqual(today.papers.map(\.id), ["2610.00001"])  // replacement hidden
        XCTAssertEqual(today.hiddenByFilters, 1)
        XCTAssertEqual(today.availableDays, [])
        _ = try await client.fetchDigest(timeframe: "pastweek")
        _ = try await client.fetchDigest(timeframe: "today")
        XCTAssertEqual(timeframes.values, ["today", "pastweek"])
    }

    func testFetchFailureIs502() async throws {
        install { _, _, _ in throw URLError(.timedOut) }
        do {
            _ = try await client.fetchDigest()
            XCTFail("expected 502")
        } catch {
            guard case .http(502, let detail)? = error as? APIError else { return XCTFail("\(error)") }
            XCTAssertTrue(detail.hasPrefix("arXiv fetch failed"), detail)
        }
    }

    func testZoteroWebAPIUnavailable() async throws {
        install { _, _, _ in .init(papers: []) }
        let status = try await client.zoteroStatus()
        XCTAssertEqual(ZoteroPolicy.availability(from: status), .unavailable)
    }
}

/// Expected values from `arxiv_digest.summarize` / `available_day_labels`.
final class EngineTextParityTests: XCTestCase {
    func testSummarize() {
        XCTAssertEqual(Scorer.summarize(""), "(No abstract available.)")
        XCTAssertEqual(Scorer.summarize("   "), "(No abstract available.)")
        XCTAssertEqual(Scorer.summarize("One. Two!  Three?\nFour."), "One. Two!")
        XCTAssertEqual(Scorer.summarize("No terminal punctuation here"), "No terminal punctuation here")
        XCTAssertEqual(Scorer.summarize("e.g. this.  And\tthat. More."), "e.g. this. And that.")
        XCTAssertEqual(Scorer.summarize("Ends with dot."), "Ends with dot.")
        // Citations, abbreviations, initials and parentheses don't end a sentence.
        XCTAssertEqual(
            Scorer.summarize("A recent experiment by Roy et al. (Nat. Commun. 17, 2853 (2026)) demonstrated a plateau. We prove a theorem. The corollary."),
            "A recent experiment by Roy et al. (Nat. Commun. 17, 2853 (2026)) demonstrated a plateau. We prove a theorem.")
        XCTAssertEqual(Scorer.summarize("Work by J. Smith shows it. Second. Third."), "Work by J. Smith shows it. Second.")
        XCTAssertEqual(Scorer.summarize("Unbalanced (paren. Still one. Two. Three."), "Unbalanced (paren. Still one.")
        XCTAssertEqual(Scorer.summarize("Trailing abbrev et al."), "Trailing abbrev et al.")
    }

    func testAvailableDayLabels() {
        let sections = ["Fri, 2 Oct 2026 (showing 3 of 3 entries )", "Mon, 28 Sep 2026",
                        "New submissions (showing 2 of 2 entries)", "Thu, 01 Oct 2026"]
        XCTAssertEqual(DigestRouter.availableDayLabels(sections),
                       ["Mon, 28 Sep 2026", "Thu, 01 Oct 2026", "Fri, 2 Oct 2026"])
    }
}

final class Counter: @unchecked Sendable {
    private let lock = NSLock()
    private var n = 0
    var value: Int { lock.withLock { n } }
    func bump() { lock.withLock { n += 1 } }
}

/// Score-a-paper for a paper outside the cached fetch (S5).
final class StandaloneScoreTests: XCTestCase {
    private func client(fetchPaper: @escaping LiveSource.PaperFetcher) -> APIClient {
        var cfg = DigestConfig(data: EngineConfig.defaults)
        cfg.namedAuthors = ["okafor"]
        cfg.feeds = ["quant-ph": DigestConfig.listingURL(for: "quant-ph")]
        cfg.defaultFeeds = ["quant-ph"]
        StandaloneBackend.shared.install(DigestRouter(
            source: LiveSource(fetcher: { _, _, _ in .init(papers: StandaloneTests.papers) }, fetchPaper: fetchPaper),
            config: cfg.data, defaults: cfg.data, presets: [:]))
        return APIClient(baseURL: LocalURLProtocol.baseURL, session: LocalURLProtocol.makeSession())
    }

    static let outside = RawPaper(id: "2609.99999", title: "Plain title", authors: "Ruth Okafor", abstract: "A.",
                                  subjects: "math.CO", link: "https://arxiv.org/abs/2609.99999", section: "Sun, 20 Sep 2026")

    func testUnfetchedPaperIsScoredWithEngineReason() async throws {
        let api = client { id in id == "2609.99999" ? (Self.outside, "2026-09-20T10:00:00Z") : nil }
        let early = try await api.score(arxivId: "2609.99999")
        XCTAssertEqual(early.absenceReason, "Load the digest first to compare this paper against it.")
        XCTAssertEqual(early.breakdown.total, 6)

        _ = try await api.fetchDigest()
        let r = try await api.score(arxivId: "https://arxiv.org/abs/2609.99999v2")
        XCTAssertEqual(r.paper?.section, "Sun, 20 Sep 2026")
        XCTAssertEqual(r.absenceReason,
            "This paper was **not in the fetched set**. Deterministic check: it was submitted on **2026-09-20**, "
                + "but the fetched feed only covers **2026-10-05, 2026-10-06**; its categories (**math.CO**) are "
                + "**not among your subscribed feeds** (quant-ph).")
        let missing = try await api.score(arxivId: "2601.00001")
        XCTAssertEqual(missing.absenceReason, "Paper not found")
    }

    func testCachedPaperNeedsNoNetwork() async throws {
        let api = client { _ in throw URLError(.notConnectedToInternet) }
        _ = try await api.fetchDigest()
        let r = try await api.score(arxivId: "2610.00002")
        XCTAssertNotNil(r.rank)
    }

    func testNetworkFailureIs502() async throws {
        let api = client { _ in throw URLError(.notConnectedToInternet) }
        do {
            _ = try await api.score(arxivId: "2609.99999")
            XCTFail("expected 502")
        } catch {
            XCTAssertEqual(error as? APIError,
                           .http(502, "Could not reach arXiv (URLError); it may be rate-limiting. Try again in a moment."))
        }
    }

    /// Expected strings from the server's `score._not_fetched_reason`.
    func testNotFetchedReasonMatchesServer() {
        let days = ["Tue, 06 Oct 2026", "Mon, 05 Oct 2026"]
        XCTAssertEqual(
            LiveSource.notFetchedReason(published: "2026-09-20T10:00:00Z", categories: ["cond-mat.str-el", "quant-ph"],
                                        fetchedSections: days, feedNames: ["quant-ph", "cond-mat.quant-gas"]),
            "This paper was **not in the fetched set**. Deterministic check: it was submitted on **2026-09-20**, but the fetched feed only covers **2026-10-05, 2026-10-06**; its categories (**quant-ph**) overlap your subscribed feeds.")
        XCTAssertEqual(
            LiveSource.notFetchedReason(published: "2026-10-05T23:00:00Z", categories: ["math.CO"],
                                        fetchedSections: days, feedNames: ["quant-ph"]),
            "This paper was **not in the fetched set**. Deterministic check: it was submitted on **2026-10-05**, which IS within the fetched days — so it was likely not yet listed in the feed pages when you fetched; its categories (**math.CO**) are **not among your subscribed feeds** (quant-ph).")
        XCTAssertEqual(
            LiveSource.notFetchedReason(published: "", categories: [], fetchedSections: [], feedNames: []),
            "This paper was **not in the fetched set**. Deterministic check: its categories (**unknown**) are **not among your subscribed feeds** (none).")
        XCTAssertEqual(
            LiveSource.notFetchedReason(published: "2026-10-05T23:00:00Z", categories: ["QUANT-PH.x"],
                                        fetchedSections: [], feedNames: ["quant-ph"]),
            "This paper was **not in the fetched set**. Deterministic check: it was submitted on **2026-10-05**; its categories (**QUANT-PH.x**) overlap your subscribed feeds.")
    }
}
