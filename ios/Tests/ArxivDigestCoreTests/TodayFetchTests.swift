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

    // MARK: (b) export API

    /// arXiv's schedule: 14:00 ET cutoffs Mon–Fri, announced 20:00 ET the same
    /// day (Friday's on Sunday). The window is the batch announced last.
    func testAnnouncementWindow() {
        let et = TimeZone(identifier: "America/New_York")!
        func date(_ s: String) -> Date {
            let f = DateFormatter()
            f.locale = Locale(identifier: "en_US_POSIX")
            f.timeZone = et
            f.dateFormat = "yyyy-MM-dd HH:mm"
            return f.date(from: s)!
        }
        func window(_ now: String) -> [Date] {
            let w = ArxivFetcher.announcementWindow(now: date(now))
            return [w.start, w.end]
        }
        // Tue 6 Oct 2026 21:00 ET: Tuesday's batch (Mon 14:00 → Tue 14:00).
        XCTAssertEqual(window("2026-10-06 21:00"), [date("2026-10-05 14:00"), date("2026-10-06 14:00")])
        // Tue 10:00 ET: still Monday's batch (Fri 14:00 → Mon 14:00).
        XCTAssertEqual(window("2026-10-06 10:00"), [date("2026-10-02 14:00"), date("2026-10-05 14:00")])
        // Saturday: Thursday's batch (Wed → Thu); Friday's comes out Sunday 20:00.
        XCTAssertEqual(window("2026-10-10 12:00"), [date("2026-10-07 14:00"), date("2026-10-08 14:00")])
        XCTAssertEqual(window("2026-10-11 20:30"), [date("2026-10-08 14:00"), date("2026-10-09 14:00")])
        // Daylight-saving switch (1 Nov 2026) keeps 14:00 local.
        XCTAssertEqual(window("2026-11-02 21:00"), [date("2026-10-30 14:00"), date("2026-11-02 14:00")])
    }

    func testTodayAPILabelsNewAndCrossByPrimaryCategory() async throws {
        let queries = Recorder<String>()
        MockURLProtocol.handler = { r in
            let q = ArxivFetcherTests.query(r)["search_query"]!
            queries.add(q)
            let entries: [(String, String)] = q.hasPrefix("cat:quant-ph ")
                ? [("2610.00001", "quant-ph"), ("2610.00002", "physics.optics")]
                : [("2610.00002", "cond-mat.str-el"), ("2610.00003", "cond-mat.quant-gas")]
            let body = entries.map { id, primary in
                "<entry><id>http://arxiv.org/abs/\(id)v1</id><published>2026-10-05T19:00:00Z</published><title>T \(id)</title>"
                    + "<summary>S.</summary><arxiv:primary_category term=\"\(primary)\"/><category term=\"\(primary)\"/></entry>"
            }.joined()
            let xml = "<feed xmlns=\"http://www.w3.org/2005/Atom\" xmlns:arxiv=\"http://arxiv.org/schemas/atom\" "
                + "xmlns:opensearch=\"http://a9.com/-/spec/opensearch/1.1/\"><opensearch:totalResults>\(entries.count)</opensearch:totalResults>\(body)</feed>"
            return (HTTPURLResponse(url: r.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, Data(xml.utf8))
        }
        let result = try await fetcher.fetchTodayAPI(["quant-ph", "cond-mat"])
        XCTAssertEqual(result.papers.map(\.id), ["2610.00001", "2610.00002", "2610.00003"])
        XCTAssertEqual(result.papers.map { ArxivFetcher.sectionCategory($0.section) }, ["new", "cross", "new"])
        XCTAssertTrue(queries.values[0].contains("submittedDate:["))
    }
}
