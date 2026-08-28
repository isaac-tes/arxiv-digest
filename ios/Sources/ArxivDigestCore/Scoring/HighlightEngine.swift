import Foundation

/// Matches configured terms against paper text for highlighting.
///
/// Mirrors the backend's `term_pattern` / `term_matches` (whole-word matching by
/// default) so the app's highlights always agree with the scores — the same
/// invariant the Streamlit GUI enforces.
public enum HighlightEngine {
    /// True if `term` occurs in `text` as a whole token (unless `wordBoundary`
    /// is false, in which case it's a plain substring match).
    public static func matches(term: String, in text: String, wordBoundary: Bool = true) -> Bool {
        let trimmed = term.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return false }
        let pattern: String
        if wordBoundary {
            let escaped = NSRegularExpression.escapedPattern(for: trimmed)
            pattern = "(?<!\\w)" + escaped + "(?!\\w)"
        } else {
            pattern = NSRegularExpression.escapedPattern(for: trimmed)
        }
        guard let regex = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) else {
            return false
        }
        let range = NSRange(text.startIndex..., in: text)
        return regex.firstMatch(in: text, options: [], range: range) != nil
    }

    /// All whole-word (or substring, if `wordBoundary` is false) match ranges of
    /// `term` within `text`. Case-insensitive. Empty terms match nothing.
    public static func ranges(of term: String, in text: String, wordBoundary: Bool = true) -> [Range<String.Index>] {
        let trimmed = term.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return [] }
        let escaped = NSRegularExpression.escapedPattern(for: trimmed)
        let pattern = wordBoundary ? "(?<!\\w)" + escaped + "(?!\\w)" : escaped
        guard let regex = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) else {
            return []
        }
        let ns = NSRange(text.startIndex..., in: text)
        return regex.matches(in: text, options: [], range: ns).compactMap { Range($0.range, in: text) }
    }

    /// Non-overlapping highlight spans for the given term groups within `text`,
    /// returned in reading order. When two groups match overlapping text, the
    /// higher-priority aspect wins: keyword > author > low-priority (so a term
    /// that is both a keyword and a low-priority term highlights positively).
    ///
    /// Mirrors the GUI's `_highlight_terms`, which highlights matched keywords
    /// and low-priority terms in the title/abstract and authors in the author
    /// list, using the same `term_pattern` the scorer uses.
    public static func spans(
        in text: String,
        keywords: [String] = [],
        authors: [String] = [],
        lowPriority: [String] = [],
        wordBoundary: Bool = true
    ) -> [HighlightSpan] {
        var raw: [(range: Range<String.Index>, aspect: HighlightAspect, priority: Int)] = []
        func collect(_ terms: [String], _ aspect: HighlightAspect, _ priority: Int) {
            for term in terms {
                for r in ranges(of: term, in: text, wordBoundary: wordBoundary) {
                    raw.append((r, aspect, priority))
                }
            }
        }
        collect(keywords, .keyword, 0)
        collect(authors, .author, 1)
        collect(lowPriority, .lowPriority, 2)

        // Sort by start position, then by priority so the winning aspect is
        // considered first when ranges start at the same index.
        raw.sort { a, b in
            if a.range.lowerBound != b.range.lowerBound { return a.range.lowerBound < b.range.lowerBound }
            return a.priority < b.priority
        }

        var result: [HighlightSpan] = []
        var lastUpper: String.Index?
        for entry in raw {
            if let lastUpper, entry.range.lowerBound < lastUpper { continue }  // overlaps a kept span
            result.append(HighlightSpan(range: entry.range, aspect: entry.aspect))
            lastUpper = entry.range.upperBound
        }
        return result
    }

    /// The matched terms per aspect for a digest `Paper` (uses `summary`).
    public static func matchedTerms(for paper: Paper, config: DigestConfig) -> HighlightTerms {
        matchedTerms(
            title: paper.title, abstract: paper.summary,
            authors: paper.authors, subjects: paper.subjects, config: config
        )
    }

    /// The matched terms per aspect for a `ScoredPaper` from `/score` (uses
    /// `abstract`).
    public static func matchedTerms(for paper: ScoredPaper, config: DigestConfig) -> HighlightTerms {
        matchedTerms(
            title: paper.title, abstract: paper.abstract,
            authors: paper.authors, subjects: paper.subjects, config: config
        )
    }

    /// The matched terms per aspect, given raw paper text and the user's config.
    /// Keywords/low-priority match title+abstract; authors match the author list
    /// only — the same aspect targeting the GUI and scorer use.
    public static func matchedTerms(
        title: String,
        abstract: String,
        authors: String,
        subjects: String,
        config: DigestConfig
    ) -> HighlightTerms {
        let wb = config.wordBoundaryMatching
        let titleAbstract = "\(title) \(abstract)"
        let keywords = config.coreKeywords.filter { matches(term: $0, in: titleAbstract, wordBoundary: wb) }
        let namedAuthors = config.namedAuthors.filter { matches(term: $0, in: authors, wordBoundary: wb) }
        let lowPriority = config.lowPriorityKeywords.filter { matches(term: $0, in: titleAbstract, wordBoundary: wb) }
        let subjectHits = subjects.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }

        return HighlightTerms(
            keywords: keywords,
            authors: namedAuthors,
            lowPriority: lowPriority,
            subjects: subjectHits
        )
    }
}

/// A scored/highlightable aspect of a paper (see CONTEXT.md "Aspect"). The
/// canonical set the app highlights; `subject` is scored but rendered as a
/// separate label rather than an inline span.
public enum HighlightAspect: String, Sendable, Equatable, Codable {
    case keyword
    case author
    case lowPriority
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
public struct HighlightTerms: Sendable {
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
