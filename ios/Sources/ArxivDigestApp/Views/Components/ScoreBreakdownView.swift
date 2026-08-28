import SwiftUI
import ArxivDigestCore

/// The per-signal "Why this score?" breakdown, mirroring the GUI expander and
/// the Score-a-paper tab: keyword/author hits with weights, subject bonuses,
/// low-priority penalty, and the long-abstract bonus, colored per aspect.
struct ScoreBreakdownView: View {
    let breakdown: ScoreBreakdown
    let config: DigestConfig

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Score")
                    .font(.headline)
                Spacer()
                Text("\(breakdown.total)")
                    .font(.headline)
                    .foregroundStyle(.blue)
            }

            ForEach(sortedSignals, id: \.0) { name, signal in
                signalSection(name: name, signal: signal)
            }
        }
    }

    private var sortedSignals: [(String, SignalBreakdown)] {
        breakdown.signals.sorted { $0.key < $1.key }
    }

    @ViewBuilder
    private func signalSection(name: String, signal: SignalBreakdown) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            if breakdown.signals.count > 1 {
                Text(name.capitalized)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.secondary)
            }

            if let keywords = signal.keywords, !keywords.isEmpty {
                aspectRow(label: "Keywords", aspect: .keyword,
                          hits: keywords.map { "\($0.term) +\($0.weight)" })
            }
            if let authors = signal.authors, !authors.isEmpty {
                aspectRow(label: "Authors", aspect: .author,
                          hits: authors.map { "\($0.term) +\($0.weight)" })
            }
            if let subjects = signal.subjects, !subjects.isEmpty {
                subjectRow(subjects)
            }
            if let low = signal.lowPriorityHits, !low.isEmpty {
                aspectRow(label: "Low-priority (penalty \(signal.lowPriorityPenalty ?? 0))",
                          aspect: .lowPriority,
                          hits: low)
            }
            if let bonus = signal.abstractBonus, bonus > 0 {
                Text("Long-abstract bonus +\(bonus)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if noHits(signal) {
                Text("No matching aspects.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func noHits(_ signal: SignalBreakdown) -> Bool {
        (signal.keywords?.isEmpty ?? true)
            && (signal.authors?.isEmpty ?? true)
            && (signal.subjects?.isEmpty ?? true)
            && (signal.lowPriorityHits?.isEmpty ?? true)
            && ((signal.abstractBonus ?? 0) == 0)
    }

    @ViewBuilder
    private func aspectRow(label: String, aspect: HighlightAspect, hits: [String]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label).font(.caption).foregroundStyle(.secondary)
            ChipRow(items: hits, color: Color(hex: config.color(for: aspect)))
        }
    }

    @ViewBuilder
    private func subjectRow(_ subjects: [String: Int]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Subjects").font(.caption).foregroundStyle(.secondary)
            ChipRow(items: subjects.sorted { $0.key < $1.key }.map { "\($0.key) +\($0.value)" },
                    color: Color(hex: config.colorSubject))
        }
    }
}

/// A wrapping row of small colored chips.
private struct ChipRow: View {
    let items: [String]
    let color: Color

    var body: some View {
        FlowLayout(spacing: 6) {
            ForEach(items, id: \.self) { item in
                Text(item)
                    .font(.caption)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(Capsule().fill(color.opacity(0.22)))
                    .overlay(Capsule().stroke(color.opacity(0.5), lineWidth: 0.5))
            }
        }
    }
}
