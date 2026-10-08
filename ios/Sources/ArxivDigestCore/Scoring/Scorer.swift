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
    /// The engine's `_ABBREVIATIONS`: words ending in "." that don't end a sentence.
    private static let abbreviations: Set<String> = Set(
        ("al e.g i.e cf vs fig figs eq eqs ref refs sec secs no vol nat phys rev lett " +
         "commun sci natl acad proc approx resp dr prof").split(separator: " ").map(String.init))

    /// The engine's `summarize`: the first two sentences, whitespace collapsed.
    /// No split inside balanced parentheses, after a known abbreviation, or
    /// after a single-letter initial ("Roy et al. (Nat. Commun. 17)").
    public static func summarize(_ text: String) -> String {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let cleaned = whitespace.stringByReplacingMatches(
            in: trimmed, range: NSRange(trimmed.startIndex..., in: trimmed), withTemplate: " ")
        guard !cleaned.isEmpty else { return "(No abstract available.)" }
        let c = Array(cleaned)
        let trackParens = c.filter { $0 == "(" }.count == c.filter { $0 == ")" }.count
        var sentences: [String] = []
        var start = 0, depth = 0
        for (i, ch) in c.enumerated() {
            if ch == "(" && trackParens {
                depth += 1
            } else if ch == ")" && trackParens {
                depth = max(depth - 1, 0)
            } else if ".!?".contains(ch), depth == 0, i + 1 < c.count, c[i + 1] == " " {
                let word = String(c[start..<i]).split(separator: " ", omittingEmptySubsequences: false).last.map(String.init) ?? ""
                if ch == ".", abbreviations.contains(word.lowercased()) || (word.count == 1 && word.first!.isLetter) {
                    continue
                }
                sentences.append(String(c[start...i]))
                start = i + 2
                if sentences.count == 2 { break }
            }
        }
        if sentences.count < 2, start < c.count { sentences.append(String(c[start...])) }
        return sentences.prefix(2).joined(separator: " ")
    }
}
