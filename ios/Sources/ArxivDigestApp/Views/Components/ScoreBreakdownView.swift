import SwiftUI
import ArxivDigestCore

/// "Why this score?", mirroring the GUI's `_render_breakdown`: matched
/// keywords and authors with their weights, subject bonuses, the low-priority
/// penalty, and the long-abstract bonus, each as chips in the aspect's color.
struct ScoreBreakdownView: View {
    let breakdown: ScoreBreakdown
    let config: DigestConfig
    var showTotal = true

    private var signals: [(String, SignalBreakdown)] {
        breakdown.signals.sorted { $0.key < $1.key }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if showTotal {
                HStack {
                    Text("Total").font(.subheadline.weight(.semibold))
                    Spacer()
                    Text("\(breakdown.total)")
                        .font(.subheadline.weight(.bold))
                        .monospacedDigit()
                        .foregroundStyle(Color.accentColor)
                }
            }
            ForEach(signals, id: \.0) { name, signal in
                if signals.count > 1 {
                    Text(name.capitalized).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                }
                rows(signal)
            }
        }
    }

    @ViewBuilder
    private func rows(_ s: SignalBreakdown) -> some View {
        if let kws = s.keywords, !kws.isEmpty {
            row("Keywords matched", aspect: .keyword, items: kws.map { "\($0.term) +\($0.weight)" })
        }
        if let authors = s.authors, !authors.isEmpty {
            row("Authors matched", aspect: .author, items: authors.map { "\($0.term) +\($0.weight)" })
        }
        if let subjects = s.subjects, !subjects.isEmpty {
            row("Subject bonuses", aspect: .subject,
                items: subjects.sorted { $0.key < $1.key }.map { "\($0.key) +\($0.value)" })
        }
        if let low = s.lowPriorityHits, !low.isEmpty {
            row("Low-priority hits · penalty \(s.lowPriorityPenalty ?? 0) (once)", aspect: .lowPriority, items: low)
        }
        if let bonus = s.abstractBonus, bonus != 0 {
            VStack(alignment: .leading, spacing: 2) {
                Text("Abstract bonus +\(bonus)").font(.caption.weight(.semibold))
                Text("Awarded because the abstract is longer than \(config.weight(.longAbstractThreshold)) characters, a rough signal of a substantial paper.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        if isEmpty(s) {
            Text("No keyword, author, or subject matches.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private func isEmpty(_ s: SignalBreakdown) -> Bool {
        (s.keywords?.isEmpty ?? true) && (s.authors?.isEmpty ?? true) && (s.subjects?.isEmpty ?? true)
            && (s.lowPriorityHits?.isEmpty ?? true) && (s.abstractBonus ?? 0) == 0
    }

    private func row(_ label: String, aspect: HighlightAspect, items: [String]) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(label).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            FlowLayout(spacing: 6) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    Chip(text: item, color: Color(hex: config.color(for: aspect)))
                }
            }
        }
    }
}
