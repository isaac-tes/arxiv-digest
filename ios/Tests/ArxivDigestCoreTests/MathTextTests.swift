import XCTest
@testable import ArxivDigestCore

/// Inline LaTeX in arXiv titles/abstracts is shown as Unicode (display only).
final class MathTextTests: XCTestCase {
    private func r(_ s: String) -> String { MathText.render(s) }

    func testAbstractFromTheDigest() {
        XCTAssertEqual(r("probes $G$-crossed associativity data"), "probes G-crossed associativity data")
        XCTAssertEqual(r("recover the $\\mathbb{Z}_{2m}$ parafermion"), "recover the ℤ₂ₘ parafermion")
        XCTAssertEqual(r("at filling $\\nu=1/m$, obtain"), "at filling ν=1/m, obtain")
        XCTAssertEqual(r("a $\\mathbb{Z}_2^{(n)}\\times\\mathbb{Z}_N$ structure"), "a ℤ₂⁽ⁿ⁾×ℤ_N structure")
        XCTAssertEqual(r("a $\\mathrm{Fib}\\times\\mathbb{Z}_N$ structure"), "a Fib×ℤ_N structure")
        XCTAssertEqual(r("with $N=2(3M+2)$ for"), "with N=2(3M+2) for")
    }

    func testScriptsSymbolsAndCommands() {
        XCTAssertEqual(r("$x^2 + y_{ij}$"), "x² + yᵢⱼ")
        XCTAssertEqual(r("$e^{i\\phi}$"), "eⁱᵠ")
        XCTAssertEqual(r("$\\frac{1}{2}$"), "1/2")
        XCTAssertEqual(r("$\\hat{H}$"), "Ĥ")
        XCTAssertEqual(r("$\\mathcal{O}(N^2)$"), "𝒪(N²)")
        XCTAssertEqual(r("$T \\to 0$ and $\\Delta \\leq \\hbar\\omega$"), "T → 0 and Δ ≤ ℏω")
        XCTAssertEqual(r("$\\langle n \\rangle$"), "⟨ n ⟩")
        XCTAssertEqual(r("$\\sqrt{2}$, $\\left( a \\right)$"), "√2, ( a )")
        XCTAssertEqual(r("\\(k_F\\) inline"), "k_F inline")
    }

    func testUnmappableScriptKeepsMarkerAndGroups() {
        XCTAssertEqual(r("$a_{F}$"), "a_F")
        XCTAssertEqual(r("$a_{FG}$"), "a_(FG)")
        XCTAssertEqual(r("$\\mathbb{Z}_N$"), "ℤ_N")
    }

    func testTextModeCommandsOutsideMath() {
        XCTAssertEqual(r("An \\textit{ab initio} formula"), "An ab initio formula")
        XCTAssertEqual(r("\\emph{Not} 50\\% of A\\&B"), "Not 50% of A&B")
    }

    func testLeavesPlainTextAlone() {
        XCTAssertEqual(r("costs $5 per run"), "costs $5 per run")      // unpaired $
        XCTAssertEqual(r("a \\$10 bill"), "a $10 bill")
        XCTAssertEqual(r("~100 atoms at T_c"), "~100 atoms at T_c")    // no math markers
        XCTAssertEqual(r("Plain title"), "Plain title")
    }
}

/// `styled` is what the app draws: scripts stay plain characters and are
/// reported as runs, so they render as real lowered/raised text.
final class MathTextStyledTests: XCTestCase {
    private func sub(_ r: Range<Int>) -> MathText.ScriptRun { .init(range: r, isSubscript: true) }
    private func sup(_ r: Range<Int>) -> MathText.ScriptRun { .init(range: r, isSubscript: false) }

    func testScriptWithoutUnicodeFormIsLowered() {  // "Chiral Parafermions in Floquet ℤ_N Topological Order"
        let s = MathText.styled("Floquet $\\mathbb{Z}_N$ Topological Order")
        XCTAssertEqual(s.text, "Floquet ℤN Topological Order")
        XCTAssertEqual(s.scripts, [sub(9..<10)])
    }

    func testTextSuperscriptIsRaisedAsAWord() {  // "SC^sharp: superconductivity intertwined with …"
        let s = MathText.styled("SC$^{\\text{sharp}}$: superconductivity")
        XCTAssertEqual(s.text, "SCsharp: superconductivity")
        XCTAssertEqual(s.scripts, [sup(2..<7)])
    }

    func testEveryScriptIsARunDigitsToo() {
        let s = MathText.styled("a $\\mathbb{Z}_2^{(n)}$ and $x^2$")
        XCTAssertEqual(s.text, "a ℤ2(n) and x2")
        XCTAssertEqual(s.scripts, [sub(3..<4), sup(4..<7), sup(13..<14)])
    }

    func testPlainTextHasNoRuns() {
        XCTAssertEqual(MathText.styled("Plain title").text, "Plain title")
        XCTAssertEqual(MathText.styled("T_c without math").scripts, [])
    }
}
