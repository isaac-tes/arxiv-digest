import SwiftUI
import ArxivDigestCore

/// Score-a-paper: paste an arXiv link/ID and get its score, breakdown, and (if
/// it isn't in the current digest) an absence reason. Mirrors the Streamlit
/// Score-a-paper tab.
struct ScoreView: View {
    @Environment(AppModel.self) private var model

    @State private var arxivInput = ""
    @State private var result: ScoreResult?
    @State private var isScoring = false
    @State private var errorText: String?

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("arXiv ID or URL (e.g. 2601.01234)", text: $arxivInput)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .submitLabel(.search)
                        .onSubmit { runScore() }
                    Button {
                        runScore()
                    } label: {
                        if isScoring {
                            ProgressView()
                        } else {
                            Text("Score paper")
                        }
                    }
                    .disabled(trimmedInput.isEmpty || isScoring)
                } footer: {
                    Text("Scores against your current config — the same engine as the digest.")
                }

                if let errorText {
                    Section {
                        Label(errorText, systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.red)
                    }
                }

                if let result {
                    resultSections(result)
                }
            }
            .navigationTitle("Score a paper")
        }
    }

    private var trimmedInput: String {
        arxivInput.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    @ViewBuilder
    private func resultSections(_ result: ScoreResult) -> some View {
        if let reason = result.absenceReason {
            Section("Not in current digest") {
                Label(reason, systemImage: "info.circle")
                    .foregroundStyle(.secondary)
            }
        }

        if let paper = result.paper {
            let terms = HighlightEngine.matchedTerms(for: paper, config: model.config)
            Section("Paper") {
                HighlightedText(
                    text: paper.title,
                    keywords: model.config.highlightTermsTitle ? terms.keywords : [],
                    lowPriority: model.config.highlightTermsTitle ? terms.lowPriority : [],
                    config: model.config
                )
                .font(.headline)

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
            }

            Section("Abstract") {
                HighlightedText(
                    text: paper.abstract,
                    keywords: model.config.highlightTermsAbstract ? terms.keywords : [],
                    lowPriority: model.config.highlightTermsAbstract ? terms.lowPriority : [],
                    config: model.config
                )
                .font(.body)
            }

            if let url = URL(string: paper.link) {
                Section {
                    Link(destination: url) {
                        Label("Open on arXiv", systemImage: "safari")
                    }
                }
            }
        }

        Section("Why this score?") {
            ScoreBreakdownView(breakdown: result.breakdown, config: model.config)
        }
    }

    private func runScore() {
        let id = trimmedInput
        guard !id.isEmpty else { return }
        isScoring = true
        errorText = nil
        Task {
            let scored = await model.requestScore(arxivId: id)
            await MainActor.run {
                self.result = scored
                self.errorText = scored == nil ? (model.errorMessage ?? "Could not score that paper.") : nil
                self.isScoring = false
            }
        }
    }
}
