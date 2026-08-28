import Foundation

/// A single arXiv paper as returned by the digest service.
///
/// Mirrors the backend's `PaperOut` schema. `Codable` so it round-trips through
/// the JSON API and can be cached locally.
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

    public init(
        rank: Int,
        id: String,
        title: String,
        authors: String,
        link: String,
        subjects: String,
        section: String,
        summary: String,
        score: Int
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
    }
}
