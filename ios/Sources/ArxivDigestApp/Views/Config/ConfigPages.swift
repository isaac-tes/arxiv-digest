import SwiftUI
import ArxivDigestCore

/// Feeds: the GUI's Feeds tab (name → listing URL) plus the sidebar's
/// subscribed-feeds multiselect and "Include replacement submissions".
struct FeedsEditor: View {
    @Environment(AppModel.self) private var model
    @State private var newName = ""
    @State private var newURL = ""
    @State private var editing: String?
    @State private var editURL = ""

    /// Common arXiv categories offered as suggestions.
    static let suggestions = [
        "cond-mat", "cond-mat.dis-nn", "cond-mat.mes-hall", "cond-mat.mtrl-sci", "cond-mat.other",
        "cond-mat.quant-gas", "cond-mat.soft", "cond-mat.stat-mech", "cond-mat.str-el",
        "cond-mat.supr-con", "quant-ph", "hep-th", "hep-lat", "math-ph", "nlin.CD",
        "physics.atom-ph", "physics.comp-ph", "physics.optics", "cs.LG",
    ]

    private var names: [String] { model.config.feeds.keys.sorted() }

    var body: some View {
        @Bindable var model = model
        List {
            Section {
                Toggle(isOn: $model.config.includeReplacements) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Include replacement submissions")
                        Text("arXiv's Today feed lists re-submitted papers under “Replacement submissions”. Hidden by default to avoid repeats. The past-week feed has none.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            } header: {
                Text("Fetch")
            }

            Section {
                if names.isEmpty {
                    Text("No feeds configured. Add one below.").foregroundStyle(.secondary)
                }
                ForEach(names, id: \.self) { name in
                    feedRow(name)
                        .swipeActions {
                            Button(role: .destructive) { model.config.removeFeed(name) } label: {
                                Label("Delete", systemImage: "trash")
                            }
                        }
                }
            } header: {
                Text("Feeds")
            } footer: {
                if model.config.defaultFeeds.isEmpty {
                    Text("⚠︎ Subscribe to at least one feed, or the digest will be empty.")
                        .foregroundStyle(.orange)
                } else {
                    Text("Toggle a feed to fetch it. Tap a feed to edit its listing URL; swipe to delete. Subject bonuses are under Scoring.")
                }
            }

            Section {
                TextField("Category, e.g. cond-mat.str-el", text: $newName)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                TextField("Listing URL (optional)", text: $newURL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)
                Button("Add and subscribe", action: add)
                    .disabled(newName.trimmingCharacters(in: .whitespaces).isEmpty)
                let unused = Self.suggestions.filter { model.config.feeds[$0] == nil }
                if !unused.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack {
                            ForEach(unused, id: \.self) { s in
                                Button(s) { newName = s }
                                    .buttonStyle(.bordered)
                                    .controlSize(.small)
                            }
                        }
                    }
                }
            } header: {
                Text("Add a feed")
            } footer: {
                Text("Without a URL the category's arXiv listing (https://arxiv.org/list/<category>/new) is used; the timeframe picks /new or the past week.")
            }
        }
        .navigationTitle("Feeds")
        .alert("Listing URL", isPresented: Binding(get: { editing != nil }, set: { if !$0 { editing = nil } })) {
            TextField("https://arxiv.org/list/…/new", text: $editURL)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
            Button("Save") {
                if let name = editing { model.config.setFeed(name: name, url: editURL) }
                editing = nil
            }
            Button("Cancel", role: .cancel) { editing = nil }
        } message: {
            Text(editing ?? "")
        }
    }

    private func feedRow(_ name: String) -> some View {
        HStack {
            Button {
                editURL = model.config.feeds[name] ?? ""
                editing = name
            } label: {
                VStack(alignment: .leading, spacing: 2) {
                    Text(name).foregroundStyle(.primary)
                    Text(model.config.feeds[name] ?? "")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
            }
            .buttonStyle(.plain)
            Spacer()
            Toggle("Subscribed", isOn: Binding(
                get: { model.config.isSubscribed(name) },
                set: { model.config.setSubscribed($0, feed: name) }))
                .labelsHidden()
        }
    }

    private func add() {
        let name = newName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return }
        model.config.setFeed(name: name, url: newURL)
        model.config.setSubscribed(true, feed: name)
        newName = ""
        newURL = ""
    }
}

/// Scoring: the GUI's Scoring tab (whole-word matching, weights, per-feed
/// subject bonuses).
struct ScoringEditor: View {
    @Environment(AppModel.self) private var model
    @State private var confirmReset = false

