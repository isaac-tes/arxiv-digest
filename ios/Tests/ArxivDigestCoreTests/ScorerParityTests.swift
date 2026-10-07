import XCTest
@testable import ArxivDigestCore

/// Every case in `ScoringParityFixture` is a paper + config + the breakdown the
/// Python engine's `explain_score` returned. Regenerate with
/// `uv run python ios/scripts/make_parity_fixture.py`.
final class ScorerParityTests: XCTestCase {
    struct Case: Decodable {
        let name: String
        let config: [String: JSONValue]
        let paper: RawPaper
        let expected: SignalBreakdown
    }

    func testMatchesEngineExplainScore() throws {
        let cases = try JSONDecoder().decode([Case].self, from: Data(ScoringParityFixture.json.utf8))
        XCTAssertEqual(cases.count, 30)
        for c in cases {
            let got = Scorer.explain(paper: c.paper, config: DigestConfig(data: c.config))
            XCTAssertEqual(got.signals["keyword"], c.expected, c.name)
            XCTAssertEqual(got.total, c.expected.total, c.name)
            XCTAssertEqual(Scorer.score(paper: c.paper, config: DigestConfig(data: c.config)), c.expected.total, c.name)
        }
    }
}
