import SwiftUI
import ArxivDigestCore

/// One paper card, mirroring the web GUI's: "rank. title" with highlighted
/// keywords, highlighted named authors, the section, the two-sentence summary
/// (highlighted only when "Highlight keywords in summaries" is on), and the
/// subjects with feed-bonus highlights; the score metric sits on the right.
struct PaperRowView: View {
    @AppStorage(Highlight.underlineKey) private var underline = false
    let paper: Paper
    let config: DigestConfig
    var maxScore: Int = 0

    private var title: AttributedString {
        var rank = AttributedString("\(paper.rank). ")
        rank.foregroundColor = .secondary
        return rank + Highlight.terms(paper.title, enabled: config.highlightTermsTitle, config: config, underline: underline)
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
                Text(title)
                    .font(.headline)
                    .fixedSize(horizontal: false, vertical: true)

                Text(Highlight.authors(paper.authors, config: config, underline: underline))
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .lineLimit(3)

                if !paper.section.isEmpty {
                    Label(paper.section, systemImage: "calendar")
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                        .labelStyle(.titleAndIcon)
                }

                Text(Highlight.terms(paper.summary, enabled: config.highlightTermsSummary, config: config, underline: underline))
                    .font(.callout)
                    .lineLimit(4)
                    .padding(.top, 2)

                if !paper.subjects.isEmpty {
                    Text(Highlight.subjects(paper.subjects, config: config, underline: underline))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            ScoreBadge(score: paper.score, maxScore: maxScore)
        }
        .padding(.vertical, 6)
        .accessibilityElement(children: .combine)
    }
}
