import SwiftUI
import ArxivDigestCore

/// The Config tab: the web GUI's Keywords / Authors / Low priority / Feeds /
/// Scoring / Profiles tabs as pages. Edits change the working config only;
/// the save bar persists them and re-ranks the digest.
struct ConfigView: View {
    @Environment(AppModel.self) private var model
    @Binding var path: [ConfigPage]

    var body: some View {
        NavigationStack(path: $path) {
            List {
                if model.configError != nil && !model.hasLoadedConfig {
                    Section { ConfigLoadBanner() }
                        .listRowInsets(EdgeInsets())
                        .listRowBackground(Color.clear)
                }
                Section {
                    summary
                }
                Section("What you're looking for") {
                    row(.keywords, count: model.config.coreKeywords.count, color: model.config.color(for: .keyword))
                    row(.authors, count: model.config.namedAuthors.count, color: model.config.color(for: .author))
                    row(.lowPriority, count: model.config.lowPriorityKeywords.count, color: model.config.color(for: .lowPriority))
                }
                Section("Where and how") {
                    row(.feeds, detail: "\(model.config.defaultFeeds.count) of \(model.config.feeds.count) subscribed",
                        color: model.config.color(for: .subject))
                    row(.scoring, detail: "+\(model.config.weight(.coreKeyword)) / +\(model.config.weight(.namedAuthor)) / \(model.config.weight(.lowPriorityPenalty))")
                }
                Section {
                    row(.presets, detail: "\(model.presets.count) bundles")
                } footer: {
                    Text("Changes stay on this device until you tap Save; saving re-ranks the digest.")
                }
            }
            .navigationTitle("Config")
            .navigationDestination(for: ConfigPage.self) { page in
                switch page {
                case .keywords:
                    TermListEditor(page: page, keyPath: \.coreKeywords, aspect: .keyword,
                                   caption: "Each matched keyword adds +\(model.config.weight(.coreKeyword)). Matched in title, abstract, authors and subjects.")
                case .authors:
                    TermListEditor(page: page, keyPath: \.namedAuthors, aspect: .author,
                                   caption: "Each matched author adds +\(model.config.weight(.namedAuthor)). Matched against the author list only. A full name (“Ada Lovelace”) also matches “Ada M. Lovelace”.")
                case .lowPriority:
                    TermListEditor(page: page, keyPath: \.lowPriorityKeywords, aspect: .lowPriority,
                                   caption: "Any match applies \(model.config.weight(.lowPriorityPenalty)) once.")
                case .feeds: FeedsEditor()
                case .scoring: ScoringEditor()
                case .presets: PresetsView()
                }
            }
            .safeAreaInset(edge: .bottom) { if model.isDirty { SaveBar() } }
            .animation(.default, value: model.isDirty)
        }
    }

    private var summary: some View {
        HStack(spacing: 0) {
            stat("\(model.config.coreKeywords.count)", "keywords", model.config.color(for: .keyword))
            stat("\(model.config.namedAuthors.count)", "authors", model.config.color(for: .author))
            stat("\(model.config.lowPriorityKeywords.count)", "low priority", model.config.color(for: .lowPriority))
            stat("\(model.config.defaultFeeds.count)", "feeds", model.config.color(for: .subject))
        }
        .padding(.vertical, 6)
    }

