import SwiftUI
import ArxivDigestCore

/// Renders text with matched keyword / author / low-priority terms highlighted,
/// using the same `HighlightEngine.spans` the scorer uses and the per-aspect
/// colors from the config — so highlights and scores never diverge (the same
/// invariant the Streamlit GUI enforces).
struct HighlightedText: View {
    let text: String
    var keywords: [String] = []
    var authors: [String] = []
    var lowPriority: [String] = []
    let config: DigestConfig

    var body: some View {
        Text(attributed)
    }

    private var attributed: AttributedString {
        var attr = AttributedString(text)
        let spans = HighlightEngine.spans(
            in: text,
            keywords: keywords,
            authors: authors,
            lowPriority: lowPriority,
            wordBoundary: config.wordBoundaryMatching
        )
        for span in spans {
            let lowerOffset = text.distance(from: text.startIndex, to: span.range.lowerBound)
            let upperOffset = text.distance(from: text.startIndex, to: span.range.upperBound)
            guard lowerOffset <= upperOffset else { continue }
            let start = attr.index(attr.startIndex, offsetByCharacters: lowerOffset)
            let end = attr.index(attr.startIndex, offsetByCharacters: upperOffset)
            guard start < end else { continue }
            let color = Color(hex: config.color(for: span.aspect))
            // Honor the config's font-vs-background toggle per aspect (GUI's
            // color_font_*): color the text itself, or draw a light background.
            if config.fontColor(for: span.aspect) {
                attr[start..<end].foregroundColor = color
            } else {
                attr[start..<end].backgroundColor = color.opacity(0.28)
            }
        }
        return attr
    }
}
