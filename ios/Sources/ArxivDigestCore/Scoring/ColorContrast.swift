import Foundation

/// WCAG contrast for the `#rrggbb` highlight colors. The defaults are GitHub
/// dark-theme hues (as in the GUI), too light to read as text on white; the
/// app darkens them for light mode only, like the GUI's light-theme override.
public enum ColorContrast {
    /// `#rrggbb` → 0…1 components, or nil.
    public static func rgb(_ hex: String) -> (Double, Double, Double)? {
        let h = hex.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: "#", with: "")
        guard h.count == 6, let v = UInt32(h, radix: 16) else { return nil }
        return (Double((v >> 16) & 0xFF) / 255, Double((v >> 8) & 0xFF) / 255, Double(v & 0xFF) / 255)
    }

    private static func luminance(_ c: (Double, Double, Double)) -> Double {
        func lin(_ x: Double) -> Double { x <= 0.03928 ? x / 12.92 : pow((x + 0.055) / 1.055, 2.4) }
        return 0.2126 * lin(c.0) + 0.7152 * lin(c.1) + 0.0722 * lin(c.2)
    }

    /// WCAG contrast ratio (1…21); 1 for unparseable input.
    public static func ratio(_ a: String, _ b: String) -> Double {
        guard let x = rgb(a), let y = rgb(b) else { return 1 }
        let (l1, l2) = (luminance(x), luminance(y))
        return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)
    }

    /// `hex` scaled toward black (same hue) until it reaches `minimum`
    /// contrast on white; unchanged if it already does or doesn't parse.
    public static func readableOnWhite(_ hex: String, minimum: Double = 4.5) -> String {
        guard let c = rgb(hex), ratio(hex, "#ffffff") < minimum else { return hex }
        var k = 1.0
        var out = hex
        while k > 0 {
            k -= 0.02
            out = String(format: "#%02x%02x%02x",
                         Int((c.0 * k * 255).rounded()), Int((c.1 * k * 255).rounded()), Int((c.2 * k * 255).rounded()))
            if ratio(out, "#ffffff") >= minimum { break }
        }
        return out
    }
}
