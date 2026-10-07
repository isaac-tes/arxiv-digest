import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

/// Demo mode (CONTEXT.md): the shared `DigestRouter` over the bundled sample
/// digest, so the app runs without a server (for trying the UI and for
/// screenshots). Scores are the engine's, precomputed by
/// `ios/scripts/make_demo_fixture.py`; they do not react to config edits.
public final class DemoBackend: @unchecked Sendable {
    public static let shared = DemoBackend()

    struct Fixture: Decodable {
        let config: [String: JSONValue]
        let pastweek: [Paper]
        let today: [Paper]
        let days: [String]
        let presets: [String: DigestRouter.Preset]
    }

    // The fixture is generated and checked by a unit test; a decode failure
    // here is a build-time bug, not a runtime condition.
    static let fixture = try! JSONDecoder().decode(Fixture.self, from: Data(DemoFixture.json.utf8))

    private let lock = NSLock()
    private var current = DemoBackend.makeRouter()

    public var router: DigestRouter { lock.withLock { current } }

    /// Back to the bundled state (used by tests and "Reset demo").
    public func reset() {
        lock.withLock { current = Self.makeRouter() }
    }

    public func handle(method: String, url: URL, body: Data?) async -> DigestRouter.Response {
        await router.handle(method: method, url: url, body: body)
    }

    // Demo defaults are the demo config (the engine's defaults name real
    // people; the demo stays invented).
    private static func makeRouter() -> DigestRouter {
        DigestRouter(source: DemoSource(), config: fixture.config, defaults: fixture.config,
                     presets: fixture.presets)
    }
}

/// The fixture's papers, with their precomputed scores.
struct DemoSource: DigestSource {
    var mode: String { "demo" }
    var zoteroWebAvailable: Bool { true }

    private func papers(_ timeframe: String) -> [Paper] {
        timeframe == "today" ? DemoBackend.fixture.today : DemoBackend.fixture.pastweek
    }

    func fetch(timeframe: String, feeds: [String], config: DigestConfig, refresh: Bool) async throws -> SourceFetch {
        SourceFetch(papers: papers(timeframe), fetchedAt: Date().addingTimeInterval(-12 * 60))
    }

    func cached(timeframe: String, feeds: [String], config: DigestConfig) async -> SourceFetch? {
        SourceFetch(papers: papers(timeframe))
    }

    func lookup(id: String, timeframe: String, feeds: [String], config: DigestConfig) async throws -> SourceLookup? {
        let f = DemoBackend.fixture
        guard let p = (f.pastweek + f.today).first(where: { $0.id == id }) else { return nil }
        return SourceLookup(
            paper: ScoredPaper(id: p.id, title: p.title, authors: p.authors, link: p.link,
                               subjects: p.subjects, section: "", abstract: p.fullAbstract),
            breakdown: p.breakdown ?? ScoreBreakdown(signals: [:], total: p.score),
            notFetchedReason: "This paper was **not in the fetched set**. Deterministic check: it is outside the "
                + "\(timeframe == "today" ? "today" : "past-week") listing of your subscribed feeds.")
    }
}

/// Routes every request of a session to an in-process `DigestRouter`. Each
/// request runs in a `Task`; `stopLoading` cancels it.
public class RouterURLProtocol: URLProtocol, @unchecked Sendable {
    /// The router this protocol class answers from (overridden per mode).
    class var router: DigestRouter { fatalError("subclass must override") }
    /// The base URL clients use (never contacted).
    public class var baseURL: URL { fatalError("subclass must override") }

    /// A session whose requests never leave the device.
    public class func makeSession() -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [self]
        // Standalone's first past-week fetch paces arXiv requests (~10-40 s).
        config.timeoutIntervalForRequest = 300
        return URLSession(configuration: config)
    }

    private var loading: Task<Void, Never>?

    override public class func canInit(with request: URLRequest) -> Bool { true }
    override public class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override public func startLoading() {
        guard let url = request.url else {
            client?.urlProtocol(self, didFailWithError: URLError(.badURL))
            return
        }
        let router = Self.router
        let method = request.httpMethod ?? "GET", body = request.bodyData
        // URLProtocol isn't Sendable on Linux; the client calls are thread-safe.
        let box = UncheckedBox(value: self)
        loading = Task {
            let proto = box.value
            let r = await router.handle(method: method, url: url, body: body)
            guard !Task.isCancelled else { return }
            let response = HTTPURLResponse(url: url, statusCode: r.status, httpVersion: "HTTP/1.1",
                                           headerFields: ["Content-Type": "application/json"])!
            proto.client?.urlProtocol(proto, didReceive: response, cacheStoragePolicy: .notAllowed)
            proto.client?.urlProtocol(proto, didLoad: r.body)
            proto.client?.urlProtocolDidFinishLoading(proto)
        }
    }

    override public func stopLoading() { loading?.cancel() }
}

private struct UncheckedBox<T>: @unchecked Sendable { let value: T }

/// Demo mode's requests → `DemoBackend.shared`.
public final class DemoURLProtocol: RouterURLProtocol {
    override class var router: DigestRouter { DemoBackend.shared.router }
    override public class var baseURL: URL { URL(string: "https://demo.arxiv-digest.invalid")! }
}

extension URLRequest {
    /// The body even when `URLSession` moved it into `httpBodyStream`.
    var bodyData: Data? {
        if let httpBody { return httpBody }
        guard let stream = httpBodyStream else { return nil }
        stream.open()
        defer { stream.close() }
        var data = Data()
        let size = 4096
        let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: size)
        defer { buffer.deallocate() }
        while stream.hasBytesAvailable {
            let read = stream.read(buffer, maxLength: size)
            if read <= 0 { break }
            data.append(buffer, count: read)
        }
        return data
    }
}
