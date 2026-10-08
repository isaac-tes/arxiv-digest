import Foundation

/// A single arXiv paper as returned by the digest service (`PaperOut`).
///
/// `abstract` and `breakdown` arrive with the digest (ADR 0008), so the detail
/// view needs no extra arXiv round-trip. Both decode leniently so an older
/// server that sends neither still works.
public struct Paper: Codable, Identifiable, Hashable, Sendable {
    public let rank: Int
    public let id: String
    public let title: String
    public let authors: String
    public let link: String
    public let subjects: String
    public let section: String
    public let summary: String
    public let score: Int
    public let abstract: String
    public let breakdown: ScoreBreakdown?

    enum CodingKeys: String, CodingKey {
        case rank, id, title, authors, link, subjects, section, summary, score, abstract, breakdown
    }

    public init(
        rank: Int,
        id: String,
        title: String,
        authors: String,
        link: String,
        subjects: String,
        section: String,
        summary: String,
        score: Int,
        abstract: String = "",
        breakdown: ScoreBreakdown? = nil
    ) {
        self.rank = rank
        self.id = id
        self.title = title
        self.authors = authors
        self.link = link
        self.subjects = subjects
        self.section = section
        self.summary = summary
        self.score = score
        self.abstract = abstract
        self.breakdown = breakdown
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        rank = try c.decode(Int.self, forKey: .rank)
        id = try c.decode(String.self, forKey: .id)
        title = try c.decode(String.self, forKey: .title)
        authors = try c.decode(String.self, forKey: .authors)
        link = try c.decode(String.self, forKey: .link)
        subjects = try c.decodeIfPresent(String.self, forKey: .subjects) ?? ""
        section = try c.decodeIfPresent(String.self, forKey: .section) ?? ""
        summary = try c.decodeIfPresent(String.self, forKey: .summary) ?? ""
        score = try c.decode(Int.self, forKey: .score)
        abstract = try c.decodeIfPresent(String.self, forKey: .abstract) ?? ""
        breakdown = try c.decodeIfPresent(ScoreBreakdown.self, forKey: .breakdown)
    }

    /// The full abstract when the server sent it, else the two-sentence summary.
    public var fullAbstract: String { abstract.isEmpty ? summary : abstract }

    /// The arXiv PDF URL (`/abs/` → `/pdf/`), or nil for a non-arXiv link.
    public var pdfURL: URL? {
        guard link.contains("/abs/") else { return nil }
        return URL(string: link.replacingOccurrences(of: "/abs/", with: "/pdf/"))
    }

    /// A copy with a different rank (used by the demo server when re-ranking).
    public func withRank(_ newRank: Int) -> Paper {
        Paper(rank: newRank, id: id, title: title, authors: authors, link: link,
              subjects: subjects, section: section, summary: summary, score: score,
              abstract: abstract, breakdown: breakdown)
    }
}
