import XCTest
@testable import ArxivDigestCore

/// Tests for the `/score` response decoding and the highlight-span engine that
/// backs the app's keyword/author highlighting (web-GUI parity).
final class ScoreResultTests: XCTestCase {
    func testScoreResultDecodingWithPaper() throws {
        // Mirrors the backend ScoreResponse: `paper` is the raw arxiv_digest
        // dict (uses "abstract", no rank/score), plus breakdown + absence_reason.
        let json = """
        {
          "paper": {
            "id": "2601.00123",
            "title": "Floquet engineering of anyons",
            "authors": "A. , I. Bloch",
            "link": "https://arxiv.org/abs/2601.00123",
            "subjects": "cond-mat.quant-gas, quant-ph",
            "section": "Fri, 19 Jun 2026",
            "abstract": "We drive a lattice periodically."
          },
          "breakdown": {
            "signals": {
              "keyword": {
                "keywords": [["floquet", 6], ["anyon", 6]],
                "authors": [[ 6]],
                "subjects": {"cond-mat.quant-gas": 4},
                "low_priority_hits": [],
                "low_priority_penalty": 0,
                "abstract_bonus": 1,
                "total": 23
              }
            },
            "total": 23
          },
          "absence_reason": null
        }
        """.data(using: .utf8)!
        let result = try JSONDecoder().decode(ScoreResult.self, from: json)
        XCTAssertEqual(result.paper?.id, "2601.00123")
        XCTAssertEqual(result.paper?.abstract, "We drive a lattice periodically.")
        XCTAssertEqual(result.breakdown.total, 23)
        XCTAssertEqual(result.breakdown.signals["keyword"]?.keywords?.count, 2)
        XCTAssertNil(result.absenceReason)
    }

    func testScoreResultDecodingNotFound() throws {
        // When the paper can't be fetched the backend returns paper: null,
        // an empty breakdown, and an absence reason.
        let json = """
        {"paper": null, "breakdown": {"signals": {}, "total": 0}, "absence_reason": "Paper not found"}
        """.data(using: .utf8)!
        let result = try JSONDecoder().decode(ScoreResult.self, from: json)
        XCTAssertNil(result.paper)
        XCTAssertEqual(result.breakdown.total, 0)
        XCTAssertEqual(result.absenceReason, "Paper not found")
    }
}

final class HighlightSpanTests: XCTestCase {
    func testRangesWholeWord() {
        let text = "Floquet and floquet-engineering but not temporal"
        let ranges = HighlightEngine.ranges(of: "floquet", in: text)
        // Two whole-word matches ("Floquet", "floquet"); "temporal" excluded.
        XCTAssertEqual(ranges.count, 2)
        XCTAssertEqual(ranges.map { String(text[$0]).lowercased() }, ["floquet", "floquet"])
    }

    func testSpansMarkKeywordsAndLowPriority() {
        let text = "A study of floquet topological phases in photonic lattices"
        let spans = HighlightEngine.spans(
            in: text,
            keywords: ["floquet", "topological"],
            lowPriority: ["photonic"]
        )
        let rendered = spans.map { (String(text[$0.range]).lowercased(), $0.aspect) }
        XCTAssertEqual(rendered.count, 3)
        XCTAssertTrue(rendered.contains(where: { $0.0 == "floquet" && $0.1 == .keyword }))
        XCTAssertTrue(rendered.contains(where: { $0.0 == "topological" && $0.1 == .keyword }))
        XCTAssertTrue(rendered.contains(where: { $0.0 == "photonic" && $0.1 == .lowPriority }))
    }

    func testSpansKeywordWinsOverlapWithLowPriority() {
        // If the same token is both a keyword and a low-priority term, the
        // positive keyword aspect wins (higher priority).
        let text = "quantum simulation"
        let spans = HighlightEngine.spans(in: text, keywords: ["quantum"], lowPriority: ["quantum"])
        XCTAssertEqual(spans.count, 1)
        XCTAssertEqual(spans.first?.aspect, .keyword)
    }

    func testSpansSortedByPosition() {
        let text = "topological floquet"
        let spans = HighlightEngine.spans(in: text, keywords: ["floquet", "topological"])
        // Emitted in reading order regardless of the argument order.
        XCTAssertEqual(spans.map { String(text[$0.range]) }, ["topological", "floquet"])
    }
}

final class APIClientScoreTests: XCTestCase {
    override func setUp() {
        super.setUp()
        MockURLProtocol.reset()
    }

    private func makeClient() -> APIClient {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockURLProtocol.self]
        let session = URLSession(configuration: config)
        return APIClient(baseURL: URL(string: "http://127.0.0.1:8000")!, session: session)
    }

    func testScorePostsAndDecodes() async throws {
        MockURLProtocol.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.path, "/score")
            let body = """
            {"paper": {"id": "2601.1", "title": "T", "authors": "A", "link": "L",
             "subjects": "quant-ph", "section": "New", "abstract": "abs"},
             "breakdown": {"signals": {"keyword": {"total": 6}}, "total": 6},
             "absence_reason": null}
            """.data(using: .utf8)!
            let resp = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (resp, body)
        }
        let client = makeClient()
        let result = try await client.score(arxivId: "2601.1")
        XCTAssertEqual(result.paper?.id, "2601.1")
        XCTAssertEqual(result.breakdown.total, 6)
    }
}
