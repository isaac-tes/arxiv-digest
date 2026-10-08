import Foundation

/// A fetched, unscored paper: the engine's paper dict (`id`, `title`, `authors`,
/// `abstract`, `subjects`, `link`, `section`). Missing fields decode as "".
public struct RawPaper: Codable, Hashable, Sendable {
    public var id: String
    public var title: String
    public var authors: String
    public var abstract: String
    public var subjects: String
    public var link: String
    public var section: String

    public init(id: String, title: String, authors: String, abstract: String,
                subjects: String, link: String = "", section: String = "") {
        self.id = id
        self.title = title
        self.authors = authors
        self.abstract = abstract
        self.subjects = subjects
        self.link = link
        self.section = section
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        func field(_ k: CodingKeys) throws -> String { try c.decodeIfPresent(String.self, forKey: k) ?? "" }
        self.init(id: try field(.id), title: try field(.title), authors: try field(.authors),
                  abstract: try field(.abstract), subjects: try field(.subjects),
                  link: try field(.link), section: try field(.section))
    }
}
