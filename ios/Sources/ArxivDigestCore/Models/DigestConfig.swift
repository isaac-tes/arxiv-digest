import Foundation

/// The user's scoring configuration, mirroring the backend `Config` blob.
///
/// Stored as a JSON dictionary so it round-trips through `GET/PUT /config`
/// without the app needing to know every field the backend supports.
public struct DigestConfig: Codable, Sendable {
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

    // MARK: - Highlight appearance (mirrors the GUI's per-aspect colors/toggles)

    /// Per-aspect highlight color as a hex string. Defaults match the GUI's
    /// `Config` defaults (blue keyword / red low-priority / green author).
    public func color(for aspect: HighlightAspect) -> String {
        switch aspect {
        case .keyword: return data["color_keyword"]?.stringValue ?? "#388bfd"
        case .lowPriority: return data["color_low_priority"]?.stringValue ?? "#f85149"
        case .author: return data["color_author"]?.stringValue ?? "#3fb950"
        }
    }

    public mutating func setColor(_ hex: String, for aspect: HighlightAspect) {
        switch aspect {
        case .keyword: data["color_keyword"] = .string(hex)
        case .lowPriority: data["color_low_priority"] = .string(hex)
        case .author: data["color_author"] = .string(hex)
        }
    }

    public var colorSubject: String {
        get { data["color_subject"]?.stringValue ?? "#a371f7" }
        set { data["color_subject"] = .string(newValue) }
    }

    /// Whether an aspect colors the text itself (font) instead of drawing a
    /// background highlight — the GUI's `color_font_*` toggles.
    public func fontColor(for aspect: HighlightAspect) -> Bool {
        switch aspect {
        case .keyword: return data["color_font_keyword"]?.boolValue ?? false
        case .lowPriority: return data["color_font_low_priority"]?.boolValue ?? false
        case .author: return data["color_font_author"]?.boolValue ?? false
        }
    }

    public mutating func setFontColor(_ on: Bool, for aspect: HighlightAspect) {
        switch aspect {
        case .keyword: data["color_font_keyword"] = .bool(on)
        case .lowPriority: data["color_font_low_priority"] = .bool(on)
        case .author: data["color_font_author"] = .bool(on)
        }
    }

    public var colorFontSubject: Bool {
        get { data["color_font_subject"]?.boolValue ?? false }
        set { data["color_font_subject"] = .bool(newValue) }
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

    public var wordBoundaryMatching: Bool {
        data["word_boundary_matching"]?.boolValue ?? true
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
        if case .int(let i) = self { return i }
        return nil
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
        if let s = try? container.decode(String.self) { self = .string(s); return }
        if let i = try? container.decode(Int.self) { self = .int(i); return }
        if let d = try? container.decode(Double.self) { self = .double(d); return }
        if let b = try? container.decode(Bool.self) { self = .bool(b); return }
        if let arr = try? container.decode([JSONValue].self) { self = .array(arr); return }
        if let obj = try? container.decode([String: JSONValue].self) { self = .object(obj); return }
        if container.decodeNil() { self = .null; return }
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
