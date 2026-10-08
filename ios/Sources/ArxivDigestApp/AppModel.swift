import Foundation
import Observation
import ArxivDigestCore

/// A short, auto-dismissing message, optionally with one action (e.g. Undo).
struct Toast: Identifiable, Equatable {
    enum Kind { case success, info, error }

    let id = UUID()
    var message: String
    var kind: Kind = .success
    var actionTitle: String?
    var action: (@MainActor () -> Void)?

    static func == (a: Toast, b: Toast) -> Bool { a.id == b.id }
}

/// Root observable state for the app (iOS 17 `@Observable`).
///
/// The digest service is the source of truth (ADR 0002/0008). `config` is the
/// working copy the Config and Settings tabs edit; `savedConfig` is what the
/// server has. They differ until the user saves (the GUI's "in-memory until
/// Save" behaviour), which drives the unsaved-changes bar.
@Observable
@MainActor
final class AppModel {
    // MARK: Connection

    enum Mode: String { case server, demo, standalone }

    static let baseURLDefaultsKey = "serverBaseURL"
    static let modeDefaultsKey = "connectionMode"
    static let defaultBaseURL = "http://127.0.0.1:8000"

    private(set) var mode: Mode
    private(set) var baseURL: URL
    private(set) var client: APIClient
    /// "Connected · local" / an error, from the last health check.
    var connectionStatus: String?

    // MARK: Digest

    var digest: Digest?
    /// The picked announcement day (nil = all days). View state, like the GUI.
    var selectedDay: String?
    var isLoading = false
    /// The last digest load failure (shown on the Papers tab).
    var digestError: String?
    private var loadGeneration = 0

    // MARK: Config

    var config = DigestConfig()
    private(set) var savedConfig = DigestConfig()
    private(set) var hasLoadedConfig = false
    /// Why the config could not be loaded (shown on Config / Settings).
    var configError: String?
    var presets: [PresetInfo] = []
    var isSaving = false

    var isDirty: Bool { hasLoadedConfig && config != savedConfig }

    // MARK: Zotero / feedback

    var zoteroAvailability: ZoteroSaveAvailability = .unavailable
    var toast: Toast?
    private var toastTask: Task<Void, Never>?

    init(launch: LaunchOptions = .current) {
        let defaults = UserDefaults.standard
        let storedMode = Mode(rawValue: defaults.string(forKey: Self.modeDefaultsKey) ?? "") ?? .standalone  // works with no server; a stored choice wins
        let mode: Mode = launch.standalone ? .standalone : launch.demo ? .demo : storedMode
        let url = defaults.string(forKey: Self.baseURLDefaultsKey).flatMap(URL.init(string:))
            ?? URL(string: Self.defaultBaseURL)!
        self.mode = mode
        self.baseURL = url
        self.client = Self.makeClient(mode: mode, url: url)
    }

    private static func makeClient(mode: Mode, url: URL) -> APIClient {
        switch mode {
        case .server: return APIClient(baseURL: url)
        case .demo: return APIClient(baseURL: DemoURLProtocol.baseURL, session: DemoURLProtocol.makeSession())
        case .standalone: return APIClient(baseURL: LocalURLProtocol.baseURL, session: LocalURLProtocol.makeSession())
        }
    }

    // MARK: - Lifecycle

    /// Load everything for the current connection.
    func bootstrap() async {
        await loadConfig()
        async let presetsLoad: Void = loadPresets()
        async let zotero: Void = refreshZoteroAvailability()
        await loadDigest()
        _ = await (presetsLoad, zotero)
    }

    /// Switch between a real server and demo mode and/or change the URL.
    func connect(mode: Mode, url: URL) async {
        self.mode = mode
        self.baseURL = url
        UserDefaults.standard.set(url.absoluteString, forKey: Self.baseURLDefaultsKey)
        UserDefaults.standard.set(mode.rawValue, forKey: Self.modeDefaultsKey)
        client = Self.makeClient(mode: mode, url: url)
        digest = nil
        digestError = nil
        configError = nil
        selectedDay = nil
        hasLoadedConfig = false
        config = DigestConfig()
        savedConfig = DigestConfig()
        presets = []
        zoteroAvailability = .unavailable
        await checkConnection()
        await bootstrap()
    }

