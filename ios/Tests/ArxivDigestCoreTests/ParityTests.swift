import XCTest
@testable import ArxivDigestCore

/// Expected values in this file come from running the Python engine
/// (`arxiv_digest` / `zotero_bridge`) on the same inputs, so highlights and
/// exports stay in step with the CLI/GUI.
final class AuthorMatchParityTests: XCTestCase {
    func testMatchesEngineAuthorMatches() {
        let cases: [(String, String, Bool)] = [
            ("Ada Lovelace", "Ada M. Lovelace, Bo Example", true),
            ("Ada Lovelace", "Bob Ada, Charlie Lovelace", false),
            ("bloch", "I. Bloch", true),
            ("bloch", "A. Blochwitz", false),
            ("ma", "Y. Mao", false),
            ("ma", "Y. Ma", true),
            ("Ada Lovelace", "Lovelace, Ada", false),
            ("Bzdušek", "T. Bzdušek", true),
            ("van Loon", "Pieter van Loon", false),
            ("o'brien", "K. O'Brien", false),
        ]
        for (term, authors, expected) in cases {
            XCTAssertEqual(HighlightEngine.authorMatches(term: term, authors: authors), expected, "\(term) in \(authors)")
        }
    }

    func testAuthorSpansCoverWholeAuthor() {
        let authors = "Ada M. Lovelace, Bo Example,  I. Bloch"
        let spans = HighlightEngine.authorSpans(in: authors, named: ["Ada Lovelace", "bloch"])
        XCTAssertEqual(spans.map { String(authors[$0.range]) }, ["Ada M. Lovelace", "I. Bloch"])
        XCTAssertTrue(spans.allSatisfy { $0.aspect == .author })
        XCTAssertTrue(HighlightEngine.authorSpans(in: authors, named: []).isEmpty)
    }

    func testMatchedTermsUseAuthorMatching() {
        var cfg = DigestConfig()
        cfg.namedAuthors = ["Ada Lovelace", "Bob Ada"]
        let terms = HighlightEngine.matchedTerms(
            title: "T", abstract: "A", authors: "Ada M. Lovelace", subjects: "", config: cfg)
        XCTAssertEqual(terms.authors, ["Ada Lovelace"])
    }
}

final class SpanParityTests: XCTestCase {
    func testLongestMatchWinsAtSameStart() {
        // GUI `_highlight_terms`: sort by (start, -length); a longer
        // low-priority term beats a shorter keyword at the same start.
        let text = "machine learning methods"
        let spans = HighlightEngine.spans(in: text, keywords: ["machine"], lowPriority: ["machine learning"])
        XCTAssertEqual(spans.count, 1)
        XCTAssertEqual(spans.first?.aspect, .lowPriority)
        XCTAssertEqual(spans.first.map { String(text[$0.range]) }, "machine learning")
    }

    func testEarlierStartWins() {
        let text = "a topological insulator"
        let spans = HighlightEngine.spans(in: text, keywords: ["insulator", "topological insulator"])
        XCTAssertEqual(spans.map { String(text[$0.range]) }, ["topological insulator"])
    }

    func testSubjectSpansSubstringAndZeroWeightSkipped() {
        let subjects = "cond-mat.quant-gas, Quant-ph, cond-mat.str-el"
        let spans = HighlightEngine.subjectSpans(
            in: subjects, feedWeights: ["cond-mat": 1, "quant-ph": 2, "cond-mat.str-el": 0])
        // Longest-first at the same start is irrelevant here; parent feed
        // `cond-mat` matches inside both sub-categories.
        XCTAssertEqual(spans.map { String(subjects[$0.range]) }, ["cond-mat", "Quant-ph", "cond-mat"])
        XCTAssertTrue(spans.allSatisfy { $0.aspect == .subject })
    }

    func testMatchedSubjectsFollowFeedWeights() {
        var cfg = DigestConfig()
        cfg.feedWeights = ["quant-ph": 2, "cond-mat.mes-hall": 4]
        let t = HighlightEngine.matchedTerms(title: "", abstract: "", authors: "",
                                             subjects: "Quantum Physics (quant-ph)", config: cfg)
        XCTAssertEqual(t.subjects, ["quant-ph"])
    }

