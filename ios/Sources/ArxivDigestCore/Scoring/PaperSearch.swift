import Foundation

/// Client-side search over an already-fetched digest, mirroring the web GUI's
/// Papers-tab search box: a case-insensitive substring match against a paper's
/// title, authors, and abstract (the full abstract when the server sent it). An empty/whitespace query returns everything.
public enum PaperSearch {
    public static func filter(_ papers: [Paper], query: String) -> [Paper] {
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !q.isEmpty else { return papers }
        return papers.filter { paper in
            paper.title.lowercased().contains(q)
                || paper.authors.lowercased().contains(q)
                || paper.fullAbstract.lowercased().contains(q)
        }
    }
}
