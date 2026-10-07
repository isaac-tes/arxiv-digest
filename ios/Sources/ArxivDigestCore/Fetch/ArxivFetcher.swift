import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
#if canImport(FoundationXML)
import FoundationXML
#endif

/// Port of the engine's export-API past-week fetch (`fetch_pastweek`'s API
/// path, `fetch_feed_api`, `_api_get_with_retry`, `_paper_from_api_entry`).
/// The HTML `/pastweek` fallback is not ported: a failed feed becomes a notice.
public struct ArxivFetcher: Sendable {
    public struct HTTPStatusError: Error, Equatable, Sendable {
        public let status: Int
    }

    // HTTPS: App Transport Security blocks the engine's plain-HTTP endpoint.
    static let endpoint = URL(string: "https://export.arxiv.org/api/query")!
    public static let userAgent = "arxiv-digest (research tool; https://github.com/isaac-tes/arxiv-digest)"
    static let rateLimit: TimeInterval = 3
    static let maxRetries = 3
    static let maxBackoff: TimeInterval = 8
    static let retryBudget: TimeInterval = 30
    static let retryableStatus: Set<Int> = [429, 500, 502, 503, 504]

    let session: URLSession
    let sleep: @Sendable (TimeInterval) async throws -> Void
    let now: @Sendable () -> Date

    public init(
        session: URLSession = .shared,
        sleep: @escaping @Sendable (TimeInterval) async throws -> Void = { try await Task.sleep(nanoseconds: UInt64($0 * 1e9)) },
        now: @escaping @Sendable () -> Date = Date.init
    ) {
        self.session = session
        self.sleep = sleep
        self.now = now
    }

    // MARK: - Past week

    /// The last seven days of each feed, deduplicated by id across feeds
    /// (a parent `cond-mat` and its sub-categories share papers). Once the API
    /// fails for one feed the rest are skipped, as the engine stops using it.
    public func fetchPastweek(_ feeds: [String]) async throws -> LiveSource.RawFetch {
        let end = now(), start = end.addingTimeInterval(-7 * 86_400)
        let names = feeds.filter { !$0.hasPrefix("http") }  // URL feeds only work on the HTML path
        var papers: [RawPaper] = [], seen = Set<String>(), failed: [String] = []
        for (i, name) in names.enumerated() {
            if !failed.isEmpty { failed.append(name); continue }
            do {
                for p in try await fetchCategory(name, start: start, end: end) where seen.insert(p.id).inserted {
                    papers.append(p)
                }
            } catch is CancellationError {
                throw CancellationError()
            } catch {
                failed.append(name)
                continue
            }
            if i < names.count - 1 { try await sleep(Self.rateLimit) }
        }
        let notices = failed.isEmpty ? [] : [
            "arXiv export API was rate-limited or timed out; could not fetch: \(failed.joined(separator: ", ")). "
                + "Pull to refresh to try again.",
        ]
        return LiveSource.RawFetch(papers: papers, notices: notices, fetchedAt: end)
    }

    /// `fetch_feed_api`: papers in `category` submitted within [start, end].
    public func fetchCategory(_ category: String, start: Date, end: Date,
                              pageSize: Int = 500, maxResults: Int = 2000) async throws -> [RawPaper] {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(identifier: "UTC")
        f.dateFormat = "yyyyMMddHHmm"
        let query = "cat:\(category) AND submittedDate:[\(f.string(from: start)) TO \(f.string(from: end))]"
        var papers: [RawPaper] = []
        var offset = 0
        while true {
            let data = try await get([
                "search_query": query, "start": "\(offset)", "max_results": "\(pageSize)",
                "sortBy": "submittedDate", "sortOrder": "descending",
            ])
            let (total, entries) = try Self.parse(data)
            papers += entries
            if entries.isEmpty || papers.count >= total || papers.count >= maxResults { break }
            offset += pageSize
            try await sleep(Self.rateLimit)
        }
        return papers
    }

    /// `_api_get_with_retry`: retry 429/5xx and transport errors, honouring
    /// `Retry-After`, else backing off from 3 s (capped at 8 s, 4 attempts,
    /// 30 s budget).
    func get(_ params: [String: String]) async throws -> Data {
        var components = URLComponents(url: Self.endpoint, resolvingAgainstBaseURL: false)!
        components.queryItems = params.sorted { $0.key < $1.key }.map { URLQueryItem(name: $0.key, value: $0.value) }
        var request = URLRequest(url: components.url!, timeoutInterval: 60)
        request.setValue(Self.userAgent, forHTTPHeaderField: "User-Agent")

        let deadline = now().addingTimeInterval(Self.retryBudget)
        var lastError: Error = URLError(.unknown)
        for attempt in 0...Self.maxRetries {
            let backoff = min(Self.rateLimit * pow(2, Double(attempt)), Self.maxBackoff)
            let delay: TimeInterval
            do {
                let (data, response) = try await session.data(for: request)
                let status = (response as? HTTPURLResponse)?.statusCode ?? 0
                if (200..<300).contains(status) { return data }
                guard Self.retryableStatus.contains(status) else { throw HTTPStatusError(status: status) }
                lastError = HTTPStatusError(status: status)
                let header = (response as? HTTPURLResponse)?.value(forHTTPHeaderField: "Retry-After")
                delay = header.flatMap(Double.init).map { max($0, 0) } ?? backoff
            } catch let e as URLError where e.code != .cancelled {
                lastError = e
                delay = backoff
            }
            if attempt == Self.maxRetries || now().addingTimeInterval(delay) >= deadline { break }
            try await sleep(delay)
        }
        throw lastError
    }

