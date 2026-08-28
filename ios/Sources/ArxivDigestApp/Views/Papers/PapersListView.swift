import SwiftUI
import ArxivDigestCore

/// The primary view: a ranked list of papers, mirroring the web GUI's Papers
/// tab. Each row shows rank, score, highlighted title/authors, subjects and an
/// arXiv link; tapping opens the full detail (breakdown + full abstract).
/// Search filters title/authors/summary; pull-to-refresh re-fetches.
struct PapersListView: View {
    @Environment(AppModel.self) private var model
    @State private var query = ""

    private var papers: [Paper] {
        PaperSearch.filter(model.digest?.papers ?? [], query: query)
    }

    var body: some View {
        NavigationStack {
            Group {
                if model.isLoading && model.digest == nil {
                    ProgressView("Fetching digest…")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if model.digest?.papers.isEmpty ?? true {
                    ContentUnavailableView(
                        "No papers",
                        systemImage: "doc.text.magnifyingglass",
                        description: Text(model.errorMessage ?? "Pull to refresh.")
                    )
                } else {
                    listContent
                }
            }
            .navigationTitle("arXiv Digest")
            #if os(iOS)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        Task { await model.loadDigest(refresh: true) }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .disabled(model.isLoading)
                }
            }
            #endif
        }
    }

    private var listContent: some View {
        List {
            if let digest = model.digest {
                Section {
                    ForEach(papers) { paper in
                        NavigationLink(value: paper) {
                            PaperRowView(paper: paper, config: model.config)
                        }
                    }
                } footer: {
                    Text("Showing \(papers.count) of \(digest.papers.count) ranked · \(digest.totalPapers) fetched.")
                }
            }
        }
        .listStyle(.plain)
        .searchable(text: $query, prompt: "Search title / authors / abstract")
        .refreshable { await model.loadDigest(refresh: true) }
        .navigationDestination(for: Paper.self) { paper in
            PaperDetailView(paper: paper)
        }
    }
}
