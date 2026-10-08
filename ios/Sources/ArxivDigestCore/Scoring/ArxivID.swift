import Foundation

/// arXiv id parsing, ported from `zotero_bridge.arxiv_id_from_input`.
public enum ArxivID {
    private static let urlRE = try! NSRegularExpression(
        pattern: #"arxiv\.org/(?:abs|pdf)/([^?#]+?)(?:\.pdf)?(?:v\d+)?$"#, options: [.caseInsensitive])
    private static let prefixRE = try! NSRegularExpression(pattern: #"^\s*arxiv\s*:\s*"#, options: [.caseInsensitive])
    private static let versionRE = try! NSRegularExpression(pattern: #"(?<=\d)v\d+$"#, options: [.caseInsensitive])
    private static let wellFormedRE = try! NSRegularExpression(
        pattern: #"^(?:\d{4}\.\d{4,5}|[a-z][a-z\-]*(?:\.[a-z]{2})?/\d{7})$"#, options: [.caseInsensitive])

    /// A canonical id from a URL, bare id, or `arXiv:xxxx`; nil if blank.
    /// URL query strings / fragments are dropped first (a pasted
    /// `…/abs/2609.21407v2?context=quant-ph` still parses).
    public static func parse(_ raw: String) -> String? {
        var text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if let cut = text.firstIndex(where: { $0 == "?" || $0 == "#" }), text.lowercased().contains("arxiv.org/") {
            text = String(text[..<cut])
        }
        guard !text.isEmpty else { return nil }
        let ns = NSRange(text.startIndex..., in: text)
        if let m = urlRE.firstMatch(in: text, range: ns), let r = Range(m.range(at: 1), in: text) {
            // Also drop a version left before `.pdf` (`/pdf/2609.21407v1.pdf`),
            // which the Python helper keeps.
            let raw = text[r].trimmingCharacters(in: .whitespaces)
            let id = versionRE.stringByReplacingMatches(
                in: raw, range: NSRange(raw.startIndex..., in: raw), withTemplate: "")
            return id.isEmpty ? nil : id
        }
        let noPrefix = prefixRE.stringByReplacingMatches(in: text, range: ns, withTemplate: "")
            .trimmingCharacters(in: .whitespaces)
        let id = versionRE.stringByReplacingMatches(
            in: noPrefix, range: NSRange(noPrefix.startIndex..., in: noPrefix), withTemplate: "")
        return id.isEmpty ? nil : id
    }

    /// Whether `id` has the shape of an arXiv identifier (new `2609.21407` or
    /// old `cond-mat/0601001` style).
    public static func isWellFormed(_ id: String) -> Bool {
        wellFormedRE.firstMatch(in: id, range: NSRange(id.startIndex..., in: id)) != nil
    }
}
