import Foundation

/// Matches configured terms against paper text for highlighting.
///
/// Mirrors the engine's `term_pattern` / `term_matches` / `author_matches` and
/// the GUI's `_highlight_terms` / `_authors_html` / `_highlight_subjects`, so the
/// app's highlights always agree with the scores (the invariant the Streamlit
/// GUI enforces).
public enum HighlightEngine {
    /// The engine's `term_pattern`: case-insensitive, literal, and with
    /// `wordBoundary` the term must not be flanked by a word character.
    static func regex(for term: String, wordBoundary: Bool) -> NSRegularExpression? {
        let trimmed = term.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        let escaped = NSRegularExpression.escapedPattern(for: trimmed)
        let pattern = wordBoundary ? "(?<!\\w)" + escaped + "(?!\\w)" : escaped
        return try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive])
    }

    /// True if `term` occurs in `text` as a whole token (unless `wordBoundary`
    /// is false, in which case it's a plain substring match).
    public static func matches(term: String, in text: String, wordBoundary: Bool = true) -> Bool {
        guard let re = regex(for: term, wordBoundary: wordBoundary) else { return false }
        return re.firstMatch(in: text, options: [], range: NSRange(text.startIndex..., in: text)) != nil
    }

    /// All match ranges of `term` within `text`. Empty terms match nothing.
    public static func ranges(of term: String, in text: String, wordBoundary: Bool = true) -> [Range<String.Index>] {
        guard let re = regex(for: term, wordBoundary: wordBoundary) else { return [] }
        let ns = NSRange(text.startIndex..., in: text)
        return re.matches(in: text, options: [], range: ns).compactMap { Range($0.range, in: text) }
    }

    /// Lowercased word tokens of a name, punctuation dropped (`_name_tokens`).
    static func nameTokens(_ text: String) -> [String] {
        text.lowercased()
            .components(separatedBy: CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "_")).inverted)
            .filter { !$0.isEmpty }
    }

    /// Port of the engine's `author_matches`: a single-token term (a surname)
    /// is a whole-word match anywhere in the author list; a multi-token term
    /// ("Ada Lovelace") needs the same first and last token within ONE
    /// comma-separated author, so middle names/initials are ignored and a name
    /// split across two authors does not match.
    public static func authorMatches(term: String, authors: String, wordBoundary: Bool = true) -> Bool {
        let termTokens = nameTokens(term)
        guard let first = termTokens.first, let last = termTokens.last else { return false }
        if termTokens.count == 1 {
            return matches(term: first, in: authors, wordBoundary: wordBoundary)
        }
        for author in authors.split(separator: ",") {
            let tokens = nameTokens(String(author))
            if tokens.count >= 2, tokens.first == first, tokens.last == last { return true }
        }
        return false
    }

    /// Non-overlapping keyword / low-priority spans in reading order. Overlaps
    /// resolve like the GUI's `_highlight_terms`: earliest start wins, then the
    /// longest match, then keyword before low-priority.
    public static func spans(
        in text: String,
        keywords: [String] = [],
        lowPriority: [String] = [],
        wordBoundary: Bool = true
    ) -> [HighlightSpan] {
        var raw: [(range: Range<String.Index>, aspect: HighlightAspect, order: Int)] = []
        for term in keywords {
            for r in ranges(of: term, in: text, wordBoundary: wordBoundary) { raw.append((r, .keyword, 0)) }
        }
        for term in lowPriority {
            for r in ranges(of: term, in: text, wordBoundary: wordBoundary) { raw.append((r, .lowPriority, 1)) }
        }
        return resolve(raw, in: text)
    }

    /// Whole-author spans in an author list, one per comma-separated author
    /// that a named author matches (the GUI's `_authors_html`).
    public static func authorSpans(in authors: String, named: [String], wordBoundary: Bool = true) -> [HighlightSpan] {
        guard !named.isEmpty else { return [] }
        var out: [HighlightSpan] = []
        for piece in authors.split(separator: ",", omittingEmptySubsequences: false) {
            var lo = piece.startIndex, hi = piece.endIndex
            while lo < hi, authors[lo].isWhitespace { lo = authors.index(after: lo) }
            while hi > lo, authors[authors.index(before: hi)].isWhitespace { hi = authors.index(before: hi) }
            guard lo < hi else { continue }
            let name = String(authors[lo..<hi])
            if named.contains(where: { authorMatches(term: $0, authors: name, wordBoundary: wordBoundary) }) {
                out.append(HighlightSpan(range: lo..<hi, aspect: .author))
            }
        }
        return out
    }

    /// Feed-name spans in a subjects string for feeds with a non-zero bonus
    /// (the GUI's `_highlight_subjects`: case-insensitive substring, like the
    /// scorer, so a parent `cond-mat` still matches `cond-mat.quant-gas`).
    public static func subjectSpans(in subjects: String, feedWeights: [String: Int]) -> [HighlightSpan] {
        var raw: [(range: Range<String.Index>, aspect: HighlightAspect, order: Int)] = []
        for (name, weight) in feedWeights where weight != 0 && !name.isEmpty {
            var searchStart = subjects.startIndex
            while searchStart < subjects.endIndex,
                  let r = subjects.range(of: name, options: [.caseInsensitive], range: searchStart..<subjects.endIndex) {
                raw.append((r, .subject, 0))
                searchStart = r.upperBound
            }
        }
        return resolve(raw, in: subjects)
    }

    private static func resolve(
        _ raw: [(range: Range<String.Index>, aspect: HighlightAspect, order: Int)],
        in text: String
    ) -> [HighlightSpan] {
        let sorted = raw.sorted { a, b in
            if a.range.lowerBound != b.range.lowerBound { return a.range.lowerBound < b.range.lowerBound }
            let la = text.distance(from: a.range.lowerBound, to: a.range.upperBound)
            let lb = text.distance(from: b.range.lowerBound, to: b.range.upperBound)
            if la != lb { return la > lb }
            return a.order < b.order
        }
        var result: [HighlightSpan] = []
        var lastUpper: String.Index?
        for entry in sorted {
            if let lastUpper, entry.range.lowerBound < lastUpper { continue }
            result.append(HighlightSpan(range: entry.range, aspect: entry.aspect))
            lastUpper = entry.range.upperBound
        }
        return result
    }

    /// The matched terms per aspect for a digest `Paper`.
    public static func matchedTerms(for paper: Paper, config: DigestConfig) -> HighlightTerms {
        matchedTerms(title: paper.title, abstract: paper.fullAbstract,
                     authors: paper.authors, subjects: paper.subjects, config: config)
    }

    /// The matched terms per aspect for a `ScoredPaper` from `/score`.
    public static func matchedTerms(for paper: ScoredPaper, config: DigestConfig) -> HighlightTerms {
        matchedTerms(title: paper.title, abstract: paper.abstract,
                     authors: paper.authors, subjects: paper.subjects, config: config)
    }

    /// The matched terms per aspect. Keywords/low-priority are matched like the
    /// scorer (title + abstract + authors + subjects); authors match the author
    /// list only; subjects are the feeds whose bonus applies.
    public static func matchedTerms(
        title: String,
        abstract: String,
        authors: String,
        subjects: String,
        config: DigestConfig
    ) -> HighlightTerms {
        let wb = config.wordBoundaryMatching
        let text = [title, abstract, authors, subjects].joined(separator: " ")
        return HighlightTerms(
            keywords: config.coreKeywords.filter { matches(term: $0, in: text, wordBoundary: wb) },
            authors: config.namedAuthors.filter { authorMatches(term: $0, authors: authors, wordBoundary: wb) },
            lowPriority: config.lowPriorityKeywords.filter { matches(term: $0, in: text, wordBoundary: wb) },
            subjects: config.feedWeights
                .filter { $0.value != 0 && subjects.range(of: $0.key, options: .caseInsensitive) != nil }
                .map(\.key).sorted()
        )
    }
}

