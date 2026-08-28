import SwiftUI
import ArxivDigestCore

/// Settings: config editors (keywords/authors/low-priority/scoring) + presets.
struct SettingsView: View {
    @Environment(AppModel.self) private var model
    @AppStorage("appearanceMode") private var appearanceRaw = AppearanceMode.system.rawValue
    @State private var serverURLText = ""

    var body: some View {
        @Bindable var model = model
        NavigationStack {
            Form {
                Section("Appearance") {
                    Picker("Theme", selection: $appearanceRaw) {
                        ForEach(AppearanceMode.allCases) { mode in
                            Text(mode.label).tag(mode.rawValue)
                        }
                    }
                    .pickerStyle(.segmented)
                }
                Section {
                    Toggle("Highlight keywords in titles", isOn: $model.config.highlightTermsTitle)
                    Toggle("Highlight keywords in abstracts", isOn: $model.config.highlightTermsAbstract)
                    Toggle("Highlight authors", isOn: $model.config.highlightAuthors)
                    aspectColorRow("Keywords", aspect: .keyword)
                    aspectColorRow("Low priority", aspect: .lowPriority)
                    aspectColorRow("Authors", aspect: .author)
                    ColorPicker("Subjects color", selection: subjectColorBinding, supportsOpacity: false)
                    Toggle("Subjects: color font not background", isOn: $model.config.colorFontSubject)
                } header: {
                    Text("Display")
                } footer: {
                    Text("Per-aspect highlight colors for the Papers list. \"Color font\" tints the text instead of drawing a background. Tap Save config to persist.")
                }
                Section {
                    TextField("http://127.0.0.1:8000", text: $serverURLText)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                    Button("Connect") {
                        guard let url = URL(string: serverURLText.trimmingCharacters(in: .whitespaces)) else { return }
                        Task { await model.updateBaseURL(url) }
                    }
                } header: {
                    Text("Server")
                } footer: {
                    Text("On a physical device use your Mac's LAN IP (e.g. http://192.168.1.20:8000), not 127.0.0.1.")
                }
                Section("Keywords") {
                    TagEditor(title: "Core keywords", tags: $model.config.coreKeywords)
                }
                Section("Authors") {
                    TagEditor(title: "Named authors", tags: $model.config.namedAuthors)
                }
                Section("Low priority") {
                    TagEditor(title: "Low-priority terms", tags: $model.config.lowPriorityKeywords)
                }
                Section("Scoring") {
                    Stepper(value: $model.config.topN, in: 1...100) {
                        Text("Top N: \(model.config.topN)")
                    }
                    Picker("Timeframe", selection: $model.config.timeframe) {
                        Text("Today").tag("today")
                        Text("Past week").tag("pastweek")
                    }
                }
                Section("Starter presets") {
                    ForEach(model.presets, id: \.self) { name in
                        Button(name) {
                            // Merge preset into the current config.
                            Task { await mergePreset(name) }
                        }
                    }
                }
                Section {
                    Button("Save config") {
                        Task { await model.saveConfig() }
                    }
                }
            }
            .navigationTitle("Settings")
            .onAppear {
                if serverURLText.isEmpty { serverURLText = model.baseURL.absoluteString }
            }
            .task {
                await model.loadConfig()
                await model.loadPresets()
            }
        }
    }

    /// A ColorPicker + "color font" toggle for one highlight aspect, bound to
    /// the config's per-aspect color/font settings.
    @ViewBuilder
    private func aspectColorRow(_ label: String, aspect: HighlightAspect) -> some View {
        ColorPicker(
            "\(label) color",
            selection: Binding(
                get: { Color(hex: model.config.color(for: aspect)) },
                set: { model.config.setColor($0.hexString, for: aspect) }
            ),
            supportsOpacity: false
        )
        Toggle(
            "\(label): color font not background",
            isOn: Binding(
                get: { model.config.fontColor(for: aspect) },
                set: { model.config.setFontColor($0, for: aspect) }
            )
        )
    }

    private var subjectColorBinding: Binding<Color> {
        Binding(
            get: { Color(hex: model.config.colorSubject) },
            set: { model.config.colorSubject = $0.hexString }
        )
    }

    private func mergePreset(_ name: String) async {
        await model.mergePreset(named: name)
    }
}

/// A simple tag editor: add terms, remove with a swipe or button.
struct TagEditor: View {
    let title: String
    @Binding var tags: [String]
    @State private var newTag = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                TextField("Add \(title.lowercased())…", text: $newTag)
                Button("Add") {
                    let t = newTag.trimmingCharacters(in: .whitespaces)
                    guard !t.isEmpty, !tags.contains(t) else { return }
                    tags.append(t)
                    newTag = ""
                }
            }
            FlowLayout(spacing: 8) {
                ForEach(tags, id: \.self) { tag in
                    HStack(spacing: 4) {
                        Text(tag)
                        Button {
                            tags.removeAll { $0 == tag }
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .font(.caption)
                        }
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Capsule().fill(Color.gray.opacity(0.2)))
                }
            }
        }
    }
}

/// A simple flow layout that wraps tags onto multiple lines.
struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let maxWidth = proposal.width ?? .infinity
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > maxWidth, x > 0 {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        return CGSize(width: maxWidth, height: y + rowHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX
        var y = bounds.minY
        var rowHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > bounds.maxX, x > bounds.minX {
                x = bounds.minX
                y += rowHeight + spacing
                rowHeight = 0
            }
            subview.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
    }
}