    private func stat(_ value: String, _ label: String, _ hex: String) -> some View {
        VStack(spacing: 2) {
            Text(value).font(.title2.weight(.bold)).monospacedDigit().foregroundStyle(Color(hex: hex))
            Text(label).font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    private func row(_ page: ConfigPage, count: Int? = nil, detail: String? = nil, color: String? = nil) -> some View {
        NavigationLink(value: page) {
            HStack {
                Label {
                    Text(page.title)
                } icon: {
                    Image(systemName: page.systemImage)
                        .foregroundStyle(color.map { Color(hex: $0) } ?? Color.accentColor)
                }
                Spacer()
                if let count {
                    Text("\(count)").foregroundStyle(.secondary).monospacedDigit()
                } else if let detail {
                    Text(detail).font(.subheadline).foregroundStyle(.secondary).lineLimit(1)
                }
            }
        }
    }
}

/// The GUI's list editor (Keywords / Authors / Low priority): add, rename
/// (tap), delete (swipe), reorder, search, reset to defaults.
struct TermListEditor: View {
    let page: ConfigPage
    let keyPath: WritableKeyPath<DigestConfig, [String]>
    let aspect: HighlightAspect
    let caption: String

    @Environment(AppModel.self) private var model
    @State private var newTerm = ""
    @State private var query = ""
    @State private var renaming: String?
    @State private var renameText = ""
    @State private var confirmReset = false
    @FocusState private var addFocused: Bool

    private var terms: [String] { model.config[keyPath: keyPath] }
    private var shown: [String] {
        let q = query.trimmingCharacters(in: .whitespaces).lowercased()
        return q.isEmpty ? terms : terms.filter { $0.lowercased().contains(q) }
    }

    var body: some View {
        List {
            Section {
                HStack {
                    TextField("Add \(page.title.lowercased())…", text: $newTerm)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .focused($addFocused)
                        .submitLabel(.done)
                        .onSubmit(add)
                    Button("Add", action: add)
                        .disabled(newTerm.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            } footer: {
                Text(caption)
            }

            Section {
                ForEach(shown, id: \.self) { term in
                    Button {
                        renameText = term
                        renaming = term
                    } label: {
                        HStack(spacing: 10) {
                            Circle().fill(Color(hex: model.config.color(for: aspect))).frame(width: 7, height: 7)
                            Text(term).foregroundStyle(.primary)
                            Spacer()
                        }
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityHint("Edit")
                }
                .onDelete { offsets in
                    let doomed = Set(offsets.map { shown[$0] })
                    model.config[keyPath: keyPath].removeAll { doomed.contains($0) }
                }
                .onMove(perform: query.isEmpty ? move : nil)
            } header: {
                Text("\(terms.count) entries")
            }

            Section {
                Button("Reset to defaults", role: .destructive) { confirmReset = true }
            }
        }
        .navigationTitle(page.title)
        .searchable(text: $query, placement: .navigationBarDrawer(displayMode: .automatic), prompt: "Filter")
        .toolbar { EditButton() }
        .alert("Edit entry", isPresented: Binding(get: { renaming != nil }, set: { if !$0 { renaming = nil } })) {
            TextField("Entry", text: $renameText)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
            Button("Save") { rename() }
            Button("Cancel", role: .cancel) { renaming = nil }
        }
        .confirmationDialog("Replace all \(page.title.lowercased()) with the built-in defaults?",
                            isPresented: $confirmReset, titleVisibility: .visible) {
            Button("Reset to defaults", role: .destructive) {
                Task {
                    if let d = await model.defaults() { model.config[keyPath: keyPath] = d[keyPath: keyPath] }
                }
            }
        }
    }

    private func add() {
        var list = model.config[keyPath: keyPath]
        if DigestConfig.append(newTerm, to: &list) {
            model.config[keyPath: keyPath] = list
            newTerm = ""
        } else if !newTerm.trimmingCharacters(in: .whitespaces).isEmpty {
            model.showToast("“\(newTerm.trimmingCharacters(in: .whitespaces))” is already in the list", kind: .info)
        }
        addFocused = true
    }

    private func move(from: IndexSet, to: Int) {
        model.config[keyPath: keyPath].move(fromOffsets: from, toOffset: to)
    }

    /// Rename in place; an emptied entry is dropped (the GUI drops empty rows).
    private func rename() {
        guard let old = renaming, let i = terms.firstIndex(of: old) else { return }
        let new = renameText.trimmingCharacters(in: .whitespacesAndNewlines)
        if new.isEmpty {
            model.config[keyPath: keyPath].remove(at: i)
        } else if new.caseInsensitiveCompare(old) == .orderedSame
                    || !terms.contains(where: { $0.caseInsensitiveCompare(new) == .orderedSame }) {
            model.config[keyPath: keyPath][i] = new
        } else {
            model.showToast("“\(new)” is already in the list", kind: .info)
        }
        renaming = nil
    }
}
