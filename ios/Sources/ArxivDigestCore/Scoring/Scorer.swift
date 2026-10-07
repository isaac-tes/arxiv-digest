import Foundation

/// Port of the engine's `explain_score` / `score_paper` (ADR 0009). Pinned to
/// the Python engine by `ScorerParityTests`; when they disagree, Python wins.
public enum Scorer {
    /// The breakdown the digest service returns:
    /// `{"signals": {"keyword": <explain_score>}, "total": N}`.
    public static func explain(paper: RawPaper, config: DigestConfig) -> ScoreBreakdown {
        let txt = [paper.title, paper.abstract, paper.authors, paper.subjects]
            .joined(separator: " ").lowercased()
        let subjects = paper.subjects.lowercased()
        // Named authors match the author list only, not title/abstract.
        let authors = paper.authors.lowercased()
        let wb = config.wordBoundaryMatching

        let keywords = config.coreKeywords.filter { HighlightEngine.matches(term: $0, in: txt, wordBoundary: wb) }
        let named = config.namedAuthors.filter { HighlightEngine.authorMatches(term: $0, authors: authors, wordBoundary: wb) }
        let low = config.lowPriorityKeywords.filter { HighlightEngine.matches(term: $0, in: txt, wordBoundary: wb) }

        // Subjects stay substring so a parent feed `cond-mat` matches `cond-mat.quant-gas`.
        // Python's `"" in s` is True; Foundation's range(of: "") is nil.
        let subjectHits = config.feedWeights.filter { name, w in
            w != 0 && (name.isEmpty || subjects.range(of: name.lowercased(), options: .literal) != nil)
        }

        let kw = config.weight(.coreKeyword), au = config.weight(.namedAuthor)
        let penalty = low.isEmpty ? 0 : config.weight(.lowPriorityPenalty)
        // Python's len() counts code points.
        let bonus = paper.abstract.unicodeScalars.count > config.weight(.longAbstractThreshold)
            ? config.weight(.longAbstractBonus) : 0
        let total = keywords.count * kw + named.count * au + subjectHits.values.reduce(0, +) + penalty + bonus

        let signal = SignalBreakdown(
            keywords: keywords.map { TermHit(term: $0, weight: kw) },
            authors: named.map { TermHit(term: $0, weight: au) },
            subjects: subjectHits,
            lowPriorityHits: low,
            lowPriorityPenalty: penalty,
            abstractBonus: bonus,
            total: total
        )
        return ScoreBreakdown(signals: ["keyword": signal], total: total)
    }

    public static func score(paper: RawPaper, config: DigestConfig) -> Int {
        explain(paper: paper, config: config).total
    }

    private static let whitespace = try! NSRegularExpression(pattern: "\\s+")
    private static let sentenceEnd = try! NSRegularExpression(pattern: "(?<=[.!?]) ")

    /// The engine's `summarize`: the first two sentences, whitespace collapsed.
    public static func summarize(_ text: String) -> String {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let cleaned = whitespace.stringByReplacingMatches(
            in: trimmed, range: NSRange(trimmed.startIndex..., in: trimmed), withTemplate: " ")
        guard !cleaned.isEmpty else { return "(No abstract available.)" }
        // After collapsing, every break is one space, so splitting on it is `re.split`.
        let marked = sentenceEnd.stringByReplacingMatches(
            in: cleaned, range: NSRange(cleaned.startIndex..., in: cleaned), withTemplate: "\u{0}")
        return marked.split(separator: "\u{0}", omittingEmptySubsequences: false).prefix(2).joined(separator: " ")
    }
}
