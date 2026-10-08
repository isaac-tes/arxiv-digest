import SwiftUI
import UIKit
import ArxivDigestCore

/// Score a paper: paste an arXiv link or ID to see how it would score under
/// the saved config, and why it did (or didn't) appear in the digest. Mirrors
/// the GUI tab: the placement uses the same view as the Papers tab (ADR 0008).
struct ScoreView: View {
    @AppStorage(Highlight.underlineKey) private var underline = false
    @Environment(AppModel.self) private var model
    @Binding var input: String
    @Binding var runRequest: Int

    @State private var result: ScoreResult?
    @State private var errorText: String?
    @State private var isScoring = false
    /// The last `runRequest` handled, so revisiting the tab doesn't re-score.
    @State private var handledRun = 0
    @FocusState private var focused: Bool

    private var parsedID: String? { ArxivID.parse(input) }

    var body: some View {
        NavigationStack {
            Form {
                inputSection
                if let errorText {
                    Section { Callout(style: .error) { Text(errorText) } }
                        .listRowInsets(EdgeInsets())
                        .listRowBackground(Color.clear)
                }
                if let result { resultSections(result) }
            }
            .navigationTitle("Score a paper")
            .task(id: runRequest) {
                guard runRequest != handledRun else { return }
                handledRun = runRequest
                run()
            }
        }
    }

    private var inputSection: some View {
        Section {
            HStack {
                TextField("https://arxiv.org/abs/2609.21407  or  2609.21407", text: $input)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)
                    .submitLabel(.go)
                    .focused($focused)
                    .onSubmit(run)
                if !input.isEmpty {
                    Button { input = ""; result = nil; errorText = nil } label: {
                        Image(systemName: "xmark.circle.fill").foregroundStyle(.tertiary)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Clear")
                }
            }
            HStack {
                PasteButton(payloadType: String.self) { strings in
                    guard let s = strings.first else { return }
                    Task { @MainActor in
                        input = s
                        run()
                    }
                }
                .labelStyle(.titleAndIcon)
                .buttonBorderShape(.capsule)
                Spacer()
                Button(action: run) {
                    if isScoring {
                        ProgressView()
                    } else {
                        Label("Score this paper", systemImage: "gauge.with.dots.needle.67percent")
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(parsedID == nil || isScoring)
            }
        } footer: {
            if let id = parsedID, !ArxivID.isWellFormed(id) {
                Text("“\(id)” doesn't look like an arXiv id; arXiv may not find it.")
            } else {
                Text("Uses your saved config and the Papers tab's timeframe, Top N and day.")
            }
        }
    }

    @ViewBuilder
    private func resultSections(_ r: ScoreResult) -> some View {
        if let paper = r.paper {
            Section {
                VStack(alignment: .leading, spacing: 8) {
                    HStack(alignment: .top) {
                        Text(Highlight.terms(paper.title, enabled: model.config.highlightTermsTitle, config: model.config, underline: underline))
                            .font(.headline)
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        ScoreBadge(score: r.breakdown.total, large: true)
                    }
                    Text(Highlight.authors(paper.authors, config: model.config, underline: underline))
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    if !paper.subjects.isEmpty {
                        Text(Highlight.subjects(paper.subjects, config: model.config, underline: underline)).font(.caption)
                    }
                }
                .padding(.vertical, 4)
            }

            Section("Why it did / didn't appear in the digest") {
                placement(r)
                    .listRowInsets(EdgeInsets(top: 8, leading: 8, bottom: 8, trailing: 8))
            }

            Section("Why this score?") {
                ScoreBreakdownView(breakdown: r.breakdown, config: model.config, showTotal: false)
                    .padding(.vertical, 4)
            }

            Section {
                DisclosureGroup("Full abstract") {
                    Text(Highlight.terms(paper.abstract, enabled: model.config.highlightTermsAbstract, config: model.config, underline: underline))
                        .font(.callout)
                        .textSelection(.enabled)
                }
            }

            Section {
                if let url = absURL(paper.link) {
                    Link(destination: url) { Label("Open on arXiv", systemImage: "safari") }
                }
                ZoteroButton(arxivId: paper.id, link: paper.link, title: paper.title)
            }
        } else {
            Section {
                Callout(style: .warning) {
                    Text("No arXiv paper found for “\(parsedID ?? input)”.")
                }
            }
            .listRowInsets(EdgeInsets())
            .listRowBackground(Color.clear)
        }
    }

    @ViewBuilder
    private func placement(_ r: ScoreResult) -> some View {
        if let rank = r.rank {
            Callout(style: .success) {
                MarkdownText("This paper **is** in the current digest at rank **#\(rank)** with score **\(r.breakdown.total)**.")
            }
        } else if let reason = r.absenceReason {
            Callout(style: .info) { MarkdownText(reason) }
        }
    }

    private func run() {
        guard let id = parsedID, !isScoring else {
            if parsedID == nil, !input.trimmingCharacters(in: .whitespaces).isEmpty {
                errorText = "Could not parse an arXiv id from that input."
            }
            return
        }
        focused = false
        isScoring = true
        errorText = nil
        Task {
            switch await model.score(id) {
            case .success(let r):
                result = r
            case .failure(let e):
                result = nil
                errorText = "Failed to fetch paper: \(e.localizedDescription)"
            }
            isScoring = false
        }
    }
}