    func testKeywordMatchedAnywhereTheScorerLooks() {
        // The scorer matches keywords in title+abstract+authors+subjects.
        var cfg = DigestConfig()
        cfg.coreKeywords = ["quant-gas"]
        let t = HighlightEngine.matchedTerms(title: "", abstract: "", authors: "",
                                             subjects: "cond-mat.quant-gas", config: cfg)
        XCTAssertEqual(t.keywords, ["quant-gas"])
    }
}

final class ArxivIDTests: XCTestCase {
    func testParseMatchesEngine() {
        XCTAssertEqual(ArxivID.parse("https://arxiv.org/abs/2609.21407v2"), "2609.21407")
        XCTAssertEqual(ArxivID.parse("arXiv:2609.21407"), "2609.21407")
        XCTAssertEqual(ArxivID.parse("2609.21407v3"), "2609.21407")
        XCTAssertEqual(ArxivID.parse("cond-mat/0601001v2"), "cond-mat/0601001")
        XCTAssertEqual(ArxivID.parse("http://arxiv.org/abs/cond-mat/0601001"), "cond-mat/0601001")
        XCTAssertNil(ArxivID.parse("  "))
    }

    func testParseImprovesOnEngineForPdfAndQuery() {
        XCTAssertEqual(ArxivID.parse("https://arxiv.org/pdf/2609.21407v1.pdf"), "2609.21407")
        XCTAssertEqual(ArxivID.parse("https://arxiv.org/abs/2609.21407v2?context=quant-ph"), "2609.21407")
    }

    func testWellFormed() {
        XCTAssertTrue(ArxivID.isWellFormed("2609.21407"))
        XCTAssertTrue(ArxivID.isWellFormed("cond-mat/0601001"))
        XCTAssertTrue(ArxivID.isWellFormed("math.AG/0601001"))
        XCTAssertFalse(ArxivID.isWellFormed("hello"))
        XCTAssertFalse(ArxivID.isWellFormed("2609.21"))
    }
}

final class ExportParityTests: XCTestCase {
    private func entries() -> [Paper] {
        [
            Paper(rank: 1, id: "x", title: "T1", authors: "A", link: "https://arxiv.org/abs/x",
                  subjects: "quant-ph", section: "Mon, 28 Sep 2026", summary: "S1.", score: 9),
            Paper(rank: 2, id: "y", title: "T2", authors: "B", link: "", subjects: "",
                  section: "", summary: "S2.", score: 3),
        ]
    }

    func testMarkdownMatchesFormatMarkdown() {
        let expected = "# Daily arXiv cond-mat/quant-ph digest\n\nTotal papers fetched: 40. Showing top 20 by relevance.\n\n## 1. T1\n- **Authors:** A\n- **Section:** Mon, 28 Sep 2026\n- **Subjects:** quant-ph\n- **Link:** https://arxiv.org/abs/x\n\nS1.\n\n## 2. T2\n- **Authors:** B\n\nS2."
        XCTAssertEqual(DigestExport.markdown(entries: entries(), totalPapers: 40, requestedTop: 20), expected)
        XCTAssertTrue(DigestExport.markdown(entries: entries(), totalPapers: 1, requestedTop: 20)
            .contains("Total papers fetched: 1. Showing top 1 by relevance."))
    }

    func testJSONPayloadShape() throws {
        let digest = Digest(papers: entries(), totalPapers: 40, requestedTop: 20)
        let data = try DigestExport.json(digest, generatedAt: Date(timeIntervalSince1970: 0))
        let obj = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(obj["generated_at"] as? String, "1970-01-01T00:00:00Z")
        XCTAssertEqual(obj["top_n"] as? Int, 20)
        XCTAssertEqual(obj["total_papers"] as? Int, 40)
        let first = try XCTUnwrap((obj["entries"] as? [[String: Any]])?.first)
        XCTAssertEqual(Set(first.keys), ["rank", "id", "title", "authors", "link", "subjects", "section", "summary", "score"])
    }

    func testFileName() {
        XCTAssertEqual(DigestExport.fileName(ext: "md", date: Date(timeIntervalSince1970: 86_400 * 365 + 43_200)), "digest-1971-01-01.md")
    }
}
