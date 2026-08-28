import XCTest
@testable import ArxivDigestCore

final class HighlightEngineTests: XCTestCase {
    func testWholeWordMatching() {
        // 'mpo' should match 'MPO' but not 'temporal'.
        XCTAssertTrue(HighlightEngine.matches(term: "mpo", in: "MPO-based methods"))
        XCTAssertFalse(HighlightEngine.matches(term: "mpo", in: "temporal evolution"))
    }

    func testSubstringWhenBoundaryDisabled() {
        XCTAssertTrue(HighlightEngine.matches(term: "mpo", in: "temporal", wordBoundary: false))
    }

    func testAuthorMatchesAuthorListOnly() {
        var config = DigestConfig()
        config.namedAuthors = ["bloch"]
        let paper = Paper(
            rank: 1, id: "arXiv:2601.0001", title: "Bloch theorem",
            authors: "I. Bloch", link: "https://arxiv.org/abs/2601.0001",
            subjects: "cond-mat.quant-gas", section: "New", summary: "A paper", score: 6
        )
        let terms = HighlightEngine.matchedTerms(for: paper, config: config)
        XCTAssertEqual(terms.authors, ["bloch"])
    }

    func testKeywordMatchesTitle() {
        var config = DigestConfig()
        config.coreKeywords = ["floquet"]
        let paper = Paper(
            rank: 1, id: "arXiv:2601.0002", title: "Floquet engineering",
            authors: "A. ", link: "https://arxiv.org/abs/2601.0002",
            subjects: "cond-mat.quant-gas", section: "New", summary: "Driven systems", score: 6
        )
        let terms = HighlightEngine.matchedTerms(for: paper, config: config)
        XCTAssertEqual(terms.keywords, ["floquet"])
    }
}

final class ModelCodableTests: XCTestCase {
    func testDigestDecoding() throws {
        let json = """
        {
          "papers": [
            {
              "rank": 1, "id": "arXiv:2601.0001", "title": "A paper",
              "authors": "A. ", "link": "https://arxiv.org/abs/2601.0001",
              "subjects": "cond-mat.quant-gas", "section": "New",
              "summary": "Summary", "score": 6
            }
          ],
          "total_papers": 1,
          "requested_top": 20
        }
        """.data(using: .utf8)!
        let digest = try JSONDecoder().decode(Digest.self, from: json)
        XCTAssertEqual(digest.papers.count, 1)
        XCTAssertEqual(digest.papers[0].score, 6)
        XCTAssertEqual(digest.totalPapers, 1)
    }

    func testConfigRoundTrip() throws {
        var config = DigestConfig()
        config.coreKeywords = ["floquet", "anyon"]
        config.topN = 10
        let data = try JSONEncoder().encode(config)
        let decoded = try JSONDecoder().decode(DigestConfig.self, from: data)
        XCTAssertEqual(decoded.coreKeywords, ["floquet", "anyon"])
        XCTAssertEqual(decoded.topN, 10)
    }

    func testScoreBreakdownDecoding() throws {
        // Matches the backend's explain_score JSON: keyword/author hits are
        // 2-element arrays [term, weight].
        let json = """
        {
          "signals": {
            "keyword": {
              "keywords": [["floquet", 6], ["anyon", 6]],
              "authors": [[ 6]],
              "subjects": {"cond-mat.quant-gas": 4},
              "low_priority_hits": ["photonic"],
              "low_priority_penalty": -5,
              "abstract_bonus": 1,
              "total": 18
            }
          },
          "total": 18
        }
        """.data(using: .utf8)!
        let breakdown = try JSONDecoder().decode(ScoreBreakdown.self, from: json)
        let keyword = breakdown.signals["keyword"]
        XCTAssertEqual(keyword?.keywords?.first?.term, "floquet")
        XCTAssertEqual(keyword?.keywords?.first?.weight, 6)
        XCTAssertEqual(keyword?.authors?.first?.term, "")
        XCTAssertEqual(keyword?.subjects?["cond-mat.quant-gas"], 4)
        XCTAssertEqual(breakdown.total, 18)
    }
}
