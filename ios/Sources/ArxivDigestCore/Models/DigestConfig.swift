import Foundation

/// The user's scoring configuration, mirroring the backend `Config` blob.
///
/// Stored as a JSON dictionary so it round-trips through `GET/PUT /config`
/// without the app needing to know every field the backend supports.
public struct DigestConfig: Codable, Sendable, Equatable {
    public var data: [String: JSONValue]

    public init(data: [String: JSONValue] = [:]) {
        self.data = data
    }

    // Convenience accessors for the fields the app edits directly.
    public var coreKeywords: [String] {
        get { data["core_keywords"]?.arrayValue ?? [] }
        set { data["core_keywords"] = .array(newValue.map { .string($0) }) }
    }

    public var namedAuthors: [String] {
        get { data["named_authors"]?.arrayValue ?? [] }
        set { data["named_authors"] = .array(newValue.map { .string($0) }) }
    }

    public var lowPriorityKeywords: [String] {
        get { data["low_priority_kw"]?.arrayValue ?? [] }
        set { data["low_priority_kw"] = .array(newValue.map { .string($0) }) }
    }

    public var topN: Int {
        get { data["top_n"]?.intValue ?? 20 }
        set { data["top_n"] = .int(newValue) }
    }

    public var timeframe: String {
        get { data["timeframe"]?.stringValue ?? "pastweek" }
        set { data["timeframe"] = .string(newValue) }
    }

    /// The arXiv feeds / cross-lists to fetch (e.g. `cond-mat.quant-gas`,
    /// `quant-ph`). Editable in the Config tab.
    public var defaultFeeds: [String] {
        get { data["default_feeds"]?.arrayValue ?? [] }
        set { data["default_feeds"] = .array(newValue.map { .string($0) }) }
    }

    /// Known feed names from the config's `feeds` map, offered as suggestions
    /// when choosing cross-lists.
    public var availableFeedNames: [String] {
        (data["feeds"]?.objectValue?.keys).map { Array($0).sorted() } ?? []
    }

    /// Feed name → arXiv listing URL (the GUI's Feeds tab).
    public var feeds: [String: String] {
        get { (data["feeds"]?.objectValue ?? [:]).compactMapValues(\.stringValue) }
        set { data["feeds"] = .object(newValue.mapValues { .string($0) }) }
    }

    /// Add or replace a feed. A blank URL defaults to the category's `/new`
    /// listing, the shape the engine's presets use (`_feeds_map`).
    public mutating func setFeed(name: String, url: String = "") {
        let n = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !n.isEmpty else { return }
        let u = url.trimmingCharacters(in: .whitespacesAndNewlines)
        feeds[n] = u.isEmpty ? Self.listingURL(for: n) : u
    }

    /// Remove a feed everywhere it is referenced: the feeds map, the subscribed
    /// feeds (as the GUI's Save feeds does) and its subject bonus (the GUI's
    /// per-feed fields follow the feeds list).
    public mutating func removeFeed(_ name: String) {
        feeds[name] = nil
        defaultFeeds.removeAll { $0 == name }
        feedWeights[name] = nil
    }

    /// Whether a configured feed is fetched (the GUI sidebar's Feeds multiselect).
    public func isSubscribed(_ name: String) -> Bool { defaultFeeds.contains(name) }

    public mutating func setSubscribed(_ on: Bool, feed name: String) {
        if on {
            if !defaultFeeds.contains(name) { defaultFeeds.append(name) }
        } else {
            defaultFeeds.removeAll { $0 == name }
        }
    }

    public static func listingURL(for category: String) -> String {
        "https://arxiv.org/list/\(category)/new"
    }

    /// Per-feed subject bonus (`feed_weights`): points added when the feed name
    /// appears in a paper's subjects.
    public var feedWeights: [String: Int] {
        get { (data["feed_weights"]?.objectValue ?? [:]).compactMapValues(\.intValue) }
        set { data["feed_weights"] = .object(newValue.mapValues { .int($0) }) }
    }

