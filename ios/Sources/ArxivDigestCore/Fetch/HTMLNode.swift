import Foundation

/// A minimal HTML tree, built the way BeautifulSoup's `html.parser` builder
/// does for arXiv's listing pages: void elements never open, an end tag closes
/// up to its matching open element (stray end tags are ignored), comments and
/// script/style bodies are dropped. Enough for `listingDayLabels`, not a
/// general HTML parser.
/// ponytail: only common named entities (plus numeric ones) are decoded, not
/// html.unescape's full HTML5 table; add names when arXiv markup needs them.
final class HTMLNode {
    let name: String  // "" for a text node
    let attributes: [String: String]
    let text: String
    private(set) var children: [HTMLNode] = []
    private(set) weak var parent: HTMLNode?

    private init(name: String, attributes: [String: String] = [:], text: String = "") {
        self.name = name
        self.attributes = attributes
        self.text = text
    }

    /// BeautifulSoup's `find(name, class_=cls)`: the first descendant with this
    /// tag and, if given, this token in its `class` list.
    func find(_ name: String, class cls: String? = nil) -> HTMLNode? {
        descendants.first { $0.name == name && (cls == nil || $0.classes.contains(cls!)) }
    }

    func findAll(_ name: String) -> [HTMLNode] { descendants.filter { $0.name == name } }

    var classes: [String] { (attributes["class"] ?? "").split(whereSeparator: \.isWhitespace).map(String.init) }

    private static let entities: [String: String] = [
        "amp": "&", "lt": "<", "gt": ">", "quot": "\"", "apos": "'", "nbsp": "\u{00A0}",
        "ndash": "\u{2013}", "mdash": "\u{2014}", "hellip": "\u{2026}", "lsquo": "\u{2018}",
        "rsquo": "\u{2019}", "ldquo": "\u{201C}", "rdquo": "\u{201D}",
    ]
    private static let entity = try! NSRegularExpression(pattern: "&(#[0-9]+|#[xX][0-9a-fA-F]+|[a-zA-Z]+);")

    /// `html.unescape` for the entities above and numeric references.
    static func unescape(_ s: String) -> String {
        guard s.contains("&") else { return s }
        let ns = s as NSString
        var out = "", last = 0
        for m in entity.matches(in: s, range: NSRange(location: 0, length: ns.length)) {
            let body = ns.substring(with: m.range(at: 1))
            let decoded: String?
            if body.hasPrefix("#x") || body.hasPrefix("#X") {
                decoded = UInt32(body.dropFirst(2), radix: 16).flatMap(Unicode.Scalar.init).map { String(Character($0)) }
            } else if body.hasPrefix("#") {
                decoded = UInt32(body.dropFirst()).flatMap(Unicode.Scalar.init).map { String(Character($0)) }
            } else {
                decoded = entities[body]
            }
            guard let decoded else { continue }
            out += ns.substring(with: NSRange(location: last, length: m.range.location - last)) + decoded
            last = m.range.upperBound
        }
        return out + ns.substring(from: last)
    }

    /// Element descendants in document order.
    var descendants: [HTMLNode] {
        children.filter { !$0.name.isEmpty }.flatMap { [$0] + $0.descendants }
    }

    /// BeautifulSoup's `get_text(separator, strip=True)`.
    func text(separator: String) -> String {
        func strings(_ n: HTMLNode) -> [String] { n.name.isEmpty ? [n.text] : n.children.flatMap(strings) }
        return strings(self).map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }.joined(separator: separator)
    }

    private func append(_ child: HTMLNode) {
        child.parent = self
        children.append(child)
    }

    static let voidElements: Set<String> = [
        "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr",
    ]

    private static let token = try! NSRegularExpression(
        pattern: "<!--.*?-->|<![^>]*>|<\\?[^>]*>|<(/?)([a-zA-Z][a-zA-Z0-9:-]*)((?:[^>\"']|\"[^\"]*\"|'[^']*')*)>",
        options: [.dotMatchesLineSeparators])
    private static let attribute = try! NSRegularExpression(
        pattern: "([^\\s=/>]+)(?:\\s*=\\s*(?:\"([^\"]*)\"|'([^']*)'|([^\\s>]+)))?")

    static func parse(_ html: String) -> HTMLNode {
        let root = HTMLNode(name: "#document")
        var stack = [root]
        let ns = html as NSString
        var cursor = 0
        var rawTextEnd: String?  // inside <script>/<style>: skip to this end tag

        func addText(upTo end: Int) {
            guard end > cursor else { return }
            stack.last!.append(HTMLNode(name: "", text: unescape(ns.substring(with: NSRange(location: cursor, length: end - cursor)))))
        }

        for m in token.matches(in: html, range: NSRange(location: 0, length: ns.length)) {
            guard m.range.location >= cursor else { continue }
            let isTag = m.range(at: 2).location != NSNotFound
            let name = isTag ? ns.substring(with: m.range(at: 2)).lowercased() : ""
            let closing = isTag && m.range(at: 1).length > 0
            if let end = rawTextEnd {
                guard closing, name == end else { continue }
                rawTextEnd = nil
                cursor = m.range.upperBound
                stack.removeLast()
                continue
            }
            addText(upTo: m.range.location)
            cursor = m.range.upperBound
            guard isTag else { continue }  // comment / doctype

            if closing {
                if let i = stack.lastIndex(where: { $0.name == name }), i > 0 { stack.removeSubrange(i...) }
                continue
            }
            let rawAttrs = ns.substring(with: m.range(at: 3))
            var attrs: [String: String] = [:]
            for a in attribute.matches(in: rawAttrs, range: NSRange(location: 0, length: (rawAttrs as NSString).length)) {
                let key = (rawAttrs as NSString).substring(with: a.range(at: 1)).lowercased()
                let value = (2...4).lazy.map { a.range(at: $0) }.first { $0.location != NSNotFound }
                    .map { (rawAttrs as NSString).substring(with: $0) } ?? ""
                if attrs[key] == nil { attrs[key] = unescape(value) }
            }
            let node = HTMLNode(name: name, attributes: attrs)
            stack.last!.append(node)
            if voidElements.contains(name) || rawAttrs.hasSuffix("/") { continue }
            stack.append(node)
            if name == "script" || name == "style" { rawTextEnd = name }
        }
        if rawTextEnd == nil { addText(upTo: ns.length) }
        return root
    }
}
