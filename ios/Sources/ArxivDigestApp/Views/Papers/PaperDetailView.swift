import SwiftUI
import ArxivDigestCore

/// Full paper detail, mirroring the web GUI paper card + its "Why this score?"
/// and "Full abstract" expanders: highlighted title/authors, subjects, the full
/// abstract (fetched via `/score`, since the digest only carries a summary), the
/// per-signal score breakdown, and an arXiv link.
struct PaperDetailView: View {
    let paper: Paper
    @Environment(AppModel.self) private var model

    @State private var result: ScoreResult?
    @State private var isLoading = false
    @State private var isSavingZotero = false
    @State private var zoteroAlert: String?

    private var terms: HighlightTerms {
        HighlightEngine.matchedTerms(for: paper, config: model.config)
    }

    /// Prefer the full abstract from /score; fall back to the digest summary.
    private var abstractText: String {
        result?.paper?.abstract ?? paper.summary
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack(alignment: .top) {
                    HighlightedText(
                        text: paper.title,
                        keywords: model.config.highlightTermsTitle ? terms.keywords : [],
                        lowPriority: model.config.highlightTermsTitle ? terms.lowPriority : [],
                        config: model.config
                    )
                    .font(.title2)
                    .fontWeight(.bold)
                    Spacer(minLength: 8)
                    Text("\(paper.score)")
                        .font(.title3.weight(.bold))
                        .foregroundStyle(.blue)
                }

                HighlightedText(
                    text: paper.authors,
                    authors: model.config.highlightAuthors ? terms.authors : [],
                    config: model.config
                )
                .font(.subheadline)
                .foregroundStyle(.secondary)

                if !paper.subjects.isEmpty {
                    Text(paper.subjects)
                        .font(.caption)
                        .foregroundStyle(Color(hex: model.config.colorSubject))
                }
                if !paper.section.isEmpty {
                    Text(paper.section).font(.caption2).foregroundStyle(.tertiary)
                }

                Divider()

                Text("Abstract").font(.headline)
                if isLoading && result == nil {
                    HStack { ProgressView(); Text("Loading full abstract…").foregroundStyle(.secondary) }
                }
                HighlightedText(
                    text: abstractText,
                    keywords: model.config.highlightTermsAbstract ? terms.keywords : [],
                    lowPriority: model.config.highlightTermsAbstract ? terms.lowPriority : [],
                    config: model.config
                )
                .font(.body)

                Divider()

                Text("Why this score?").font(.headline)
                if let result {
                    ScoreBreakdownView(breakdown: result.breakdown, config: model.config)
                } else if isLoading {
                    HStack { ProgressView(); Text("Loading breakdown…").foregroundStyle(.secondary) }
                } else {
                    Text("Score: \(paper.score)").font(.headline).foregroundStyle(.blue)
                }

                if let url = URL(string: paper.link) {
                    Link(destination: url) {
                        Label("Open on arXiv", systemImage: "safari")
                    }
                    .padding(.top, 4)
                }

                zoteroSection
            }
            .padding()
        }
        .navigationTitle("Paper")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .task { await load() }
        .task { await model.refreshZoteroAvailability() }
        .alert("Zotero", isPresented: zoteroAlertPresented) {
            Button("OK", role: .cancel) { zoteroAlert = nil }
        } message: {
            Text(zoteroAlert ?? "")
        }
    }

    /// "Save to Zotero", shown only when the server has a Web API key. When it
    /// doesn't, an explanatory row keeps the feature discoverable without firing
    /// a deep-link that can't actually create an item.
    @ViewBuilder
    private var zoteroSection: some View {
        Divider()
        switch model.zoteroAvailability {
        case .web:
            Button {
                Task { await saveToZotero() }
            } label: {
                if isSavingZotero {
                    HStack { ProgressView(); Text("Saving to Zotero…") }
                } else {
                    Label("Save to Zotero", systemImage: "tray.and.arrow.down")
                }
            }
            .disabled(isSavingZotero)
        case .unavailable:
            Label("Zotero saving not configured on the server", systemImage: "info.circle")
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
    }

    private var zoteroAlertPresented: Binding<Bool> {
        Binding(get: { zoteroAlert != nil }, set: { if !$0 { zoteroAlert = nil } })
    }

    private func saveToZotero() async {
        isSavingZotero = true
        defer { isSavingZotero = false }
        let result = await model.saveToZotero(arxivId: paper.id)
        zoteroAlert = result?.message ?? model.errorMessage ?? "Could not save to Zotero."
    }

    private func load() async {
        guard result == nil, !isLoading else { return }
        isLoading = true
        defer { isLoading = false }
        result = await model.requestScore(arxivId: paper.id)
    }
}
