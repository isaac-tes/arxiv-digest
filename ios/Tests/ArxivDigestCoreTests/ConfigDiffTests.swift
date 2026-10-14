import XCTest
@testable import ArxivDigestCore

/// The save bar's change list, grouped like the web GUI's unsaved bar.
final class ConfigDiffTests: XCTestCase {
    private func base() -> DigestConfig {
        var c = DigestConfig()
        c.coreKeywords = ["floquet", "anyons"]
        c.namedAuthors = ["Ada Lovelace"]
        c.feeds = ["quant-ph": DigestConfig.listingURL(for: "quant-ph")]
        c.defaultFeeds = ["quant-ph"]
        c.includeReplacements = false
        for w in ScoringWeight.allCases { c.setWeight(DigestConfig.defaultWeights[w]!, for: w) }
        c.setColor("#388bfd", for: .keyword)  // configs from the server carry every field
        return c
    }

    func testNoChangesIsEmpty() {
        XCTAssertTrue(ConfigDiff.changes(saved: base(), current: base()).isEmpty)
    }

    func testChangesAreGroupedBySectionWithEntries() {
        var cur = base()
        cur.namedAuthors.append("Zed Quill")
        cur.coreKeywords.removeAll { $0 == "anyons" }
        cur.setWeight(7, for: .coreKeyword)
        cur.setFeed(name: "cond-mat.str-el")
        cur.setColor("#000000", for: .keyword)

        let changes = ConfigDiff.changes(saved: base(), current: cur)

        XCTAssertEqual(changes.map(\.section), [.keywords, .authors, .feeds, .scoring, .settings])
        XCTAssertEqual(changes.first { $0.section == .keywords }?.lines, ["− anyons"])
        XCTAssertEqual(changes.first { $0.section == .authors }?.lines, ["+ Zed Quill"])
        XCTAssertEqual(changes.first { $0.section == .feeds }?.lines, ["+ cond-mat.str-el"])
        XCTAssertEqual(changes.first { $0.section == .scoring }?.lines, ["core keyword: 6 → 7"])
        XCTAssertEqual(changes.first { $0.section == .settings }?.lines, ["color keyword: #388bfd → #000000"])
    }

    func testSubscriptionAndToggleLinesNameTheirField() {
        var cur = base()
        cur.setSubscribed(false, feed: "quant-ph")
        cur.includeReplacements = true
        XCTAssertEqual(ConfigDiff.changes(saved: base(), current: cur).first?.lines,
                       ["default feeds: − quant-ph", "include replacements: false → true"])
    }
}
