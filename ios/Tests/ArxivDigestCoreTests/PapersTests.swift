import XCTest
@testable import ArxivDigestCore
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

private func makePaper(rank: Int, title: String, authors: String, summary: String) -> Paper {
    Paper(rank: rank, id: "id\(rank)", title: title, authors: authors,
          link: "https://arxiv.org/abs/id\(rank)", subjects: "quant-ph",
          section: "New", summary: summary, score: 10 - rank)
}

final class PaperSearchTests: XCTestCase {
    private let papers = [
        makePaper(rank: 1, title: "Floquet engineering", authors: "A. Einstein", summary: "driven lattices"),
        makePaper(rank: 2, title: "Anyon statistics", authors: "I. Bloch", summary: "fractional excitations"),
        makePaper(rank: 3, title: "Tensor networks", authors: "F. Verstraete", summary: "DMRG methods"),
    ]

    func testEmptyQueryReturnsAll() {
        XCTAssertEqual(PaperSearch.filter(papers, query: "").count, 3)
        XCTAssertEqual(PaperSearch.filter(papers, query: "   ").count, 3)
    }

    func testMatchesTitleCaseInsensitive() {
        let r = PaperSearch.filter(papers, query: "floquet")
        XCTAssertEqual(r.map(\.id), ["id1"])
    }

    func testMatchesAuthors() {
        XCTAssertEqual(PaperSearch.filter(papers, query: "bloch").map(\.id), ["id2"])
    }

    func testMatchesSummary() {
        XCTAssertEqual(PaperSearch.filter(papers, query: "dmrg").map(\.id), ["id3"])
    }

    func testNoMatch() {
        XCTAssertTrue(PaperSearch.filter(papers, query: "supersymmetry").isEmpty)
    }
}

final class ConfigAppearanceTests: XCTestCase {
    func testColorSettersRoundTrip() {
        var cfg = DigestConfig()
        cfg.setColor("#123456", for: .keyword)
        cfg.setColor("#abcdef", for: .author)
        cfg.setColor("#0f0f0f", for: .lowPriority)
        cfg.colorSubject = "#ffffff"
        XCTAssertEqual(cfg.color(for: .keyword), "#123456")
        XCTAssertEqual(cfg.color(for: .author), "#abcdef")
        XCTAssertEqual(cfg.color(for: .lowPriority), "#0f0f0f")
        XCTAssertEqual(cfg.colorSubject, "#ffffff")
    }

    func testFontToggleRoundTrip() {
        var cfg = DigestConfig()
        // Defaults follow the engine's Config: font tint on for keywords and
        // authors, off for low-priority and subjects.
        XCTAssertTrue(cfg.fontColor(for: .keyword))
        XCTAssertTrue(cfg.fontColor(for: .author))
        XCTAssertFalse(cfg.fontColor(for: .lowPriority))
        XCTAssertFalse(cfg.colorFontSubject)
        cfg.setFontColor(false, for: .keyword)
        XCTAssertFalse(cfg.fontColor(for: .keyword))
    }

    func testFeedsRoundTripAndAvailableNames() throws {
        let json = """
        {"default_feeds": ["cond-mat.quant-gas", "quant-ph"],
         "feeds": {"cond-mat.quant-gas": "u1", "quant-ph": "u2", "cond-mat": "u3"}}
        """.data(using: .utf8)!
        let inner = try JSONDecoder().decode([String: JSONValue].self, from: json)
        var cfg = DigestConfig(data: inner)
        XCTAssertEqual(cfg.defaultFeeds, ["cond-mat.quant-gas", "quant-ph"])
        XCTAssertEqual(cfg.availableFeedNames, ["cond-mat", "cond-mat.quant-gas", "quant-ph"])
        cfg.defaultFeeds = ["cond-mat.mes-hall"]
        XCTAssertEqual(cfg.defaultFeeds, ["cond-mat.mes-hall"])
    }

    func testZoteroSaveResultDecoding() throws {
        let json = """
        {"ok": true, "mode": "web", "message": "Saved to Zotero"}
        """.data(using: .utf8)!
        let r = try JSONDecoder().decode(ZoteroSaveResult.self, from: json)
        XCTAssertTrue(r.ok)
        XCTAssertEqual(r.mode, "web")
        XCTAssertEqual(r.message, "Saved to Zotero")
    }

    // Without a Web API key on the server, the app offers Share to Zotero
    // (the OS share sheet) instead of a server save.
    func testZoteroPolicyAvailability() {
        XCTAssertEqual(ZoteroPolicy.availability(from: ["web_api_available": true]), .web)
        XCTAssertEqual(ZoteroPolicy.availability(from: ["web_api_available": false]), .unavailable)
        XCTAssertEqual(ZoteroPolicy.availability(from: [:]), .unavailable)
    }

    func testHighlightTogglesRoundTrip() {
        var cfg = DigestConfig()
        cfg.highlightAuthors = false
        cfg.highlightTermsTitle = false
        XCTAssertFalse(cfg.highlightAuthors)
        XCTAssertFalse(cfg.highlightTermsTitle)
        // Persists through JSON.
        let data = try! JSONEncoder().encode(cfg)
        let decoded = try! JSONDecoder().decode(DigestConfig.self, from: data)
        XCTAssertFalse(decoded.highlightAuthors)
        XCTAssertEqual(decoded.color(for: .keyword), cfg.color(for: .keyword))
    }
}

final class APIClientZoteroTests: XCTestCase {
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

    func testSaveToZoteroPostsSnakeCaseBodyAndDecodes() async throws {
        MockURLProtocol.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.path, "/zotero/save")
            let bodyData = request.bodyData ?? Data()
            let obj = try XCTUnwrap(try JSONSerialization.jsonObject(with: bodyData) as? [String: Any])
            XCTAssertEqual(obj["arxiv_id"] as? String, "2601.1")
            XCTAssertEqual(obj["mode"] as? String, "web")
            let body = #"{"ok": true, "mode": "web", "message": "Saved to Zotero"}"#.data(using: .utf8)!
            let resp = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (resp, body)
        }
        let result = try await makeClient().saveToZotero(arxivId: "2601.1", mode: .web)
        XCTAssertTrue(result.ok)
        XCTAssertEqual(result.mode, "web")
    }
}
