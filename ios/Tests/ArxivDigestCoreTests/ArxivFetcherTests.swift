import XCTest
@testable import ArxivDigestCore
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

/// The export-API fetch, network-free: `MockURLProtocol` serves invented Atom
/// pages and sleeps are recorded instead of waited.
final class ArxivFetcherTests: XCTestCase {
    struct Expected: Decodable {
        let atom: String
        let total: Int
        let papers: [RawPaper]
    }

    private let expected = try! JSONDecoder().decode(Expected.self, from: Data(FetchParityFixture.json.utf8))
    private var sleeps: Recorder<TimeInterval>!
    private var fetcher: ArxivFetcher!

    override func setUp() {
        super.setUp()
        MockURLProtocol.reset()
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockURLProtocol.self]
        let sleeps = Recorder<TimeInterval>()
        self.sleeps = sleeps
        fetcher = ArxivFetcher(session: URLSession(configuration: config), sleep: { sleeps.add($0) })
    }

    /// An Atom page with `total` results whose entries are `ids`.
    static func page(total: Int, ids: [String]) -> Data {
        let entries = ids.map {
            "<entry><id>http://arxiv.org/abs/\($0)v1</id><published>2026-10-05T10:00:00Z</published>"
                + "<title>Paper \($0)</title><summary>S.</summary><author><name>Ada Example</name></author>"
                + "<category term=\"quant-ph\"/></entry>"
        }.joined()
        return Data(("<feed xmlns=\"http://www.w3.org/2005/Atom\" xmlns:opensearch=\"http://a9.com/-/spec/opensearch/1.1/\">"
            + "<opensearch:totalResults>\(total)</opensearch:totalResults>\(entries)</feed>").utf8)
    }

    static func response(_ r: URLRequest, _ status: Int = 200, headers: [String: String] = [:]) -> HTTPURLResponse {
        HTTPURLResponse(url: r.url!, statusCode: status, httpVersion: nil, headerFields: headers)!
    }

    static func query(_ r: URLRequest) -> [String: String] {
        Dictionary(uniqueKeysWithValues: (URLComponents(url: r.url!, resolvingAgainstBaseURL: false)?.queryItems ?? [])
            .map { ($0.name, $0.value ?? "") })
    }

    func testParseMatchesEnginePaperFromApiEntry() throws {
        let (total, papers) = try ArxivFetcher.parse(Data(expected.atom.utf8))
        XCTAssertEqual(total, expected.total)
        XCTAssertEqual(papers, expected.papers)
    }

    func testQueryShapeAndPagination() async throws {
        let requests = Recorder<URLRequest>()
        MockURLProtocol.handler = { r in
            requests.add(r)
            let start = Int(Self.query(r)["start"]!)!
            let ids = start == 0 ? ["2610.00001", "2610.00002"] : ["2610.00003"]
            return (Self.response(r), Self.page(total: 3, ids: ids))
        }
        let start = Date(timeIntervalSince1970: 1_790_000_000)  // 2026-09-21 14:13 UTC
        let papers = try await fetcher.fetchCategory("quant-ph", start: start,
                                                     end: start.addingTimeInterval(7 * 86_400), pageSize: 2)
        XCTAssertEqual(papers.map(\.id), ["2610.00001", "2610.00002", "2610.00003"])
        let q = Self.query(requests.values[0])
        XCTAssertEqual(q["search_query"], "cat:quant-ph AND submittedDate:[202609211413 TO 202609281413]")
        XCTAssertEqual(q["sortBy"], "submittedDate")
        XCTAssertEqual(q["sortOrder"], "descending")
        XCTAssertEqual(q["max_results"], "2")
        XCTAssertEqual(Self.query(requests.values[1])["start"], "2")
        XCTAssertEqual(requests.values[0].value(forHTTPHeaderField: "User-Agent"), ArxivFetcher.userAgent)
        XCTAssertEqual(requests.values[0].url?.host, "export.arxiv.org")
        XCTAssertEqual(sleeps.values, [3])  // paced between pages
    }

    func testRetriesRateLimitHonouringRetryAfter() async throws {
        let calls = Counter()
        MockURLProtocol.handler = { r in
            calls.bump()
            switch calls.value {
            case 1: return (Self.response(r, 429, headers: ["Retry-After": "5"]), Data())
            case 2: return (Self.response(r, 503), Data())
            default: return (Self.response(r), Self.page(total: 1, ids: ["2610.00001"]))
            }
        }
        let papers = try await fetcher.fetchCategory("quant-ph", start: Date(), end: Date())
        XCTAssertEqual(papers.count, 1)
        XCTAssertEqual(sleeps.values, [5, 6])  // Retry-After, then backoff 3 * 2^1
    }

    func testGivesUpAfterRetries() async throws {
        MockURLProtocol.handler = { r in (Self.response(r, 429), Data()) }
        do {
            _ = try await fetcher.fetchCategory("quant-ph", start: Date(), end: Date())
            XCTFail("expected an error")
        } catch {
            XCTAssertEqual(error as? ArxivFetcher.HTTPStatusError, .init(status: 429))
        }
        XCTAssertEqual(sleeps.values, [3, 6, 8])  // capped at 8 s, four attempts
    }

    func testNonRetryableStatusFailsFast() async throws {
        MockURLProtocol.handler = { r in (Self.response(r, 400), Data()) }
        do {
            _ = try await fetcher.fetchCategory("quant-ph", start: Date(), end: Date())
            XCTFail("expected an error")
        } catch {
            XCTAssertEqual(error as? ArxivFetcher.HTTPStatusError, .init(status: 400))
        }
        XCTAssertEqual(sleeps.values, [])
    }

    func testPastweekDedupesAcrossFeedsAndPaces() async throws {
        MockURLProtocol.handler = { r in
            let q = Self.query(r)["search_query"]!
            let ids = q.hasPrefix("cat:cond-mat ") ? ["2610.00001", "2610.00002"] : ["2610.00002", "2610.00003"]
            return (Self.response(r), Self.page(total: 2, ids: ids))
        }
        let result = try await fetcher.fetchPastweek(["cond-mat", "cond-mat.quant-gas"])
        XCTAssertEqual(result.papers.map(\.id), ["2610.00001", "2610.00002", "2610.00003"])
        XCTAssertEqual(result.notices, [])
        XCTAssertEqual(sleeps.values, [3])  // between feeds
    }

    func testPastweekReportsFailureAsNotice() async throws {
        MockURLProtocol.handler = { r in
            if Self.query(r)["search_query"]!.hasPrefix("cat:quant-ph ") {
                return (Self.response(r), Self.page(total: 1, ids: ["2610.00001"]))
            }
            throw URLError(.timedOut)
        }
        let result = try await fetcher.fetchPastweek(["quant-ph", "cond-mat", "cond-mat.mes-hall"])
        XCTAssertEqual(result.papers.map(\.id), ["2610.00001"])
        XCTAssertEqual(result.notices, [
            "arXiv export API was rate-limited or timed out; could not fetch: cond-mat, cond-mat.mes-hall. "
                + "Pull to refresh to try again.",
        ])
    }
}

final class Recorder<T>: @unchecked Sendable {
    private let lock = NSLock()
    private var items: [T] = []
    var values: [T] { lock.withLock { items } }
    func add(_ v: T) { lock.withLock { items.append(v) } }
}
