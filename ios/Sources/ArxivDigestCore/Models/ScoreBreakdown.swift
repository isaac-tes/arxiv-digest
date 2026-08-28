import Foundation

/// A single matched term and its weight, e.g. `("floquet", 6)`.
///
/// The backend serializes keyword/author hits as JSON 2-element arrays
/// (`[["floquet", 6]]`), so this type decodes that shape directly.
public struct TermHit: Codable, Hashable, Sendable {
    public let term: String
    public let weight: Int

    public init(term: String, weight: Int) {
        self.term = term
        self.weight = weight
    }

    public init(from decoder: Decoder) throws {
        var container = try decoder.unkeyedContainer()
        let term = try container.decode(String.self)
        let weight = try container.decode(Int.self)
        self.init(term: term, weight: weight)
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.unkeyedContainer()
        try container.encode(term)
        try container.encode(weight)
    }
}

/// The per-signal score breakdown for a paper (from `POST /score`).
///
/// The backend returns `{"signals": {"keyword": {...}}, "total": N}`. The app
/// renders this as the "why this score?" breakdown.
public struct ScoreBreakdown: Codable, Sendable {
    public let signals: [String: SignalBreakdown]
    public let total: Int

    public init(signals: [String: SignalBreakdown], total: Int) {
        self.signals = signals
        self.total = total
    }
}

/// A single signal's contribution to a paper's score.
public struct SignalBreakdown: Codable, Sendable {
    public let keywords: [TermHit]?
    public let authors: [TermHit]?
    public let subjects: [String: Int]?
    public let lowPriorityHits: [String]?
    public let lowPriorityPenalty: Int?
    public let abstractBonus: Int?
    public let total: Int?

    enum CodingKeys: String, CodingKey {
        case keywords
        case authors
        case subjects
        case lowPriorityHits = "low_priority_hits"
        case lowPriorityPenalty = "low_priority_penalty"
        case abstractBonus = "abstract_bonus"
        case total
    }

    public init(
        keywords: [TermHit]? = nil,
        authors: [TermHit]? = nil,
        subjects: [String: Int]? = nil,
        lowPriorityHits: [String]? = nil,
        lowPriorityPenalty: Int? = nil,
        abstractBonus: Int? = nil,
        total: Int? = nil
    ) {
        self.keywords = keywords
        self.authors = authors
        self.subjects = subjects
        self.lowPriorityHits = lowPriorityHits
        self.lowPriorityPenalty = lowPriorityPenalty
        self.abstractBonus = abstractBonus
        self.total = total
    }
}