    func checkConnection() async {
        do {
            let h = try await client.health()
            connectionStatus = "Connected · \(h["mode"] ?? "ok") mode"
        } catch {
            connectionStatus = error.localizedDescription
        }
    }

    // MARK: - Digest

    /// Fetch the digest view for the *saved* timeframe / top N (the ranking
    /// reflects saved config only) and the picked day. Before the config has
    /// loaded, the server's own config decides. `refresh` bypasses the
    /// server's 1 h fetch cache (a new arXiv fetch). Overlapping calls are
    /// safe: only the newest response is applied.
    func loadDigest(refresh: Bool = false) async {
        loadGeneration += 1
        let generation = loadGeneration
        isLoading = true
        defer { if generation == loadGeneration { isLoading = false } }
        do {
            let result = try await client.fetchDigest(
                timeframe: hasLoadedConfig ? savedConfig.timeframe : nil,
                topN: hasLoadedConfig ? savedConfig.topN : nil,
                day: selectedDay, refresh: refresh)
            guard generation == loadGeneration else { return }
            digest = result
            digestError = nil
            // The server drops a day that left the fetch; follow it.
            if selectedDay != result.day { selectedDay = result.day }
        } catch {
            guard generation == loadGeneration else { return }
            digestError = error.localizedDescription
        }
    }

    func selectDay(_ day: String?) async {
        guard day != selectedDay else { return }
        selectedDay = day
        await loadDigest()
    }

    /// The Papers toolbar's timeframe / top N. Persisted right away (PATCH,
    /// only these fields) so other unsaved edits stay unsaved.
    func setFetchOptions(timeframe: String? = nil, topN: Int? = nil) async {
        var fields: [String: JSONValue] = [:]
        if let timeframe, timeframe != savedConfig.timeframe { fields["timeframe"] = .string(timeframe) }
        if let topN, topN != savedConfig.topN { fields["top_n"] = .int(topN) }
        guard !fields.isEmpty else { return }
        do {
            let stored = try await client.patchConfig(fields)
            savedConfig = stored
            config.timeframe = stored.timeframe
            config.topN = stored.topN
            if timeframe != nil { selectedDay = nil }
            await loadDigest()
        } catch {
            showToast(error.localizedDescription, kind: .error)
        }
    }

    // MARK: - Removed papers

    /// Hide a paper (the GUI's ✕). The row disappears at once; the reload
    /// moves the next paper up into the freed slot. Offers Undo.
    func remove(_ paper: Paper) async {
        if let d = digest {
            digest = Digest(
                papers: d.papers.filter { $0.id != paper.id }, totalPapers: d.totalPapers - 1,
                requestedTop: d.requestedTop, fetchedPapers: d.fetchedPapers,
                hiddenByFilters: d.hiddenByFilters, removed: d.removed + [paper],
                availableDays: d.availableDays, day: d.day, timeframe: d.timeframe,
                feeds: d.feeds, notices: d.notices, fetchedAt: d.fetchedAt)
        }
        do {
            try await client.removePaper(arxivId: paper.id)
            showToast("Removed “\(paper.title)”", kind: .info, actionTitle: "Undo") { [weak self] in
                Task { await self?.restore([paper.id], announce: false) }
            }
        } catch {
            showToast(error.localizedDescription, kind: .error)
        }
        await loadDigest()
    }

    func restore(_ ids: [String], announce: Bool = true) async {
        guard !ids.isEmpty else { return }
        do {
            try await client.restorePapers(arxivIds: ids)
            if announce { showToast(ids.count == 1 ? "Restored 1 paper" : "Restored \(ids.count) papers") }
        } catch {
            showToast(error.localizedDescription, kind: .error)
        }
        await loadDigest()
    }

    // MARK: - Config

