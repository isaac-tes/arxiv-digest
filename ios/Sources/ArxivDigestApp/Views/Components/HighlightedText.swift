import SwiftUI
import ArxivDigestCore

/// Builds highlighted text the way the web GUI renders a paper card: matched
/// terms get a faint aspect-colored background (plus a dotted underline when
/// Settings → *Underline highlights* is on, like the GUI), and the font is
/// tinted when the aspect's "color font" toggle is on; matched authors are
/// bold. Spans come from `HighlightEngine`, which uses the scorer's matching,
/// so highlights and scores never diverge. Titles and abstracts show inline
/// LaTeX as Unicode (`MathText`).
enum Highlight {
    /// `@AppStorage` key for the dotted underline (device-local display pref).
    static let underlineKey = "underlineHighlights"

    static func attributed(_ text: String, spans: [HighlightSpan], config: DigestConfig, underline: Bool) -> AttributedString {
        var attr = AttributedString(text)
        for span in spans {
            guard let range = attributedRange(span.range, in: text, attr) else { continue }
            let color = Color(hex: config.color(for: span.aspect))
            attr[range].backgroundColor = color.opacity(0.14)
            if underline {
                attr[range].underlineStyle = Text.LineStyle(pattern: .dot, color: color)
            }
            if config.fontColor(for: span.aspect) {
                attr[range].foregroundColor = color
            }
            if span.aspect == .author {
                attr[range].inlinePresentationIntent = .stronglyEmphasized
            }
        }
        return attr
    }

    /// Title / abstract / summary: keywords + low-priority terms, when the
    /// matching display toggle is on.
    static func terms(_ raw: String, enabled: Bool, config: DigestConfig, underline: Bool) -> AttributedString {
        let text = MathText.render(raw)
        guard enabled else { return AttributedString(text) }
        let spans = HighlightEngine.spans(
            in: text, keywords: config.coreKeywords, lowPriority: config.lowPriorityKeywords,
            wordBoundary: config.wordBoundaryMatching)
        return attributed(text, spans: spans, config: config, underline: underline)
    }

    static func authors(_ text: String, config: DigestConfig, underline: Bool) -> AttributedString {
        guard config.highlightAuthors else { return AttributedString(text) }
        let spans = HighlightEngine.authorSpans(
            in: text, named: config.namedAuthors, wordBoundary: config.wordBoundaryMatching)
        return attributed(text, spans: spans, config: config, underline: underline)
    }

    static func subjects(_ text: String, config: DigestConfig, underline: Bool) -> AttributedString {
        attributed(text, spans: HighlightEngine.subjectSpans(in: text, feedWeights: config.feedWeights),
                   config: config, underline: underline)
    }
}

/// The `AttributedString` range for a range of the `String` it was built
/// from, via character offsets.
private func attributedRange(
    _ range: Range<String.Index>, in text: String, _ attr: AttributedString
) -> Range<AttributedString.Index>? {
    let lo = text.distance(from: text.startIndex, to: range.lowerBound)
    let hi = text.distance(from: text.startIndex, to: range.upperBound)
    let count = attr.characters.count
    guard lo >= 0, lo < hi, hi <= count else { return nil }
    let start = attr.characters.index(attr.startIndex, offsetBy: lo)
    let end = attr.characters.index(attr.startIndex, offsetBy: hi)
    return start..<end
}