/// A scored-and-highlightable aspect of a paper (see CONTEXT.md "Aspect").
public enum HighlightAspect: String, Sendable, Equatable, Codable, CaseIterable, Identifiable {
    case keyword
    case author
    case lowPriority
    case subject

    public var id: String { rawValue }

    public var label: String {
        switch self {
        case .keyword: return "Keywords"
        case .author: return "Authors"
        case .lowPriority: return "Low priority"
        case .subject: return "Subjects"
        }
    }
}

/// A single highlighted range within a piece of text, tagged with the aspect
/// that matched it so the UI can color it per the config's per-aspect colors.
public struct HighlightSpan: Sendable, Equatable {
    public let range: Range<String.Index>
    public let aspect: HighlightAspect

    public init(range: Range<String.Index>, aspect: HighlightAspect) {
        self.range = range
        self.aspect = aspect
    }
}

/// The matched terms per aspect, used to drive highlighting in the UI.
public struct HighlightTerms: Sendable, Equatable {
    public let keywords: [String]
    public let authors: [String]
    public let lowPriority: [String]
    public let subjects: [String]

    public init(keywords: [String], authors: [String], lowPriority: [String], subjects: [String]) {
        self.keywords = keywords
        self.authors = authors
        self.lowPriority = lowPriority
        self.subjects = subjects
    }
}
