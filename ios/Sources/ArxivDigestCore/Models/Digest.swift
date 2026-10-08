import Foundation

/// The ranked digest view from `GET /digest` (ADR 0008).
///
/// Mirrors the web GUI's Papers tab: the top-N after the replacement/day
/// filters and the user's removals, plus what the caption and the
/// "Removed papers" section need. Every field beyond `papers` /
/// `total_papers` / `requested_top` decodes with a default, so an older server
/// still works.
public struct Digest: Codable, Sendable, Equatable {
    public let papers: [Paper]
    /// Papers left after filters and removals ("shown" in the GUI caption).
    public let totalPapers: Int
    public let requestedTop: Int
    /// Everything the fetch returned, before any filter.
    public let fetchedPapers: Int
    /// Dropped by the replacement or day filter.
    public let hiddenByFilters: Int
    /// Removed papers that would otherwise be in this ranking (restorable).
    public let removed: [Paper]
    /// Announcement days present in the fetch, chronological.
    public let availableDays: [String]
    /// The day applied, or nil for all days.
    public let day: String?
    public let timeframe: String
    public let feeds: [String]
    /// Warnings about a degraded fetch.
    public let notices: [String]
    /// ISO-8601 time of the underlying arXiv fetch (server clock).
    public let fetchedAt: String?

    enum CodingKeys: String, CodingKey {
        case papers
        case totalPapers = "total_papers"
        case requestedTop = "requested_top"
        case fetchedPapers = "fetched_papers"
        case hiddenByFilters = "hidden_by_filters"
        case removed
        case availableDays = "available_days"
        case day, timeframe, feeds, notices
        case fetchedAt = "fetched_at"
    }

    public init(
        papers: [Paper],
        totalPapers: Int,
        requestedTop: Int,
        fetchedPapers: Int? = nil,
        hiddenByFilters: Int = 0,
        removed: [Paper] = [],
        availableDays: [String] = [],
        day: String? = nil,
        timeframe: String = "pastweek",
        feeds: [String] = [],
        notices: [String] = [],
        fetchedAt: String? = nil
    ) {
        self.papers = papers
        self.totalPapers = totalPapers
        self.requestedTop = requestedTop
        self.fetchedPapers = fetchedPapers ?? totalPapers
        self.hiddenByFilters = hiddenByFilters
        self.removed = removed
        self.availableDays = availableDays
        self.day = day
        self.timeframe = timeframe
        self.feeds = feeds
        self.notices = notices
        self.fetchedAt = fetchedAt
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        papers = try c.decode([Paper].self, forKey: .papers)
        totalPapers = try c.decode(Int.self, forKey: .totalPapers)
        requestedTop = try c.decode(Int.self, forKey: .requestedTop)
        fetchedPapers = try c.decodeIfPresent(Int.self, forKey: .fetchedPapers) ?? totalPapers
        hiddenByFilters = try c.decodeIfPresent(Int.self, forKey: .hiddenByFilters) ?? 0
        removed = try c.decodeIfPresent([Paper].self, forKey: .removed) ?? []
        availableDays = try c.decodeIfPresent([String].self, forKey: .availableDays) ?? []
        day = try c.decodeIfPresent(String.self, forKey: .day)
        timeframe = try c.decodeIfPresent(String.self, forKey: .timeframe) ?? "pastweek"
        feeds = try c.decodeIfPresent([String].self, forKey: .feeds) ?? []
        notices = try c.decodeIfPresent([String].self, forKey: .notices) ?? []
        fetchedAt = try c.decodeIfPresent(String.self, forKey: .fetchedAt)
    }

    /// `fetchedAt` parsed (with or without fractional seconds / zone).
    public var fetchedDate: Date? {
        guard let fetchedAt else { return nil }
        return ISODate.parse(fetchedAt)
    }

    /// The GUI's Papers caption, given how many papers the search left.
    /// e.g. "Showing 3 of 20 ranked (out of 180 shown / 200 fetched). 20 hidden
    /// by replacement/day filters. 1 removed by you."
    public func caption(showing: Int) -> String {
        var text = "Showing \(showing) of \(papers.count) ranked "
            + "(out of \(totalPapers) shown / \(fetchedPapers) fetched)."
        if hiddenByFilters > 0 { text += " \(hiddenByFilters) hidden by replacement/day filters." }
        if !removed.isEmpty { text += " \(removed.count) removed by you." }
        return text
    }
}

/// Lenient ISO-8601 parsing for server timestamps (Python's `isoformat()`
/// emits microseconds and may omit the zone).
public enum ISODate {
    public static func parse(_ s: String) -> Date? {
        let withFraction = ISO8601DateFormatter()
        withFraction.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = withFraction.date(from: s) { return d }
        let plain = ISO8601DateFormatter()
        plain.formatOptions = [.withInternetDateTime]
        if let d = plain.date(from: s) { return d }
        // No zone designator: treat as UTC.
        if !s.hasSuffix("Z"), !s.contains("+") {
            return parse(s + "Z")
        }
        return nil
    }
}
