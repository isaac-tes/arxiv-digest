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
        install { _, _ in .init(papers: Self.papers) }
        let h = try await client.health()
        XCTAssertEqual(h["mode"], "standalone")
    }

    func testScoresReactToConfigEdits() async throws {
        install { _, _ in .init(papers: Self.papers) }
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
        install { _, _ in calls.bump(); return .init(papers: Self.papers) }
        _ = try await client.fetchDigest()
        _ = try await client.fetchDigest()
        XCTAssertEqual(calls.value, 1)
        _ = try await client.fetchDigest(refresh: true)
        XCTAssertEqual(calls.value, 2)
    }

    func testScoreUsesCachedFetch() async throws {
        install { _, _ in .init(papers: Self.papers) }
        let early = try await client.score(arxivId: "2610.00002")
        XCTAssertNil(early.paper)
        _ = try await client.fetchDigest(topN: 1)
        let below = try await client.score(arxivId: "arXiv:2610.00002v3", topN: 1)
        XCTAssertEqual(below.paper?.section, "Tue, 6 Oct 2026")
        XCTAssertEqual(below.absenceReason, "This paper **was** fetched but ranked below your top-1 cutoff.")
    }

    func testTodayIsNotAvailable() async throws {
        install { _, _ in .init(papers: Self.papers) }
        do {
            _ = try await client.fetchDigest(timeframe: "today")
            XCTFail("expected 422")
        } catch {
            XCTAssertEqual(error as? APIError, .http(422, LiveSource.todayUnavailable))
        }
    }

    func testFetchFailureIs502() async throws {
        install { _, _ in throw URLError(.timedOut) }
        do {
            _ = try await client.fetchDigest()
            XCTFail("expected 502")
        } catch {
            guard case .http(502, let detail)? = error as? APIError else { return XCTFail("\(error)") }
            XCTAssertTrue(detail.hasPrefix("arXiv fetch failed"), detail)
        }
    }

    func testZoteroWebAPIUnavailable() async throws {
        install { _, _ in .init(papers: []) }
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
        XCTAssertEqual(Scorer.summarize("e.g. this.  And\tthat. More."), "e.g. this.")
        XCTAssertEqual(Scorer.summarize("Ends with dot."), "Ends with dot.")
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
