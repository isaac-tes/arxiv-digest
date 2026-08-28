import Foundation

/// A saved list of papers (multi-list support).
public struct SavedList: Codable, Identifiable, Hashable, Sendable {
    public let id: Int
    public var name: String
    public var papers: [ListPaper]

    public init(id: Int, name: String, papers: [ListPaper] = []) {
        self.id = id
        self.name = name
        self.papers = papers
    }
}

/// A paper within a saved list.
public struct ListPaper: Codable, Identifiable, Hashable, Sendable {
    public let arxivId: String
    public let title: String
    public let authors: String
    public let link: String
    public let addedAt: Date

    public var id: String { arxivId }

    enum CodingKeys: String, CodingKey {
        case arxivId = "arxiv_id"
        case title
        case authors
        case link
        case addedAt = "added_at"
    }

    public init(arxivId: String, title: String, authors: String, link: String, addedAt: Date) {
        self.arxivId = arxivId
        self.title = title
        self.authors = authors
        self.link = link
        self.addedAt = addedAt
    }
}
