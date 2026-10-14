import Foundation

/// Unsaved edits between the saved and the working config, grouped by where
/// they are edited: the web GUI's unsaved bar and tab dots, for the iOS
/// save bar and Config rows. Compares the raw fields: configs from the server
/// and the on-device store carry every field, so this is exact.
public enum ConfigDiff {
    /// Where a field is edited in the app (Config pages, else Settings).
    public enum Section: String, CaseIterable, Sendable {
        case keywords = "Keywords", authors = "Authors", lowPriority = "Low priority"
        case feeds = "Feeds", scoring = "Scoring", settings = "Settings"
    }

    public struct Change: Equatable, Sendable {
        public let section: Section
        /// "+ added", "− removed", "field: old → new".
        public let lines: [String]
    }

    /// Field → section, in display order. Fields that are a page's whole list
    /// get no field-name prefix.
    private static let fields: [(key: String, section: Section, own: Bool)] = [
        ("core_keywords", .keywords, true), ("named_authors", .authors, true),
        ("low_priority_kw", .lowPriority, true),
        ("feeds", .feeds, true), ("default_feeds", .feeds, false), ("include_replacements", .feeds, false),
        ("weights", .scoring, true), ("feed_weights", .scoring, false), ("word_boundary_matching", .scoring, false),
    ]

    public static func changes(saved: DigestConfig, current: DigestConfig) -> [Change] {
        let known = Set(fields.map(\.key))
        let others = Set(saved.data.keys).union(current.data.keys).subtracting(known).sorted()
        var lines: [Section: [String]] = [:]
        for (key, section, own) in fields + others.map({ ($0, Section.settings, false) }) {
            let old = saved.data[key], new = current.data[key]
            guard old != new else { continue }
            let prefix = own ? "" : label(key) + ": "
            lines[section, default: []] += describe(old, new, prettyKeys: key == "weights").map { prefix + $0 }
        }
        return Section.allCases.compactMap { s in lines[s].map { Change(section: s, lines: $0) } }
    }

    private static func label(_ key: String) -> String { key.replacingOccurrences(of: "_", with: " ") }

    private static func describe(_ old: JSONValue?, _ new: JSONValue?, prettyKeys: Bool) -> [String] {
        switch (old, new) {
        case (.array(let a)?, .array(let b)?):
            let lines = b.filter { !a.contains($0) }.map { "+ " + text($0) } + a.filter { !b.contains($0) }.map { "− " + text($0) }
            return lines.isEmpty ? ["reordered"] : lines
        case (.object(let a)?, .object(let b)?):
            let name = { (k: String) in prettyKeys ? label(k) : k }
            return b.keys.sorted().filter { a[$0] == nil }.map { "+ " + name($0) }
                + a.keys.sorted().filter { b[$0] == nil }.map { "− " + name($0) }
                + b.keys.sorted().compactMap { k in
                    guard let o = a[k], let n = b[k], o != n else { return nil }
                    return "\(name(k)): \(text(o)) → \(text(n))"
                }
        default:
            return ["\(old.map(text) ?? "—") → \(new.map(text) ?? "—")"]
        }
    }

    private static func text(_ v: JSONValue) -> String {
        switch v {
        case .string(let s): return s
        case .int(let i): return "\(i)"
        case .double(let d): return "\(d)"
        case .bool(let b): return b ? "true" : "false"
        case .array(let a): return a.map(text).joined(separator: ", ")
        case .object: return "{…}"
        case .null: return "—"
        }
    }
}
