import SwiftUI
import ArxivDigestCore

/// A paper's full card: the GUI card plus its "Why this score?" and
/// "Full abstract" expanders, opened. The digest already carries the abstract
/// and breakdown; an older server without them falls back to `/score`.
struct PaperDetailView: View {
    @AppStorage(Highlight.underlineKey) private var underline = false
    let paper: Paper
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL

    @State private var fetched: ScoreResult?
    @State private var isFetching = false
    @State private var fetchFailed = false

    private var config: DigestConfig { model.config }
    private var abstract: String {
        if let a = fetched?.paper?.abstract, !a.isEmpty { return a }
        return paper.fullAbstract
    }
    private var breakdown: ScoreBreakdown? { paper.breakdown ?? fetched?.breakdown }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                header
                actions
                card("Abstract", systemImage: "text.alignleft") {
                    if isFetching && paper.abstract.isEmpty {
                        HStack { ProgressView(); Text("Loading full abstract…").foregroundStyle(.secondary) }
                    }
                    if MathText.mathRanges(in: abstract).isEmpty {
                        Text(Highlight.terms(abstract, enabled: config.highlightTermsAbstract, config: config, underline: underline))
                            .font(.body)
                            .textSelection(.enabled)
                            .fixedSize(horizontal: false, vertical: true)
                    } else {
                        MathAbstractView(abstract: abstract, config: config, underline: underline)
                    }
                }
                card("Why this score?", systemImage: "chart.bar.doc.horizontal") {
                    if let breakdown {
                        ScoreBreakdownView(breakdown: breakdown, config: config)
                    } else if isFetching {
                        HStack { ProgressView(); Text("Loading breakdown…").foregroundStyle(.secondary) }
                    } else {
                        Text("Score \(paper.score)").font(.headline)
                        if fetchFailed {
                            Button("Couldn't load the breakdown. Try again") {
                                Task { await loadIfNeeded() }
                            }
                            .font(.footnote)
                        }
                    }
                }
                Button(role: .destructive) {
                    dismiss()
                    let model = model, paper = paper
                    Task { await model.remove(paper) }
                } label: {
                    Label("Remove from digest", systemImage: "eye.slash")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
                Text("Removing hides this paper from this and later rankings; the papers below move up one place. Restore it from Removed papers.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding()
        }
        .navigationTitle("#\(paper.rank)")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                if let url = absURL(paper.link) {
                    ShareLink(item: url, subject: Text(paper.title)) {
                        Label("Share", systemImage: "square.and.arrow.up")
                    }
                }
            }
        }
        .task { await loadIfNeeded() }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 12) {
                Text(Highlight.terms(paper.title, enabled: config.highlightTermsTitle, config: config, underline: underline))
                    .font(.title2.weight(.bold))
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                ScoreBadge(score: paper.score, large: true)
            }
            let addable = config.addableAuthors(in: paper.authors)
            Menu {
                Section("Add to highlighted authors") {
                    ForEach(addable, id: \.self) { name in
                        Button(name) { model.addNamedAuthor(name) }
                    }
                }
            } label: {
                Text(Highlight.authors(paper.authors, config: config, underline: underline))
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.leading)
            }
            .buttonStyle(.plain)  // keep the author text colors, not the accent tint
            .disabled(addable.isEmpty)
            HStack(spacing: 6) {
                Text(paper.id).font(.caption.monospaced())
                if !paper.section.isEmpty {
                    Text("·")
                    Text(paper.section).font(.caption)
                }
            }
            .foregroundStyle(.secondary)
            if !paper.subjects.isEmpty {
                (Text("Subjects: ").foregroundStyle(.secondary) + Text(Highlight.subjects(paper.subjects, config: config, underline: underline)))
                    .font(.caption)
            }
        }
    }

    private var actions: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                if let url = absURL(paper.link) {
                    Button { openURL(url) } label: { Label("arXiv", systemImage: "safari") }
                }
                if let pdf = paper.pdfURL {
                    Button { openURL(pdf) } label: { Label("PDF", systemImage: "doc.richtext") }
                }
                ZoteroButton(arxivId: paper.id, link: paper.link, title: paper.title)
            }
            .buttonStyle(.bordered)
        }
    }

    private func card<Content: View>(_ title: String, systemImage: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(title, systemImage: systemImage).font(.headline)
            content()
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private func loadIfNeeded() async {
        guard paper.breakdown == nil || paper.abstract.isEmpty, fetched == nil, !isFetching else { return }
        isFetching = true
        defer { isFetching = false }
        if case .success(let r) = await model.score(paper.id) {
            fetched = r
            fetchFailed = false
        } else {
            fetchFailed = true
        }
    }
}
