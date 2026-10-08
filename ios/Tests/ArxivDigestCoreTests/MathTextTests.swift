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
