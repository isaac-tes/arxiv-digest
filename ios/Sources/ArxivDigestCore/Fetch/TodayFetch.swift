import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

/// Where Standalone mode gets "today" (S7). Both exist so they can be compared
/// on the phone; Settings picks one.
public enum TodaySource: String, CaseIterable, Sendable {
    /// (a) The engine's way: scrape each feed's HTML `/new` listing (New /
    /// Cross / Replacement sections), back-filling missing abstracts.
    case listing
    /// (b) The export API over arXiv's last announcement window; "cross" is
    /// derived from the primary category, and there are no replacements.
    case api

    public var label: String {
        switch self {
        case .listing: return "arXiv listing"
        case .api: return "Export API"
        }
    }
}

extension ArxivFetcher {
    // MARK: - (a) HTML /new listing

    /// `fetch_feeds` over each feed's `/new` URL (`feed_url(…, "today")`),
    /// deduplicated by id. Any page failing fails the fetch, like the server.
    /// Abstracts are back-filled once over the deduplicated set (the engine
    /// back-fills per feed; same result, fewer requests).
    public func fetchTodayListing(_ feeds: [String], config: DigestConfig) async throws -> LiveSource.RawFetch {
        let known = config.feeds
        var papers: [RawPaper] = [], seen = Set<String>()
        for name in feeds {
            let url = known[name].map { Self.todayURL($0) } ?? name
            for p in Self.parseListing(try await page(url)) where seen.insert(p.id).inserted {
                papers.append(p)
            }
        }
        await backfillAbstracts(&papers)
        return LiveSource.RawFetch(papers: papers, fetchedAt: now())
    }

    /// `feed_url(url, "today")`: a trailing `/new`, `/recent` or `/pastweek` becomes `/new`.
    static func todayURL(_ url: String) -> String {
        for old in ["/new", "/recent", "/pastweek"] where url.hasSuffix(old) {
            return String(url.dropLast(old.count)) + "/new"
        }
        return url
    }

    func page(_ url: String) async throws -> Data {
        guard let u = URL(string: url) else { throw URLError(.badURL) }
        var request = URLRequest(url: u, timeoutInterval: 30)
        request.setValue(Self.userAgent, forHTTPHeaderField: "User-Agent")
        let (data, response) = try await session.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else { throw HTTPStatusError(status: status) }
        return data
    }

    /// Port of `fetch_feed`'s parsing: for each `<h3>` section, its sibling
    /// `<dt>`/`<dd>` pairs (zipped by position) up to the next `<h3>`.
    public static func parseListing(_ data: Data) -> [RawPaper] {
        let root = HTMLNode.parse(String(decoding: data, as: UTF8.self))
        let headers = root.findAll("h3")
        var papers: [RawPaper] = []
        for (i, h3) in headers.enumerated() {
            guard let parent = h3.parent else { continue }
            let section = h3.text(separator: "")
            let stop = i + 1 < headers.count ? headers[i + 1] : nil
            var dts: [HTMLNode] = [], dds: [HTMLNode] = []
            for node in parent.children[(parent.children.firstIndex { $0 === h3 }! + 1)...] {
                if node === stop { break }
                if node.name == "dt" { dts.append(node) } else if node.name == "dd" { dds.append(node) }
            }
            for (dt, dd) in zip(dts, dds) {
                guard let a = dt.descendants.first(where: { $0.name == "a" && $0.attributes["title"] == "Abstract" })
                else { continue }
                let href = a.attributes["href"] ?? ""
                let raw = href.contains("/abs/")
                    ? String(href[href.range(of: "/abs/", options: .backwards)!.upperBound...])
                    : a.text(separator: "")
                func div(_ cls: String, _ label: String) -> String {
                    guard let d = dd.find("div", class: cls) else { return "" }
                    return d.text(separator: " ").replacingOccurrences(of: label, with: "")
                        .trimmingCharacters(in: .whitespacesAndNewlines)
                }
                let title = div("list-title", "Title:")
                let authors = div("list-authors", "Authors:")
                let subjects = div("list-subjects", "Subjects:")
                // /new inlines the abstract as <p class="mathjax">; else the first
                // substantial <p> that isn't text already captured.
                var abstract = dd.find("p", class: "mathjax")?.text(separator: " ") ?? ""
                if dd.find("p", class: "mathjax") == nil {
                    let known: Set<String> = [title, authors, subjects]
                    abstract = dd.findAll("p").map { $0.text(separator: " ") }
                        .first { $0.count > 20 && !known.contains($0) } ?? ""
                }
                papers.append(RawPaper(
                    id: stripArxivPrefix(raw), title: title, authors: authors,
                    abstract: stripAbstractLabel(abstract), subjects: subjects,
                    link: "https://arxiv.org" + href, section: section))
            }
        }
        return papers
    }

