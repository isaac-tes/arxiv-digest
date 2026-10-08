import Foundation

/// The GUI's Papers-tab downloads: Markdown (`arxiv_digest.format_markdown`)
/// and JSON (the GUI's export payload).
public enum DigestExport {
    /// Port of `format_markdown(entries, total_papers, requested_top)`.
    public static func markdown(entries: [Paper], totalPapers: Int, requestedTop: Int) -> String {
        var lines = [
            "# Daily arXiv cond-mat/quant-ph digest",
            "",
            "Total papers fetched: \(totalPapers). Showing top \(min(requestedTop, totalPapers)) by relevance.",
            "",
        ]
        for e in entries {
            lines.append("## \(e.rank). \(e.title)")
            lines.append("- **Authors:** \(e.authors)")
            if !e.section.isEmpty { lines.append("- **Section:** \(e.section)") }
            if !e.subjects.isEmpty { lines.append("- **Subjects:** \(e.subjects)") }
            if !e.link.isEmpty { lines.append("- **Link:** \(e.link)") }
            lines.append("")
            lines.append(e.summary)
            lines.append("")
        }
        return lines.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    public static func markdown(_ digest: Digest) -> String {
        markdown(entries: digest.papers, totalPapers: digest.totalPapers, requestedTop: digest.requestedTop)
    }

    private struct Entry: Encodable {
        let rank: Int, id: String, title: String, authors: String, link: String
        let subjects: String, section: String, summary: String, score: Int
    }

    private struct Payload: Encodable {
        let generated_at: String
        let top_n: Int
        let total_papers: Int
        let entries: [Entry]
    }

    /// The GUI's JSON download: `{generated_at, top_n, total_papers, entries}`.
    public static func json(_ digest: Digest, generatedAt: Date = Date()) throws -> Data {
        let fmt = ISO8601DateFormatter()
        let payload = Payload(
            generated_at: fmt.string(from: generatedAt),
            top_n: digest.requestedTop,
            total_papers: digest.totalPapers,
            entries: digest.papers.map {
                Entry(rank: $0.rank, id: $0.id, title: $0.title, authors: $0.authors, link: $0.link,
                      subjects: $0.subjects, section: $0.section, summary: $0.summary, score: $0.score)
            }
        )
        let enc = JSONEncoder()
        enc.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        return try enc.encode(payload)
    }

    /// `digest-YYYY-MM-DD.<ext>`, the GUI's download file name.
    public static func fileName(ext: String, date: Date = Date()) -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        return "digest-\(f.string(from: date)).\(ext)"
    }
}
