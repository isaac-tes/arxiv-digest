import Foundation

/// A minimal HTML tree, built the way BeautifulSoup's `html.parser` builder
/// does for arXiv's listing pages: void elements never open, an end tag closes
/// up to its matching open element (stray end tags are ignored), comments and
/// script/style bodies are dropped. Enough for `listingDayLabels`, not a
/// general HTML parser.
/// ponytail: entities in text and attributes stay undecoded; arXiv ids and day
/// labels contain none.
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
            stack.last!.append(HTMLNode(name: "", text: ns.substring(with: NSRange(location: cursor, length: end - cursor))))
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
                if attrs[key] == nil { attrs[key] = value }
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
