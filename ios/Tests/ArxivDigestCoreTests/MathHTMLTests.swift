import XCTest
@testable import ArxivDigestCore

/// The paper page's abstract as HTML for KaTeX: math kept verbatim (with its
/// delimiters) for KaTeX's auto-render, text HTML-escaped, highlights as spans.
final class MathHTMLTests: XCTestCase {
    func testMathRanges() {
        let t = "a $x$ b $$y$$ c \\(z\\) d \\$5 and $ alone"
        XCTAssertEqual(MathText.mathRanges(in: t).map { String(t[$0]) }, ["$x$", "$$y$$", "\\(z\\)"])
    }

    func testEscapesTextKeepsMathForKaTeX() {
        let html = MathText.html("A<b & $x<y$", spans: [])
        XCTAssertEqual(html, "A&lt;b &amp; $x&lt;y$")
    }

    func testHighlightSpansBecomeClassedSpans() {
        let text = "Floquet anyons in $\\mathbb{Z}_N$"
        let r = text.range(of: "anyons")!
        let html = MathText.html(text, spans: [HighlightSpan(range: r, aspect: .keyword)])
        XCTAssertEqual(html, "Floquet <span class=\"hl keyword\">anyons</span> in $\\mathbb{Z}_N$")
    }

    func testSpanInsideMathIsDropped() {
        let text = "the $\\mathbb{Z}$ anyon"
        let inMath = text.range(of: "mathbb")!
        let html = MathText.html(text, spans: [HighlightSpan(range: inMath, aspect: .keyword)])
        XCTAssertEqual(html, "the $\\mathbb{Z}$ anyon")
    }

    func testTextModeCommandsOutsideMathAreRendered() {
        XCTAssertEqual(MathText.html("An \\textit{ab initio} 50\\% fit", spans: []), "An ab initio 50% fit")
    }

    func testRenderStillWorksAfterRefactor() {
        XCTAssertEqual(MathText.render("costs $5 per run"), "costs $5 per run")
        XCTAssertEqual(MathText.render("a $\\nu=1/m$ b"), "a ν=1/m b")
    }
}
