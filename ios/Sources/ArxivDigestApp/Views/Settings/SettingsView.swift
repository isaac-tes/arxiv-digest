import SwiftUI
import ArxivDigestCore

/// Settings: connection (server or demo), appearance, and the GUI sidebar's
/// Display section (highlight toggles, per-aspect colors and font tints).
/// Display options are config fields, saved with the same save bar.
struct SettingsView: View {
    @Environment(AppModel.self) private var model
    @AppStorage("appearanceMode") private var appearanceRaw = AppearanceMode.system.rawValue
    @State private var serverURLText = ""
    @State private var modeChoice: AppModel.Mode = .server
    @State private var isConnecting = false

    var body: some View {
        @Bindable var model = model
        NavigationStack {
            Form {
                connectionSection

                Section("Appearance") {
                    Picker("Theme", selection: $appearanceRaw) {
                        ForEach(AppearanceMode.allCases) { Text($0.label).tag($0.rawValue) }
                    }
                    .pickerStyle(.segmented)
                }

                Section {
                    Toggle("Highlight authors", isOn: $model.config.highlightAuthors)
                    Toggle("Highlight keywords in titles", isOn: $model.config.highlightTermsTitle)
                    Toggle("Highlight keywords in abstracts", isOn: $model.config.highlightTermsAbstract)
                    Toggle("Highlight keywords in summaries", isOn: $model.config.highlightTermsSummary)
                } header: {
                    Text("Display")
                } footer: {
                    Text("Summaries are the two-sentence previews on each paper card; off by default, as in the web GUI.")
                }

                Section {
                    ForEach(HighlightAspect.allCases) { aspect in
                        aspectRow(aspect)
                    }
                    preview
                } header: {
                    Text("Highlight colors")
                } footer: {
                    Text("“Tint font” also colors the matched text, not just its background. Colors and toggles are saved with your config, shared with the web GUI's profile format.")
                }

                Section("Zotero") {
                    switch model.zoteroAvailability {
                    case .web:
                        Label("Saving via the server's Zotero Web API key", systemImage: "checkmark.seal.fill")
                            .foregroundStyle(.green)
                    case .unavailable:
                        VStack(alignment: .leading, spacing: 4) {
                            Label("No Zotero key on the server", systemImage: "books.vertical")
                            Text("Use Share to Zotero: it opens the share sheet, where the Zotero app saves the paper. To save directly, set ZOTERO_API_KEY and ZOTERO_LIBRARY_ID on the server.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                Section("About") {
                    LabeledContent("Version", value: Self.version)
                    Link(destination: URL(string: "https://github.com/isaac-tes/arxiv-digest")!) {
                        Label("Source on GitHub", systemImage: "chevron.left.forwardslash.chevron.right")
                    }
                }
            }
            .navigationTitle("Settings")
            .safeAreaInset(edge: .bottom) { if model.isDirty { SaveBar() } }
            .animation(.default, value: model.isDirty)
            .onAppear {
                if serverURLText.isEmpty { serverURLText = model.baseURL.absoluteString }
                modeChoice = model.mode
            }
            .task { if model.connectionStatus == nil { await model.checkConnection() } }
        }
    }

    private var connectionSection: some View {
        Section {
            Picker("Source", selection: $modeChoice) {
                Text("Digest server").tag(AppModel.Mode.server)
                Text("Demo").tag(AppModel.Mode.demo)
            }
            .pickerStyle(.segmented)

            if modeChoice == .server {
                TextField("http://192.168.1.20:8000", text: $serverURLText)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)
            }

            Button {
                connect()
            } label: {
                HStack {
                    Text(modeChoice == model.mode && modeChoice == .demo ? "Reload demo" : "Connect")
                    if isConnecting { Spacer(); ProgressView() }
                }
            }
            .disabled(isConnecting || (modeChoice == .server && normalizedURL == nil))

            if let status = model.connectionStatus {
                Label(status, systemImage: status.hasPrefix("Connected") ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                    .font(.footnote)
                    .foregroundStyle(status.hasPrefix("Connected") ? .green : .orange)
            }
        } header: {
            Text("Connection")
        } footer: {
            if modeChoice == .server {
                Text("Run the server with `uv run uvicorn app.main:app --host 0.0.0.0` and enter your computer's LAN address. On a physical device, 127.0.0.1 is the phone itself.")
            } else {
                Text("Demo mode uses built-in sample papers with invented authors; nothing leaves the device. Scores were computed by the real engine, but they don't change when you edit the config.")
            }
        }
    }

    /// The typed URL, with `http://` added when no scheme was given.
    private var normalizedURL: URL? {
        let t = serverURLText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty else { return nil }
        let withScheme = t.contains("://") ? t : "http://" + t
        guard let url = URL(string: withScheme), url.host != nil else { return nil }
        return url
    }

    private func connect() {
        let url = modeChoice == .server ? (normalizedURL ?? model.baseURL) : model.baseURL
        if modeChoice == .server { serverURLText = url.absoluteString }
        isConnecting = true
        Task {
            if modeChoice == .demo { DemoBackend.shared.reset() }
            await model.connect(mode: modeChoice, url: url)
            isConnecting = false
        }
    }

    private func aspectRow(_ aspect: HighlightAspect) -> some View {
        HStack {
            ColorPicker(aspect.label, selection: Binding(
                get: { Color(hex: model.config.color(for: aspect)) },
                set: { model.config.setColor($0.hexString, for: aspect) }), supportsOpacity: false)
            Toggle("Tint font", isOn: Binding(
                get: { model.config.fontColor(for: aspect) },
                set: { model.config.setFontColor($0, for: aspect) }))
                .toggleStyle(.button)
                .controlSize(.small)
        }
    }

    /// A live sample of every aspect in the current colors.
    private var preview: some View {
        let cfg = model.config
        let text = "Floquet anyons, by Ada Lovelace · photonic · quant-ph"
        var spans: [HighlightSpan] = []
        func add(_ needle: String, _ aspect: HighlightAspect) {
            if let r = text.range(of: needle) { spans.append(HighlightSpan(range: r, aspect: aspect)) }
        }
        add("Floquet anyons", .keyword)
        add("Ada Lovelace", .author)
        add("photonic", .lowPriority)
        add("quant-ph", .subject)
        return Text(Highlight.attributed(text, spans: spans, config: cfg))
            .font(.callout)
            .padding(.vertical, 4)
    }

    static var version: String {
        let info = Bundle.main.infoDictionary
        let v = info?["CFBundleShortVersionString"] as? String ?? "?"
        let b = info?["CFBundleVersion"] as? String ?? "?"
        return "\(v) (\(b))"
    }
}