    /// Bonus for one feed (0 when unset). Setting 0 removes the entry, as the
    /// GUI's "Apply weights" drops zero bonuses.
    public func feedWeight(_ name: String) -> Int { feedWeights[name] ?? 0 }

    public mutating func setFeedWeight(_ value: Int, for name: String) {
        feedWeights[name] = value == 0 ? nil : value
    }

    public var includeReplacements: Bool {
        get { data["include_replacements"]?.boolValue ?? false }
        set { data["include_replacements"] = .bool(newValue) }
    }

    // MARK: - Scoring weights (`weights` object, `ScoringWeights` in the engine)

    /// Engine defaults (`arxiv_digest.ScoringWeights`).
    public static let defaultWeights: [ScoringWeight: Int] = [
        .coreKeyword: 6, .namedAuthor: 6, .lowPriorityPenalty: -5,
        .longAbstractBonus: 1, .longAbstractThreshold: 200,
    ]

    public func weight(_ w: ScoringWeight) -> Int {
        data["weights"]?.objectValue?[w.rawValue]?.intValue ?? Self.defaultWeights[w]!
    }

    public mutating func setWeight(_ value: Int, for w: ScoringWeight) {
        var obj = data["weights"]?.objectValue ?? [:]
        obj[w.rawValue] = .int(value)
        data["weights"] = .object(obj)
    }

    // MARK: - Highlight appearance (mirrors the GUI's per-aspect colors/toggles)

    /// Per-aspect highlight color as a hex string. Defaults match the GUI's
    /// `Config` defaults (blue keyword / red low-priority / green author).
    public func color(for aspect: HighlightAspect) -> String {
        switch aspect {
        case .keyword: return data["color_keyword"]?.stringValue ?? "#388bfd"
        case .lowPriority: return data["color_low_priority"]?.stringValue ?? "#f85149"
        case .author: return data["color_author"]?.stringValue ?? "#3fb950"
        case .subject: return data["color_subject"]?.stringValue ?? "#a371f7"
        }
    }

    public mutating func setColor(_ hex: String, for aspect: HighlightAspect) {
        data[Self.colorKey(aspect)] = .string(hex)
    }

    public var colorSubject: String {
        get { color(for: .subject) }
        set { setColor(newValue, for: .subject) }
    }

    /// Whether an aspect also tints the matched text's font (the GUI's
    /// `color_font_*` toggles). Defaults follow the engine: on for keywords and
    /// authors, off for low-priority and subjects.
    public func fontColor(for aspect: HighlightAspect) -> Bool {
        data[Self.fontKey(aspect)]?.boolValue ?? (aspect == .keyword || aspect == .author)
    }

    public mutating func setFontColor(_ on: Bool, for aspect: HighlightAspect) {
        data[Self.fontKey(aspect)] = .bool(on)
    }

    public var colorFontSubject: Bool {
        get { fontColor(for: .subject) }
        set { setFontColor(newValue, for: .subject) }
    }

    private static func colorKey(_ a: HighlightAspect) -> String {
        switch a {
        case .keyword: return "color_keyword"
        case .lowPriority: return "color_low_priority"
        case .author: return "color_author"
        case .subject: return "color_subject"
        }
    }

    private static func fontKey(_ a: HighlightAspect) -> String {
        switch a {
        case .keyword: return "color_font_keyword"
        case .lowPriority: return "color_font_low_priority"
        case .author: return "color_font_author"
        case .subject: return "color_font_subject"
        }
    }

    public var highlightAuthors: Bool {
        get { data["highlight_authors"]?.boolValue ?? true }
        set { data["highlight_authors"] = .bool(newValue) }
    }

    public var highlightTermsTitle: Bool {
        get { data["highlight_terms_title"]?.boolValue ?? true }
        set { data["highlight_terms_title"] = .bool(newValue) }
    }

    public var highlightTermsAbstract: Bool {
        get { data["highlight_terms_abstract"]?.boolValue ?? true }
        set { data["highlight_terms_abstract"] = .bool(newValue) }
    }

