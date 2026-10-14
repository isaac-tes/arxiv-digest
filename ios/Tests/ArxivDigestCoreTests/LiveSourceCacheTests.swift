import XCTest
@testable import ArxivDigestCore

/// Standalone mode's fetch cache: kept until arXiv announces new papers, then a
/// cached past week is topped up instead of fetched again.
final class LiveSourceCacheTests: XCTestCase {
    /// A time in US Eastern, the zone arXiv announces in.
    static func eastern(_ y: Int, _ m: Int, _ d: Int, _ h: Int, _ min: Int = 0) -> Date {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "America/New_York")!
        return cal.date(from: DateComponents(year: y, month: m, day: d, hour: h, minute: min))!
    }

    static func paper(_ id: String) -> RawPaper {
        RawPaper(id: id, title: "Paper \(id)", authors: "A. Author", abstract: "Text.",
                 subjects: "Quantum Physics (quant-ph)", link: "https://arxiv.org/abs/\(id)", section: "")
    }

    final class Clock: @unchecked Sendable {
        private let lock = NSLock()
        private var t: Date
        init(_ t: Date) { self.t = t }
        var now: Date { lock.withLock { t } }
        func set(_ d: Date) { lock.withLock { t = d } }
    }

    // Oct 2026: Mon 12, Tue 13, Wed 14, Thu 15, Fri 16, Sat 17, Sun 18.
    func testNextAnnouncementIsEightPmEasternSundayToThursday() {
        let next = LiveSource.nextAnnouncement
        XCTAssertEqual(next(Self.eastern(2026, 10, 13, 10)), Self.eastern(2026, 10, 13, 20))  // Tue morning
        XCTAssertEqual(next(Self.eastern(2026, 10, 13, 21)), Self.eastern(2026, 10, 14, 20))  // Tue evening
        XCTAssertEqual(next(Self.eastern(2026, 10, 15, 21)), Self.eastern(2026, 10, 18, 20))  // Thu → Sun
        XCTAssertEqual(next(Self.eastern(2026, 10, 16, 12)), Self.eastern(2026, 10, 18, 20))  // Fri → Sun
        XCTAssertEqual(next(Self.eastern(2026, 10, 18, 19, 59)), Self.eastern(2026, 10, 18, 20))  // Sun
    }

    func testNoRefetchUntilArxivAnnouncesThenOnlyATopUp() async throws {
        let clock = Clock(Self.eastern(2026, 10, 13, 10))
        let full = Counter(), tops = Counter()
        let sinceSeen = Clock(.distantPast)
        let source = LiveSource(
            fetcher: { _, _, _ in
                full.bump()
                return .init(papers: [Self.paper("old")], fetchedAt: clock.now,
                             submitted: ["old": clock.now.addingTimeInterval(-86_400)])
            },
            update: { _, since in
                tops.bump()
                sinceSeen.set(since)
                return .init(papers: [Self.paper("new")], fetchedAt: clock.now, submitted: ["new": clock.now])
            },
            now: { clock.now })
        let cfg = DigestConfig()

        _ = try await source.fetch(timeframe: "pastweek", feeds: ["quant-ph"], config: cfg, refresh: false)
        clock.set(Self.eastern(2026, 10, 13, 19))  // reopened before the 20:00 announcement
        _ = try await source.fetch(timeframe: "pastweek", feeds: ["quant-ph"], config: cfg, refresh: false)
        XCTAssertEqual(full.value, 1)
        XCTAssertEqual(tops.value, 0)

        clock.set(Self.eastern(2026, 10, 14, 8))  // next morning: only the latest days are asked for
        let topped = try await source.fetch(timeframe: "pastweek", feeds: ["quant-ph"], config: cfg, refresh: false)
        XCTAssertEqual(full.value, 1)
        XCTAssertEqual(tops.value, 1)
        XCTAssertEqual(Set(topped.papers.map(\.id)), ["old", "new"])
        XCTAssertEqual(sinceSeen.now, Self.eastern(2026, 10, 13, 10).addingTimeInterval(-LiveSource.announcementLag))

        // A pull to refresh tops up too, rather than fetching the whole week again.
        _ = try await source.fetch(timeframe: "pastweek", feeds: ["quant-ph"], config: cfg, refresh: true)
        XCTAssertEqual(full.value, 1)
        XCTAssertEqual(tops.value, 2)
    }

    func testTopUpKeepsTheWeekExact() {
        let fetchedAt = Self.eastern(2026, 10, 14, 8)
        let old = LiveSource.RawFetch(
            papers: [Self.paper("a"), Self.paper("b"), Self.paper("c")],
            notices: ["old notice"], fetchedAt: fetchedAt.addingTimeInterval(-86_400),
            submitted: [
                "a": fetchedAt.addingTimeInterval(-8 * 86_400),  // left the week: dropped
                "b": fetchedAt.addingTimeInterval(-3 * 86_400),  // still in: kept
                "c": fetchedAt.addingTimeInterval(-2 * 86_400),  // fetched again: the new copy wins
            ])
        var newC = Self.paper("c")
        newC.section = "Wed, 14 Oct 2026"
        let delta = LiveSource.RawFetch(papers: [Self.paper("d"), newC], fetchedAt: fetchedAt,
                                        submitted: ["d": fetchedAt, "c": fetchedAt.addingTimeInterval(-2 * 86_400)])
        let merged = LiveSource.merged(old, delta)
        XCTAssertEqual(merged.papers.map(\.id), ["d", "c", "b"])
        XCTAssertEqual(merged.papers[1].section, "Wed, 14 Oct 2026")
        XCTAssertEqual(merged.notices, [])
        XCTAssertEqual(merged.fetchedAt, fetchedAt)
        XCTAssertEqual(Set(merged.submitted!.keys), ["b", "c", "d"])
    }

    func testIncompleteOrOldCachesAreFetchedAgainInFull() async throws {
        let clock = Clock(Self.eastern(2026, 10, 13, 10))
        let full = Counter(), tops = Counter()
        let notices = Clock(Date(timeIntervalSince1970: 1))  // 1: the full fetch reports a failed feed
        let source = LiveSource(
            fetcher: { _, _, _ in
                full.bump()
                let failed = notices.now == Date(timeIntervalSince1970: 1)
                return .init(papers: [Self.paper("x")], notices: failed ? ["could not fetch: quant-ph"] : [],
                             fetchedAt: clock.now, submitted: ["x": clock.now])
            },
            update: { _, _ in tops.bump(); return .init(papers: [], fetchedAt: clock.now, submitted: [:]) },
            now: { clock.now })
        let cfg = DigestConfig()

        _ = try await source.fetch(timeframe: "pastweek", feeds: ["quant-ph"], config: cfg, refresh: false)
        notices.set(.distantPast)
        clock.set(Self.eastern(2026, 10, 14, 8))  // a feed failed last time: fetch everything again
        _ = try await source.fetch(timeframe: "pastweek", feeds: ["quant-ph"], config: cfg, refresh: false)
        XCTAssertEqual(full.value, 2)
        XCTAssertEqual(tops.value, 0)

        clock.set(Self.eastern(2026, 10, 22, 8))  // more than a week later: nothing worth keeping
        _ = try await source.fetch(timeframe: "pastweek", feeds: ["quant-ph"], config: cfg, refresh: false)
        XCTAssertEqual(full.value, 3)
        XCTAssertEqual(tops.value, 0)
    }
}
