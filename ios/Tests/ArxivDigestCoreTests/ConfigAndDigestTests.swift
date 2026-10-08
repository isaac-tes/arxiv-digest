import XCTest
@testable import ArxivDigestCore
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

final class DigestConfigEditingTests: XCTestCase {
    func testJSONValueDecodesBoolsAsBools() throws {
        let data = #"{"a": true, "b": 1, "c": 2.5, "d": null, "e": [1, "x"], "f": {"g": false}}"#.data(using: .utf8)!
        let v = try JSONDecoder().decode([String: JSONValue].self, from: data)
        XCTAssertEqual(v["a"], .bool(true))
        XCTAssertEqual(v["b"], .int(1))
        XCTAssertEqual(v["c"], .double(2.5))
        XCTAssertEqual(v["d"], .null)
        XCTAssertEqual(v["e"], .array([.int(1), .string("x")]))
        XCTAssertEqual(v["f"], .object(["g": .bool(false)]))
        XCTAssertEqual(JSONValue.double(4.0).intValue, 4)
        XCTAssertNil(JSONValue.double(4.5).intValue)
    }

    func testFeedsSubscribeAndRemove() {
        var cfg = DigestConfig()
        cfg.setFeed(name: " quant-ph ")
        cfg.setFeed(name: "cond-mat.str-el", url: "https://arxiv.org/list/cond-mat.str-el/pastweek")
        cfg.setFeed(name: "   ")
        XCTAssertEqual(cfg.feeds, [
            "quant-ph": "https://arxiv.org/list/quant-ph/new",
            "cond-mat.str-el": "https://arxiv.org/list/cond-mat.str-el/pastweek",
        ])
        cfg.setSubscribed(true, feed: "quant-ph")
        cfg.setSubscribed(true, feed: "quant-ph")
        cfg.setSubscribed(true, feed: "cond-mat.str-el")
        XCTAssertEqual(cfg.defaultFeeds, ["quant-ph", "cond-mat.str-el"])
        cfg.setFeedWeight(3, for: "quant-ph")
        cfg.removeFeed("quant-ph")
        XCTAssertNil(cfg.feeds["quant-ph"])
        XCTAssertEqual(cfg.defaultFeeds, ["cond-mat.str-el"])
        XCTAssertEqual(cfg.feedWeight("quant-ph"), 0)
    }

    func testFeedWeightZeroRemovesEntry() {
        var cfg = DigestConfig()
        cfg.setFeedWeight(4, for: "quant-ph")
        XCTAssertEqual(cfg.feedWeights, ["quant-ph": 4])
        cfg.setFeedWeight(0, for: "quant-ph")
        XCTAssertEqual(cfg.feedWeights, [:])
    }

    func testWeightsDefaultAndSetKeepOtherFields() {
        var cfg = DigestConfig(data: ["weights": .object(["core_keyword": .int(8)])])
        XCTAssertEqual(cfg.weight(.coreKeyword), 8)
        XCTAssertEqual(cfg.weight(.lowPriorityPenalty), -5)
        cfg.setWeight(-3, for: .lowPriorityPenalty)
        XCTAssertEqual(cfg.data["weights"]?.objectValue?["core_keyword"], .int(8))
        XCTAssertEqual(cfg.weight(.lowPriorityPenalty), -3)
        XCTAssertEqual(ScoringWeight.longAbstractThreshold.label, "long abstract threshold")
    }

    func testDisplayDefaultsMatchEngine() {
        let cfg = DigestConfig()
        XCTAssertFalse(cfg.highlightTermsSummary)
        XCTAssertTrue(cfg.highlightTermsTitle)
        XCTAssertFalse(cfg.includeReplacements)
        XCTAssertTrue(cfg.wordBoundaryMatching)
        XCTAssertEqual(cfg.color(for: .subject), "#a371f7")
    }

    func testListHelpers() {
        XCTAssertEqual(DigestConfig.cleaned([" a ", "", "  ", "b"]), ["a", "b"])
        var list = ["Floquet"]
        XCTAssertFalse(DigestConfig.append("floquet", to: &list))
        XCTAssertFalse(DigestConfig.append("  ", to: &list))
        XCTAssertTrue(DigestConfig.append(" anyon ", to: &list))
        XCTAssertEqual(list, ["Floquet", "anyon"])
    }