    /// Highlight the two-sentence summary on each paper card. Off by default,
    /// as in the GUI.
    public var highlightTermsSummary: Bool {
        get { data["highlight_terms_summary"]?.boolValue ?? false }
        set { data["highlight_terms_summary"] = .bool(newValue) }
    }

    public var wordBoundaryMatching: Bool {
        get { data["word_boundary_matching"]?.boolValue ?? true }
        set { data["word_boundary_matching"] = .bool(newValue) }
    }

    // MARK: - Editing helpers

    /// Clean a list-editor result the way the GUI's Save does: trim entries and
    /// drop blanks. Order is kept.
    public static func cleaned(_ items: [String]) -> [String] {
        items.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
    }

    /// Append `item` unless a case-insensitive duplicate exists. Returns false
    /// when nothing was added (blank or duplicate).
    @discardableResult
    public static func append(_ item: String, to list: inout [String]) -> Bool {
        let t = item.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty, !list.contains(where: { $0.caseInsensitiveCompare(t) == .orderedSame }) else {
            return false
        }
        list.append(t)
        return true
    }
}

/// The engine's `ScoringWeights` fields, in the GUI's Scoring-tab order.
public enum ScoringWeight: String, CaseIterable, Sendable, Identifiable {
    case coreKeyword = "core_keyword"
    case namedAuthor = "named_author"
    case lowPriorityPenalty = "low_priority_penalty"
    case longAbstractBonus = "long_abstract_bonus"
    case longAbstractThreshold = "long_abstract_threshold"

    public var id: String { rawValue }

    /// The GUI's label: the field name with underscores as spaces.
    public var label: String { rawValue.replacingOccurrences(of: "_", with: " ") }

    public var help: String {
        switch self {
        case .coreKeyword: return "Points per matched core keyword."
        case .namedAuthor: return "Points per matched named author."
        case .lowPriorityPenalty: return "Applied once if any low-priority term matches."
        case .longAbstractBonus: return "Added when the abstract is longer than the threshold."
        case .longAbstractThreshold: return "Abstract length (characters) for the bonus."
        }
    }
}

/// A minimal JSON value type so `DigestConfig` can hold arbitrary config fields
/// without a heavyweight dependency.
public enum JSONValue: Codable, Sendable, Equatable {
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)
    case array([JSONValue])
    case object([String: JSONValue])
    case null

    public var stringValue: String? {
        if case .string(let s) = self { return s }
        return nil
    }

    public var intValue: Int? {
        switch self {
        case .int(let i): return i
        case .double(let d) where d == d.rounded() && abs(d) < 1e15: return Int(d)
        default: return nil
        }
    }

    public var boolValue: Bool? {
        if case .bool(let b) = self { return b }
        return nil
    }

    public var arrayValue: [String]? {
        if case .array(let arr) = self {
            return arr.compactMap { $0.stringValue }
        }
        return nil
    }

    public var objectValue: [String: JSONValue]? {
        if case .object(let o) = self { return o }
        return nil
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() { self = .null; return }
        // Bool before numbers: some Foundation versions decode true/false as 1/0.
        if let b = try? container.decode(Bool.self) { self = .bool(b); return }
        if let s = try? container.decode(String.self) { self = .string(s); return }
        if let i = try? container.decode(Int.self) { self = .int(i); return }
        if let d = try? container.decode(Double.self) { self = .double(d); return }
        if let arr = try? container.decode([JSONValue].self) { self = .array(arr); return }
        if let obj = try? container.decode([String: JSONValue].self) { self = .object(obj); return }
        throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unsupported JSON value")
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let s): try container.encode(s)
        case .int(let i): try container.encode(i)
        case .double(let d): try container.encode(d)
        case .bool(let b): try container.encode(b)
        case .array(let a): try container.encode(a)
        case .object(let o): try container.encode(o)
        case .null: try container.encodeNil()
        }
    }
}