    var body: some View {
        @Bindable var model = model
        Form {
            Section {
                Toggle(isOn: $model.config.wordBoundaryMatching) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Whole-word matching")
                        Text("“mpo” won't score “temporal” and author “ma” won't score “Mao”. Off = legacy substring matching. Subjects are unaffected.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            Section {
                ForEach(ScoringWeight.allCases) { w in
                    Stepper(value: weightBinding(w), in: range(w), step: w == .longAbstractThreshold ? 50 : 1) {
                        VStack(alignment: .leading, spacing: 2) {
                            HStack {
                                Text(w.label.capitalized(with: nil))
                                Spacer()
                                Text("\(model.config.weight(w))").monospacedDigit().foregroundStyle(.secondary)
                            }
                            Text(w.help).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            } header: {
                Text("Weights")
            }

            Section {
                let names = model.config.feeds.keys.sorted()
                if names.isEmpty {
                    Text("No feeds configured. Add some under Feeds.").foregroundStyle(.secondary)
                }
                ForEach(names, id: \.self) { name in
                    Stepper(value: Binding(
                        get: { model.config.feedWeight(name) },
                        set: { model.config.setFeedWeight($0, for: name) }), in: -20...20) {
                        HStack {
                            Text(name)
                            Spacer()
                            Text(signed(model.config.feedWeight(name)))
                                .monospacedDigit()
                                .foregroundStyle(model.config.feedWeight(name) == 0 ? Color.secondary : Color(hex: model.config.color(for: .subject)))
                        }
                    }
                }
            } header: {
                Text("Per-feed subject bonuses")
            } footer: {
                Text("Each feed scores this bonus when its name appears in a paper's subjects; 0 disables it. A parent feed like cond-mat also matches its sub-categories.")
            }

            Section {
                Button("Reset to defaults", role: .destructive) { confirmReset = true }
            }
        }
        .navigationTitle("Scoring")
        .confirmationDialog("Reset weights and subject bonuses to the built-in defaults?",
                            isPresented: $confirmReset, titleVisibility: .visible) {
            Button("Reset to defaults", role: .destructive) {
                Task {
                    guard let d = await model.defaults() else { return }
                    for w in ScoringWeight.allCases { model.config.setWeight(d.weight(w), for: w) }
                    model.config.feedWeights = d.feedWeights
                    model.config.wordBoundaryMatching = d.wordBoundaryMatching
                }
            }
        }
    }

    private func weightBinding(_ w: ScoringWeight) -> Binding<Int> {
        Binding(get: { model.config.weight(w) }, set: { model.config.setWeight($0, for: w) })
    }

    private func range(_ w: ScoringWeight) -> ClosedRange<Int> {
        switch w {
        case .longAbstractThreshold: return 0...5000
        case .lowPriorityPenalty: return -100...0
        default: return -100...100
        }
    }

    private func signed(_ n: Int) -> String { n > 0 ? "+\(n)" : "\(n)" }
}

/// Starter presets: the GUI's Profiles tab presets. Load replaces the working
/// config, Add merges; both stay unsaved until Save.
struct PresetsView: View {
    @Environment(AppModel.self) private var model
    @State private var confirmLoad: PresetInfo?

    var body: some View {
        List {
            Section {
                ForEach(model.presets) { preset in
                    VStack(alignment: .leading, spacing: 10) {
                        Text(preset.displayName).font(.headline)
                        Text(preset.description).font(.subheadline).foregroundStyle(.secondary)
                        HStack {
                            Button("Load") { confirmLoad = preset }
                                .buttonStyle(.bordered)
                            Button("Add") { Task { await model.addPreset(preset) } }
                                .buttonStyle(.borderedProminent)
                        }
                        .controlSize(.small)
                    }
                    .padding(.vertical, 6)
                }
                if model.presets.isEmpty {
                    Text("No presets from the server.").foregroundStyle(.secondary)
                }
            } footer: {
                Text("Built-in topic bundles (keywords, authors, feeds). Load replaces your working config; Add merges the preset in. Nothing is stored until you tap Save.")
            }
        }
        .navigationTitle("Starter presets")
        .confirmationDialog(
            "Replace your working config with “\(confirmLoad?.displayName ?? "")”?",
            isPresented: Binding(get: { confirmLoad != nil }, set: { if !$0 { confirmLoad = nil } }),
            titleVisibility: .visible
        ) {
            Button("Load preset", role: .destructive) {
                if let p = confirmLoad { Task { await model.loadPreset(p) } }
                confirmLoad = nil
            }
        } message: {
            Text("Keywords, authors and feeds are replaced; other settings return to defaults. You can still Discard before saving.")
        }
    }
}
