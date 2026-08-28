import Foundation

/// A paper as returned by `POST /score`.
///
/// This is the raw `arxiv_digest` paper shape (uses `abstract`, and has no
/// `rank`/`score`), which differs from the digest `Paper` (`summary` + rank +
/// score). Kept as a separate type so each endpoint decodes exactly what it
/// returns rather than forcing lenient optionals onto `Paper`.
public struct ScoredPaper: Codable, Identifiable, Hashable, Sendable {
    public let id: String
    public let title: String
    public let authors: String
    public let link: String
    public let subjects: String
    public let section: String
    public let abstract: String

    public init(
        id: String,
        title: String,
        authors: String,
        link: String,
        subjects: String,
        section: String,
        abstract: String
    ) {
        self.id = id
        self.title = title
        self.authors = authors
        self.link = link
        self.subjects = subjects
        self.section = section
        self.abstract = abstract
    }
}

/// The response from `POST /score`: the fetched paper (or nil), its per-signal
/// breakdown, and — when the paper isn't in the current digest — an
/// `absenceReason` explaining why (mirrors the GUI Score-a-paper tab).
public struct ScoreResult: Codable, Sendable {
    public let paper: ScoredPaper?
    public let breakdown: ScoreBreakdown
    public let absenceReason: String?

    enum CodingKeys: String, CodingKey {
        case paper
        case breakdown
        case absenceReason = "absence_reason"
    }

    public init(paper: ScoredPaper?, breakdown: ScoreBreakdown, absenceReason: String? = nil) {
        self.paper = paper
        self.breakdown = breakdown
        self.absenceReason = absenceReason
    }
}
