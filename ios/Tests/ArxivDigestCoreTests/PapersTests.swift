import XCTest
@testable import ArxivDigestCore

private func makePaper(rank: Int, title: String, authors: String, summary: String) -> Paper {
    Paper(rank: rank, id: "id\(rank)", title: title, authors: authors,
          link: "https://arxiv.org/abs/id\(rank)", subjects: "quant-ph",
          section: "New", summary: summary, score: 10 - rank)
}

final class PaperSearchTests: XCTestCase {
    private let papers = [
        makePaper(rank: 1, title: "Floquet engineering", authors: "A. ", summary: "driven lattices"),
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
        XCTAssertFalse(cfg.fontColor(for: .keyword))  // default background highlight
        cfg.setFontColor(true, for: .keyword)
        XCTAssertTrue(cfg.fontColor(for: .keyword))
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
