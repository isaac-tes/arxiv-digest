import XCTest
@testable import ArxivDigestCore

/// Highlight colors are GitHub dark-theme hues; as text on a white background
/// they're darkened until readable (WCAG AA, 4.5:1), like the GUI's light-mode
/// override.
final class ColorContrastTests: XCTestCase {
    func testContrastOfKnownPairs() {
        XCTAssertEqual(ColorContrast.ratio("#000000", "#ffffff"), 21, accuracy: 0.01)
        XCTAssertEqual(ColorContrast.ratio("#ffffff", "#ffffff"), 1, accuracy: 0.01)
        XCTAssertLessThan(ColorContrast.ratio("#3fb950", "#ffffff"), 3)  // default author green
    }

    func testDefaultHighlightColorsBecomeReadableOnWhite() {
        for hex in ["#388bfd", "#f85149", "#3fb950", "#a371f7", "#ffff00"] {
            let dark = ColorContrast.readableOnWhite(hex)
            XCTAssertGreaterThanOrEqual(ColorContrast.ratio(dark, "#ffffff"), 4.5, "\(hex) → \(dark)")
        }
    }

    func testKeepsHueAndLeavesDarkColorsAlone() {
        XCTAssertEqual(ColorContrast.readableOnWhite("#24292f"), "#24292f")
        let green = ColorContrast.readableOnWhite("#3fb950")
        let (r, g, b) = ColorContrast.rgb(green)!
        XCTAssertTrue(g > r && g > b, "still green: \(green)")
    }

    func testBadInputPassesThrough() {
        XCTAssertEqual(ColorContrast.readableOnWhite("not a color"), "not a color")
    }
}
