import SwiftUI
import ArxivDigestCore

/// One paper row in the Papers list, mirroring a web-GUI paper card: rank +
/// score, highlighted title and authors, section, a summary preview, and
/// subjects. Highlights use the config's per-aspect colors/toggles.
struct PaperRowView: View {
    let paper: Paper
    let config: DigestConfig

    private var terms: HighlightTerms {
        HighlightEngine.matchedTerms(for: paper, config: config)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text("\(paper.rank).")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.secondary)
                HighlightedText(
                    text: paper.title,
                    keywords: config.highlightTermsTitle ? terms.keywords : [],
                    lowPriority: config.highlightTermsTitle ? terms.lowPriority : [],
                    config: config
                )
                .font(.headline)
                Spacer(minLength: 8)
                Text("\(paper.score)")
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(.blue)
                    .accessibilityLabel("Score \(paper.score)")
            }

            HighlightedText(
                text: paper.authors,
                authors: config.highlightAuthors ? terms.authors : [],
                config: config
            )
            .font(.subheadline)
            .foregroundStyle(.secondary)
            .lineLimit(2)

            if !paper.section.isEmpty {
                Text(paper.section)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }

            Text(paper.summary)
                .font(.callout)
                .foregroundStyle(.primary)
                .lineLimit(3)

            if !paper.subjects.isEmpty {
                Text(paper.subjects)
                    .font(.caption)
                    .foregroundStyle(Color(hex: config.colorSubject))
                    .lineLimit(1)
            }
        }
        .padding(.vertical, 4)
    }
}