    func loadConfig() async {
        do {
            let c = try await client.getConfig()
            config = c
            savedConfig = c
            hasLoadedConfig = true
            configError = nil
        } catch {
            configError = error.localizedDescription
        }
    }

    /// Persist the working config, confirm, and re-rank. Keywords/weights only
    /// re-rank the cached fetch; changed feeds fetch those feeds.
    func saveConfig() async {
        // The engine treats an empty subscription as "use the built-in feeds";
        // the GUI disables Fetch instead. Refuse rather than surprise.
        guard !config.defaultFeeds.isEmpty else {
            showToast("Subscribe to at least one feed before saving (Config → Feeds).", kind: .error)
            return
        }
        isSaving = true
        defer { isSaving = false }
        do {
            let stored = try await client.putConfig(config)
            savedConfig = stored
            config = stored
            showToast("Saved ✓")
            await loadDigest()
        } catch {
            showToast("Couldn't save: \(error.localizedDescription)", kind: .error)
        }
    }

    func discardChanges() {
        config = savedConfig
    }

    /// The engine's defaults, for per-page "Reset to defaults".
    func defaults() async -> DigestConfig? {
        do {
            return try await client.defaultConfig()
        } catch {
            showToast(error.localizedDescription, kind: .error)
            return nil
        }
    }

    func loadPresets() async {
        presets = (try? await client.presetInfo()) ?? []
    }

    /// GUI "Load preset": replace the working config (unsaved until Save).
    func loadPreset(_ preset: PresetInfo) async {
        do {
            config = try await client.loadPreset(named: preset.name, save: false)
            showToast("Loaded “\(preset.displayName)”. Save to apply.", kind: .info)
        } catch {
            showToast(error.localizedDescription, kind: .error)
        }
    }

    /// GUI "Add preset": merge into the working config (unsaved until Save).
    func addPreset(_ preset: PresetInfo) async {
        do {
            config = try await client.mergePreset(named: preset.name, into: config, save: false)
            showToast("Added “\(preset.displayName)”. Save to apply.", kind: .info)
        } catch {
            showToast(error.localizedDescription, kind: .error)
        }
    }

    // MARK: - Score a paper

    /// Score against the same view the Papers tab shows (ADR 0008).
    func score(_ input: String) async -> Result<ScoreResult, Error> {
        do {
            // Before the config loads, let the server use its own (as loadDigest does).
            return .success(try await client.score(
                arxivId: input,
                timeframe: hasLoadedConfig ? savedConfig.timeframe : nil,
                topN: hasLoadedConfig ? savedConfig.topN : nil,
                day: selectedDay))
        } catch {
            return .failure(error)
        }
    }

    // MARK: - Zotero

    func refreshZoteroAvailability() async {
        let status = (try? await client.zoteroStatus()) ?? [:]
        zoteroAvailability = ZoteroPolicy.availability(from: status)
    }

    /// Save via the server's Zotero Web API key. Returns true on success.
    @discardableResult
    func saveToZotero(_ arxivId: String) async -> Bool {
        do {
            let result = try await client.saveToZotero(arxivId: arxivId)
            showToast(result.message)
            return true
        } catch {
            showToast(error.localizedDescription, kind: .error)
            return false
        }
    }

    /// Adds to the working config only; Save persists it.
    func addNamedAuthor(_ name: String) {
        guard DigestConfig.append(name, to: &config.namedAuthors) else { return }
        showToast("Added \(name) to highlighted authors - Save to apply")
    }

    // MARK: - Toast

    func showToast(
        _ message: String, kind: Toast.Kind = .success,
        actionTitle: String? = nil, action: (@MainActor () -> Void)? = nil
    ) {
        toastTask?.cancel()
        let t = Toast(message: message, kind: kind, actionTitle: actionTitle, action: action)
        toast = t
        let seconds: Double = action == nil ? 2.2 : 4.5
        toastTask = Task { [weak self] in
            try? await Task.sleep(for: .seconds(seconds))
            guard !Task.isCancelled, self?.toast?.id == t.id else { return }
            self?.toast = nil
        }
    }
}