    func testAddableAuthorsSkipsNamedCaseInsensitively() {
        var cfg = DigestConfig()
        cfg.namedAuthors = ["alice smith"]
        XCTAssertEqual(cfg.addableAuthors(in: "Alice Smith, Bob Jones,  Carol Wu , "), ["Bob Jones", "Carol Wu"])
        XCTAssertEqual(cfg.addableAuthors(in: ""), [])
        XCTAssertTrue(DigestConfig.append("Bob Jones", to: &cfg.namedAuthors))
        XCTAssertFalse(DigestConfig.append("BOB JONES", to: &cfg.namedAuthors))
        XCTAssertEqual(cfg.addableAuthors(in: "Alice Smith, Bob Jones"), [])
    }

    func testAddableAuthorsSkipsSurnameOnlyMatch() {
        var cfg = DigestConfig()
        cfg.namedAuthors = ["jones"]
        XCTAssertEqual(cfg.addableAuthors(in: "Bob Jones, Carol Wu, Joneson Ray"), ["Carol Wu", "Joneson Ray"])
    }

    func testEquatableForDirtyTracking() {
        var a = DigestConfig()
        a.coreKeywords = ["x"]
        var b = a
        XCTAssertEqual(a, b)
        b.topN = 5
        XCTAssertNotEqual(a, b)
    }

    func testPresetDisplayName() {
        XCTAssertEqual(PresetInfo(name: "open-quantum-systems", description: "").displayName, "Open Quantum Systems")
    }
}

final class DigestDecodingTests: XCTestCase {
    func testFullDigestDecodes() throws {
        let json = """
        {"papers": [{"rank": 1, "id": "2609.1", "title": "T", "authors": "A", "link": "https://arxiv.org/abs/2609.1",
          "subjects": "quant-ph", "section": "Mon, 28 Sep 2026", "summary": "S.", "score": 8,
          "abstract": "S. More.", "breakdown": {"signals": {"keyword": {"total": 8}}, "total": 8}}],
         "total_papers": 30, "requested_top": 10, "fetched_papers": 40, "hidden_by_filters": 9,
         "removed": [], "available_days": ["Mon, 28 Sep 2026"], "day": null, "timeframe": "pastweek",
         "feeds": ["quant-ph"], "notices": ["slow"], "fetched_at": "2026-10-02T09:15:00.123456+00:00"}
        """.data(using: .utf8)!
        let d = try JSONDecoder().decode(Digest.self, from: json)
        XCTAssertEqual(d.papers[0].fullAbstract, "S. More.")
        XCTAssertEqual(d.papers[0].breakdown?.total, 8)
        XCTAssertEqual(d.papers[0].pdfURL?.absoluteString, "https://arxiv.org/pdf/2609.1")
        XCTAssertEqual(d.fetchedPapers, 40)
        XCTAssertEqual(d.availableDays, ["Mon, 28 Sep 2026"])
        XCTAssertNil(d.day)
        XCTAssertEqual(d.notices, ["slow"])
        XCTAssertNotNil(d.fetchedDate)
        XCTAssertEqual(d.caption(showing: 1),
                       "Showing 1 of 1 ranked (out of 30 shown / 40 fetched). 9 hidden by replacement/day filters.")
    }

    func testOldServerDigestDecodesWithDefaults() throws {
        let json = """
        {"papers": [{"rank": 1, "id": "a", "title": "T", "authors": "A", "link": "L",
          "subjects": "s", "section": "", "summary": "Sum", "score": 1}],
         "total_papers": 5, "requested_top": 20}
        """.data(using: .utf8)!
        let d = try JSONDecoder().decode(Digest.self, from: json)
        XCTAssertEqual(d.fetchedPapers, 5)
        XCTAssertEqual(d.papers[0].fullAbstract, "Sum")
        XCTAssertNil(d.papers[0].breakdown)
        XCTAssertNil(d.papers[0].pdfURL)
        XCTAssertEqual(d.caption(showing: 1), "Showing 1 of 1 ranked (out of 5 shown / 5 fetched).")
    }

    func testISODateVariants() {
        XCTAssertNotNil(ISODate.parse("2026-10-02T09:15:00Z"))
        XCTAssertNotNil(ISODate.parse("2026-10-02T09:15:00.5+00:00"))
        XCTAssertNotNil(ISODate.parse("2026-10-02T09:15:00"))
        XCTAssertNil(ISODate.parse("yesterday"))
    }

    func testScoreResultRank() throws {
        let json = #"{"paper": null, "breakdown": {"signals": {}, "total": 0}, "rank": 3, "absence_reason": null}"#
        let r = try JSONDecoder().decode(ScoreResult.self, from: Data(json.utf8))
        XCTAssertEqual(r.rank, 3)
    }

