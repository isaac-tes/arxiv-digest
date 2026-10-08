import XCTest
@testable import ArxivDigestCore
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

/// S7, both variants of Standalone's "today" feed: (a) the engine's HTML `/new`
/// parser (parity with `fetch_feed` / `fetch_abstract`) and (b) the export API
/// over arXiv's last announcement window.
final class TodayFetchTests: XCTestCase {
    struct Expected: Decodable {
        let new_page: String
        let papers: [RawPaper]
        let categories: [String]
        let abs_pages: [String: String]
        let abstracts: [String: String]
    }

    private let expected = try! JSONDecoder().decode(Expected.self, from: Data(TodayParityFixture.json.utf8))
    private var fetcher: ArxivFetcher!

    override func setUp() {
        super.setUp()
        MockURLProtocol.reset()
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockURLProtocol.self]
        fetcher = ArxivFetcher(session: URLSession(configuration: config), sleep: { _ in })
    }

    // MARK: (a) HTML /new

    func testNewPageParseMatchesEngineFetchFeed() {
        let papers = ArxivFetcher.parseListing(Data(expected.new_page.utf8))
        XCTAssertEqual(papers, expected.papers)
        XCTAssertEqual(papers.map { ArxivFetcher.sectionCategory($0.section) }, expected.categories)
    }

    func testAbstractPageParseMatchesEngineFetchAbstract() {
        for (id, page) in expected.abs_pages {
            XCTAssertEqual(ArxivFetcher.abstract(fromAbsPage: Data(page.utf8)), expected.abstracts[id], id)
        }
    }

    func testTodayListingFetchesEachFeedDedupesAndBackfills() async throws {
        let pages = expected.abs_pages, newPage = Data(expected.new_page.utf8)
        let requests = Recorder<String>()
        MockURLProtocol.handler = { r in
            let url = r.url!.absoluteString
            requests.add(url)
            let ok = HTTPURLResponse(url: r.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            if url.contains("/list/") { return (ok, newPage) }
            let id = String(url.split(separator: "/").last!)
            return (ok, Data((pages[id] ?? "<html></html>").utf8))
        }
        var cfg = DigestConfig()
        cfg.feeds = ["quant-ph": "https://arxiv.org/list/quant-ph/pastweek", "cond-mat": "https://arxiv.org/list/cond-mat/new"]
        let result = try await fetcher.fetchTodayListing(["quant-ph", "cond-mat"], config: cfg)
        XCTAssertEqual(result.papers.map(\.id), expected.papers.map(\.id))  // second feed's copies deduped
        XCTAssertTrue(requests.values.contains("https://arxiv.org/list/quant-ph/new"))  // /pastweek rewritten
        XCTAssertTrue(requests.values.contains("https://arxiv.org/list/cond-mat/new"))
        // Only the replacement without an abstract is back-filled (once, despite two feeds).
        XCTAssertEqual(requests.values.filter { $0.contains("/abs/") }, ["https://arxiv.org/abs/2609.00001"])
        XCTAssertEqual(result.papers.last?.abstract, "")
    }

    func testTodayListingFailureThrows() async {
        MockURLProtocol.handler = { r in (HTTPURLResponse(url: r.url!, statusCode: 503, httpVersion: nil, headerFields: nil)!, Data()) }
        var cfg = DigestConfig()
        cfg.feeds = ["quant-ph": DigestConfig.listingURL(for: "quant-ph")]
        do {
            _ = try await fetcher.fetchTodayListing(["quant-ph"], config: cfg)
            XCTFail("expected an error")
        } catch {
            XCTAssertEqual(error as? ArxivFetcher.HTTPStatusError, .init(status: 503))
        }
    }
}