    /// `section_category`: new | cross | replacement | other.
    public static func sectionCategory(_ section: String) -> String {
        let s = section.lowercased()
        if s.contains("replacement") { return "replacement" }
        if s.contains("cross") { return "cross" }
        if s.contains("new submission") { return "new" }
        return "other"
    }

    static func stripArxivPrefix(_ s: String) -> String {
        s.replacingOccurrences(of: "^\\s*arxiv\\s*:\\s*", with: "", options: [.regularExpression, .caseInsensitive])
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    static func stripAbstractLabel(_ s: String) -> String {
        s.replacingOccurrences(of: "^\\s*abstract\\s*:\\s*", with: "", options: [.regularExpression, .caseInsensitive])
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// `_backfill_missing_abstracts`: fetch empty abstracts, ten at a time.
    func backfillAbstracts(_ papers: inout [RawPaper]) async {
        let missing = papers.indices.filter { papers[$0].abstract.isEmpty }
        for chunk in stride(from: 0, to: missing.count, by: 10).map({ Array(missing[$0..<min($0 + 10, missing.count)]) }) {
            let found = await withTaskGroup(of: (Int, String).self) { group in
                for i in chunk {
                    let id = papers[i].id
                    group.addTask { (i, await fetchAbstract(id)) }
                }
                return await group.reduce(into: [:]) { $0[$1.0] = $1.1 }
            }
            for (i, abstract) in found { papers[i].abstract = abstract }
        }
    }

    /// `fetch_abstract`: the `/abs/` page's abstract, two retries, "" on failure.
    func fetchAbstract(_ id: String) async -> String {
        let clean = Self.stripArxivPrefix(id)
        guard !clean.isEmpty else { return "" }
        for attempt in 0...2 {
            if let data = try? await page("https://arxiv.org/abs/\(clean)") {
                return Self.abstract(fromAbsPage: data)
            }
            if attempt < 2 { try? await sleep(0.5 * Double(attempt + 1)) }
        }
        return ""
    }

    /// `fetch_abstract`'s parse: `blockquote.abstract`, else `div.abstract`.
    static func abstract(fromAbsPage data: Data) -> String {
        let root = HTMLNode.parse(String(decoding: data, as: UTF8.self))
        guard let block = root.find("blockquote", class: "abstract") ?? root.find("div", class: "abstract") else { return "" }
        return stripAbstractLabel(block.text(separator: " "))
    }

    // MARK: - (b) Export API

    /// The export API for submissions in arXiv's last announced batch, per
    /// feed, paced like the past-week fetch. A paper whose primary category is
    /// under the feed is a new submission, else a cross-list (first feed wins).
    public func fetchTodayAPI(_ feeds: [String]) async throws -> LiveSource.RawFetch {
        let window = Self.announcementWindow(now: now())
        let names = feeds.filter { !$0.hasPrefix("http") }
        var papers: [RawPaper] = [], seen = Set<String>()
        for (i, name) in names.enumerated() {
            for (paper, primary) in try await fetchCategoryEntries(name, start: window.start, end: window.end)
            where seen.insert(paper.id).inserted {
                var p = paper
                p.section = primary.lowercased().hasPrefix(name.lowercased()) ? "New submissions" : "Cross submissions"
                papers.append(p)
            }
            if i < names.count - 1 { try await sleep(Self.rateLimit) }
        }
        return LiveSource.RawFetch(papers: papers, fetchedAt: now())
    }

    /// The submission window of arXiv's most recently announced batch:
    /// cutoffs are 14:00 US Eastern Mon–Fri, each announced 20:00 the same day
    /// (Friday's on Sunday). Returns (previous cutoff, cutoff].
    /// ponytail: ignores arXiv holidays; a holiday week shifts the window by a day.
    static func announcementWindow(now: Date) -> (start: Date, end: Date) {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "America/New_York")!
        func cutoff(onDayOf d: Date) -> Date { cal.date(bySettingHour: 14, minute: 0, second: 0, of: d)! }
        func isWeekday(_ d: Date) -> Bool { !(cal.component(.weekday, from: d) == 1 || cal.component(.weekday, from: d) == 7) }
        func announced(_ c: Date) -> Date {
            let days = cal.component(.weekday, from: c) == 6 ? 2 : 0  // Friday → Sunday
            return cal.date(byAdding: .hour, value: 6, to: cal.date(byAdding: .day, value: days, to: c)!)!
        }
        func previousCutoff(before c: Date) -> Date {
            var d = cal.date(byAdding: .day, value: -1, to: c)!
            while !isWeekday(d) { d = cal.date(byAdding: .day, value: -1, to: d)! }
            return cutoff(onDayOf: d)
        }
        var c = cutoff(onDayOf: now)
        if !isWeekday(c) || c > now { c = previousCutoff(before: c) }
        while announced(c) > now { c = previousCutoff(before: c) }
        return (previousCutoff(before: c), c)
    }
}
