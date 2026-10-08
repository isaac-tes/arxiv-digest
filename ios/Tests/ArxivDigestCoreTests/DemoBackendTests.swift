import XCTest
@testable import ArxivDigestCore
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

final class DemoBackendTests: XCTestCase {
    private var client: APIClient!

    override func setUp() {
        super.setUp()
        DemoBackend.shared.reset()
        client = APIClient(baseURL: DemoURLProtocol.baseURL, session: DemoURLProtocol.makeSession())
    }

    func testFixtureIsInternallyConsistent() async throws {
        let digest = try await client.fetchDigest(topN: 100)
        XCTAssertEqual(digest.papers.count, 14)
        for p in digest.papers {
            XCTAssertEqual(p.breakdown?.total, p.score, p.title)
            XCTAssertFalse(p.abstract.isEmpty)
            XCTAssertTrue(p.abstract.hasPrefix(p.summary.replacingOccurrences(of: "  ", with: " ").prefix(20)))
        }
        // Ranked by (-score, title), ranks 1...n.
        XCTAssertEqual(digest.papers.map(\.rank), Array(1...14))
        let scores = digest.papers.map(\.score)
        XCTAssertEqual(scores, scores.sorted(by: >))
        XCTAssertEqual(digest.availableDays.count, 5)
    }

    func testFixtureNamesAreInventedAndHighlightsAgreeWithScores() async throws {
        let cfg = try await client.getConfig()
        let digest = try await client.fetchDigest(topN: 100)
        for p in digest.papers {
            let kw = p.breakdown?.signals["keyword"]
            let terms = HighlightEngine.matchedTerms(for: p, config: cfg)
            XCTAssertEqual(Set(terms.keywords), Set(kw?.keywords?.map(\.term) ?? []), p.title)
            XCTAssertEqual(Set(terms.authors), Set(kw?.authors?.map(\.term) ?? []), p.title)
            XCTAssertEqual(Set(terms.lowPriority), Set(kw?.lowPriorityHits ?? []), p.title)
            XCTAssertEqual(Set(terms.subjects), Set(kw?.subjects?.keys.map { $0 } ?? []), p.title)
        }
    }

    func testTopNDayAndRemovalLikeServer() async throws {
        let top = try await client.fetchDigest(topN: 3)
        XCTAssertEqual(top.papers.count, 3)
        XCTAssertEqual(top.totalPapers, 14)

        let day = top.availableDays.last!
        let byDay = try await client.fetchDigest(topN: 10, day: day)
        XCTAssertEqual(byDay.day, day)
        XCTAssertTrue(byDay.papers.allSatisfy { $0.section == day })
        XCTAssertEqual(byDay.hiddenByFilters, 14 - byDay.papers.count)

        let first = top.papers[0]
        let topFour = try await client.fetchDigest(topN: 4).papers.map(\.id)
        try await client.removePaper(arxivId: first.id)
        let after = try await client.fetchDigest(topN: 3)
        XCTAssertEqual(after.papers.map(\.id), Array(topFour.dropFirst()))
        XCTAssertEqual(after.papers[0].id, top.papers[1].id)
        XCTAssertEqual(after.removed.map(\.id), [first.id])
        XCTAssertEqual(after.removed.first?.rank, 1)  // full-ranking position, like the server
        XCTAssertEqual(after.caption(showing: 3), "Showing 3 of 3 ranked (out of 13 shown / 14 fetched). 1 removed by you.")
        let removedIds = try await client.removedPapers()
        XCTAssertEqual(removedIds, [first.id])

        try await client.restorePapers(arxivIds: [first.id])
        let restored = try await client.fetchDigest(topN: 3)
        XCTAssertEqual(restored.papers.map(\.id), top.papers.map(\.id))
    }

    func testTodayHidesReplacementUnlessIncluded() async throws {
        let today = try await client.fetchDigest(timeframe: "today", topN: 10)
        XCTAssertEqual(today.fetchedPapers, 4)
        XCTAssertEqual(today.hiddenByFilters, 1)
        var cfg = try await client.getConfig()
        cfg.includeReplacements = true
        _ = try await client.putConfig(cfg)
        let all = try await client.fetchDigest(timeframe: "today", topN: 10)
        XCTAssertEqual(all.papers.count, 4)
    }

    func testScorePlacement() async throws {
        let top = try await client.fetchDigest(topN: 3)
        let ranked = try await client.score(arxivId: "https://arxiv.org/abs/\(top.papers[1].id)v2", topN: 3)
        XCTAssertEqual(ranked.rank, 2)
        XCTAssertNil(ranked.absenceReason)

        let all = try await client.fetchDigest(topN: 100)
        let below = try await client.score(arxivId: all.papers.last!.id, topN: 3)
        XCTAssertEqual(below.absenceReason, "This paper **was** fetched but ranked below your top-3 cutoff.")

        try await client.removePaper(arxivId: top.papers[0].id)
        let removed = try await client.score(arxivId: top.papers[0].id, topN: 3)
        XCTAssertTrue(removed.absenceReason?.hasPrefix("You **removed** this paper from the digest") ?? false)

        let otherDay = all.availableDays.first { $0 != all.papers[1].section }!
        let dayMiss = try await client.score(arxivId: all.papers[1].id, topN: 3, day: otherDay)
        XCTAssertTrue(dayMiss.absenceReason?.contains("not from the picked day") ?? false)

        let missing = try await client.score(arxivId: "2601.00001")
        XCTAssertNil(missing.paper)
        XCTAssertEqual(missing.absenceReason, "Paper not found")
    }

    func testPresetsUnsavedThenSaved() async throws {
        let info = try await client.presetInfo()
        XCTAssertEqual(info.count, 3)
        let before = try await client.getConfig()
        let merged = try await client.mergePreset(named: info[0].name, into: before, save: false)
        XCTAssertGreaterThan(merged.coreKeywords.count, before.coreKeywords.count)
        XCTAssertEqual(merged.coreKeywords.prefix(before.coreKeywords.count).map { $0 }, before.coreKeywords)
        let stillBefore = try await client.getConfig()
        XCTAssertEqual(stillBefore, before)

        let loaded = try await client.loadPreset(named: info[0].name, save: true)
        let now = try await client.getConfig()
        XCTAssertEqual(now, loaded)
    }

    func testZoteroAndErrors() async throws {
        let status = try await client.zoteroStatus()
        XCTAssertEqual(ZoteroPolicy.availability(from: status), .web)
        let saved = try await client.saveToZotero(arxivId: "2609.21407")
        XCTAssertTrue(saved.ok)
        do {
            _ = try await client.fetchDigest(timeframe: "yesterday")
            XCTFail("expected 422")
        } catch {
            XCTAssertEqual(error as? APIError, .http(422, "timeframe must be 'today' or 'pastweek'"))
        }
    }
}
