import Foundation

/// Renders a paper's score breakdown for display ("why this score?").
public enum ScoreDisplay {
    /// Human-readable lines describing how a paper's score was reached.
    public static func lines(for breakdown: ScoreBreakdown) -> [String] {
        var out: [String] = []
        out.append("Score: \(breakdown.total)")
        for (signalName, signal) in breakdown.signals {
            out.append("— \(signalName) —")
            if let keywords = signal.keywords, !keywords.isEmpty {
                let parts = keywords.map { "'\($0.term)' (+\($0.weight))" }
                out.append("Keywords: " + parts.joined(separator: ", "))
            }
            if let authors = signal.authors, !authors.isEmpty {
                let parts = authors.map { "'\($0.term)' (+\($0.weight))" }
                out.append("Authors: " + parts.joined(separator: ", "))
            }
            if let subjects = signal.subjects, !subjects.isEmpty {
                let parts = subjects.map { "\($0.key) (+\($0.value))" }
                out.append("Subjects: " + parts.joined(separator: ", "))
            }
            if let low = signal.lowPriorityHits, !low.isEmpty {
                out.append("Low-priority hits: \(low.joined(separator: ", ")) (penalty \(signal.lowPriorityPenalty ?? 0))")
            }
            if let bonus = signal.abstractBonus, bonus > 0 {
                out.append("Abstract bonus: +\(bonus)")
            }
        }
        return out
    }
}