    // MARK: - Atom parsing

    /// The page's `opensearch:totalResults` and its entries as engine paper
    /// dicts (`_paper_from_api_entry`).
    public static func parse(_ data: Data) throws -> (total: Int, papers: [RawPaper]) {
        let (total, entries) = try parseEntries(data)
        return (total, entries.map(\.paper))
    }

    static func parseEntries(_ data: Data) throws -> (total: Int, entries: [(paper: RawPaper, published: String)]) {
        let delegate = AtomParser()
        let parser = XMLParser(data: data)
        parser.shouldProcessNamespaces = true
        parser.delegate = delegate
        guard parser.parse() else { throw parser.parserError ?? URLError(.cannotParseResponse) }
        return (delegate.total, delegate.entries)
    }

    /// One paper by id (`zotero_bridge.fetch_arxiv_atom` + `_paper_from_api_entry`),
    /// with its `published` timestamp; nil when arXiv has no such paper.
    public func fetchPaper(_ id: String) async throws -> (paper: RawPaper, published: String)? {
        let data = try await get(["id_list": id, "max_results": "1"])
        guard let (_, entries) = try? Self.parseEntries(data), let first = entries.first,
              !first.paper.id.isEmpty else { return nil }  // arXiv's error entry has no /abs/ id
        return first
    }

    /// "Thu, 20 Aug 2026" in UTC (`_api_day_label`).
    static func dayLabel(published: String) -> String {
        guard let date = ISO8601DateFormatter().date(from: published) else { return "" }
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(identifier: "UTC")
        f.dateFormat = "EEE, dd MMM yyyy"
        return f.string(from: date)
    }
}

/// SAX state for an export-API page. Only Atom-namespace children of
/// `<entry>` count (like ElementTree's `entry.find(atom + tag)`), so
/// `arxiv:primary_category` or `arxiv:affiliation` never leak in.
private final class AtomParser: NSObject, XMLParserDelegate {
    static let atom = "http://www.w3.org/2005/Atom"
    static let opensearch = "http://a9.com/-/spec/opensearch/1.1/"

    var total = 0
    var entries: [(paper: RawPaper, published: String)] = []

    private var path: [String] = []
    private var text = ""
    private var fields: [String: String] = [:]
    private var authors: [String] = []
    private var categories: [String] = []

    func parser(_ parser: XMLParser, didStartElement name: String, namespaceURI: String?,
                qualifiedName: String?, attributes: [String: String] = [:]) {
        let tag = (namespaceURI == Self.atom ? "" : (namespaceURI ?? "") + "|") + name
        path.append(tag)
        text = ""
        if path == ["feed", "entry"] {
            fields = [:]; authors = []; categories = []
        } else if path == ["feed", "entry", "category"], let term = attributes["term"], !term.isEmpty {
            categories.append(term)
        }
    }

    func parser(_ parser: XMLParser, foundCharacters string: String) { text += string }

    func parser(_ parser: XMLParser, foundCDATA block: Data) { text += String(decoding: block, as: UTF8.self) }

    func parser(_ parser: XMLParser, didEndElement name: String, namespaceURI: String?, qualifiedName: String?) {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        switch path {
        case ["feed", Self.opensearch + "|totalResults"]:
            total = Int(trimmed) ?? 0
        case ["feed", "entry", "author", "name"] where !text.isEmpty:
            authors.append(trimmed)
        case let p where p.count == 3 && p[1] == "entry" && ["id", "title", "summary", "published"].contains(p[2]):
            if fields[p[2]] == nil { fields[p[2]] = trimmed }  // first match, like find()
        case ["feed", "entry"]:
            entries.append((paper(), fields["published"] ?? ""))
        default:
            break
        }
        path.removeLast()
        text = ""
    }

    private func paper() -> RawPaper {
        let versioned = fields["id"] ?? ""
        let url = versioned.replacingOccurrences(of: "v\\d+$", with: "", options: .regularExpression)
        let id = url.range(of: "/abs/", options: .backwards).map { String(url[$0.upperBound...]) } ?? ""
        return RawPaper(
            id: id, title: fields["title"] ?? "", authors: authors.joined(separator: ", "),
            abstract: fields["summary"] ?? "", subjects: categories.joined(separator: ", "),
            link: url, section: ArxivFetcher.dayLabel(published: fields["published"] ?? ""))
    }
}
