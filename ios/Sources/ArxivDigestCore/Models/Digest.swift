import Foundation

/// The ranked digest response from `GET /digest`.
public struct Digest: Codable, Sendable {
    public let papers: [Paper]
    public let totalPapers: Int
    public let requestedTop: Int

    enum CodingKeys: String, CodingKey {
        case papers
        case totalPapers = "total_papers"
        case requestedTop = "requested_top"
    }

    public init(papers: [Paper], totalPapers: Int, requestedTop: Int) {
        self.papers = papers
        self.totalPapers = totalPapers
        self.requestedTop = requestedTop
    }
}