    func testAPIErrorMessages() {
        XCTAssertEqual(APIError.message(fromBody: Data(#"{"detail": "arXiv down"}"#.utf8)), "arXiv down")
        XCTAssertEqual(APIError.message(fromBody: Data(#"{"detail": [{"msg": "bad"}, {"msg": "worse"}]}"#.utf8)), "bad; worse")
        XCTAssertEqual(APIError.message(fromBody: Data("plain".utf8)), "plain")
        XCTAssertEqual(APIError.http(502, "arXiv down").errorDescription, "arXiv down")
    }
}

final class APIClientEndpointTests: XCTestCase {
    override func setUp() {
        super.setUp()
        MockURLProtocol.reset()
    }

    private func client() -> APIClient {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockURLProtocol.self]
        return APIClient(baseURL: URL(string: "http://127.0.0.1:8000")!, session: URLSession(configuration: config))
    }

    private static func respond(_ request: URLRequest, _ status: Int, _ body: String) -> (HTTPURLResponse, Data) {
        (HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!, Data(body.utf8))
    }

    func testDigestQueryItems() {
        let q = APIClient.digestQuery(timeframe: "today", topN: 5, day: "Mon, 28 Sep 2026", feeds: nil, refresh: true)
        XCTAssertEqual(q.map(\.name), ["timeframe", "top_n", "day", "refresh"])
        XCTAssertTrue(APIClient.digestQuery(timeframe: nil, topN: nil, day: nil, feeds: [], refresh: false).isEmpty)
    }

    func testFetchDigestSendsDay() async throws {
        MockURLProtocol.handler = { request in
            let comps = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)!
            XCTAssertEqual(comps.path, "/digest")
            XCTAssertEqual(comps.queryItems?.first { $0.name == "day" }?.value, "Mon, 28 Sep 2026")
            return Self.respond(request, 200, #"{"papers": [], "total_papers": 0, "requested_top": 10}"#)
        }
        let d = try await client().fetchDigest(day: "Mon, 28 Sep 2026")
        XCTAssertEqual(d.requestedTop, 10)
    }

    func testRemoveAndRestoreAccept204() async throws {
        MockURLProtocol.handler = { request in
            let body = try XCTUnwrap(request.bodyData)
            let obj = try XCTUnwrap(try JSONSerialization.jsonObject(with: body) as? [String: Any])
            if request.url?.path == "/removed" {
                XCTAssertEqual(obj["arxiv_id"] as? String, "2609.1")
            } else {
                XCTAssertEqual(request.url?.path, "/removed/restore")
                XCTAssertEqual(obj["arxiv_ids"] as? [String], ["2609.1"])
            }
            return Self.respond(request, 204, "")
        }
        try await client().removePaper(arxivId: "2609.1")
        try await client().restorePapers(arxivIds: ["2609.1"])
    }

    func testHTTPErrorCarriesDetail() async {
        MockURLProtocol.handler = { request in Self.respond(request, 502, #"{"detail": "arXiv fetch failed"}"#) }
        do {
            _ = try await client().fetchDigest()
            XCTFail("expected error")
        } catch {
            XCTAssertEqual(error as? APIError, .http(502, "arXiv fetch failed"))
        }
    }

    func testMergePresetUnsavedSendsWorkingConfig() async throws {
        MockURLProtocol.handler = { request in
            let comps = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)!
            XCTAssertEqual(comps.path, "/config/presets/quantum-many-body/merge")
            XCTAssertEqual(comps.queryItems?.first?.value, "false")
            let obj = try XCTUnwrap(try JSONSerialization.jsonObject(with: XCTUnwrap(request.bodyData)) as? [String: Any])
            XCTAssertEqual((obj["data"] as? [String: Any])?["top_n"] as? Int, 7)
            return Self.respond(request, 200, #"{"data": {"top_n": 7, "core_keywords": ["dmrg"]}}"#)
        }
        var working = DigestConfig()
        working.topN = 7
        let merged = try await client().mergePreset(named: "quantum-many-body", into: working, save: false)
        XCTAssertEqual(merged.coreKeywords, ["dmrg"])
    }

    func testScoreSendsViewParameters() async throws {
        MockURLProtocol.handler = { request in
            let obj = try XCTUnwrap(try JSONSerialization.jsonObject(with: XCTUnwrap(request.bodyData)) as? [String: Any])
            XCTAssertEqual(obj["arxiv_id"] as? String, "2609.1")
            XCTAssertEqual(obj["top_n"] as? Int, 5)
            XCTAssertNil(obj["day"])
            return Self.respond(request, 200, #"{"paper": null, "breakdown": {"signals": {}, "total": 0}, "rank": null, "absence_reason": "Paper not found"}"#)
        }
        let r = try await client().score(arxivId: "2609.1", timeframe: "pastweek", topN: 5)
        XCTAssertEqual(r.absenceReason, "Paper not found")
    }
}
