import Foundation
import Observation
import ArxivDigestCore

/// Root observable state for the app.
///
/// Holds the API client, the current digest, config, and saved lists. Uses
/// `@Observable` (iOS 17+). The backend is the source of truth; this model is
/// the in-memory cache the views render.
@Observable
@MainActor
final class AppModel {
    // The backend base URL. Local mode defaults to the Mac's LAN address so a
    // device on the same Wi-Fi can reach the FastAPI server.
    var baseURL: URL
    var client: APIClient

    var digest: Digest?
    var config: DigestConfig = DigestConfig()
    var presets: [String] = []

    var isLoading = false
    var errorMessage: String?
    /// Transient success note (e.g. "Saved ✓"), shown then cleared by views.
    var statusMessage: String?

    /// UserDefaults key for the persisted backend URL (editable in Settings so
    /// the app can point at a Mac's LAN IP when running on a physical device).
    static let baseURLDefaultsKey = "serverBaseURL"
    static let defaultBaseURL = "http://127.0.0.1:8000"

    init(baseURL: URL? = nil) {
        let stored = UserDefaults.standard.string(forKey: Self.baseURLDefaultsKey)
        let resolved = baseURL
            ?? stored.flatMap(URL.init(string:))
            ?? URL(string: Self.defaultBaseURL)!
        self.baseURL = resolved
        self.client = APIClient(baseURL: resolved)
    }

    /// Point the app at a different backend (e.g. `http://192.168.1.20:8000` for
    /// a physical device), persist it, and reload everything.
    func updateBaseURL(_ url: URL) async {
        baseURL = url
        client = APIClient(baseURL: url)
        UserDefaults.standard.set(url.absoluteString, forKey: Self.baseURLDefaultsKey)
        await loadConfig()
        await loadPresets()
        await loadDigest()
    }

    // MARK: - Digest

    /// Fetch using the current config's timeframe + top_n. The server resolves
    /// feeds from the saved config, so changing feeds/timeframe requires a
    /// `refresh` to bypass the 1h cache (see saveConfig).
    func loadDigest(refresh: Bool = false) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            digest = try await client.fetchDigest(
                timeframe: config.timeframe, topN: config.topN, refresh: refresh
            )
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Config

    func loadConfig() async {
        do {
            config = try await client.getConfig()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    /// Persist the config, then re-fetch the digest so new keywords / feeds /
    /// timeframe are reflected in the rankings (refresh bypasses the 1h cache,
    /// which is keyed on the request feeds, not the saved config).
    func saveConfig() async {
        do {
            config = try await client.putConfig(config)
            statusMessage = "Saved ✓"
            await loadDigest(refresh: true)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func loadPresets() async {
        do {
            presets = try await client.listPresets()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func mergePreset(named name: String) async {
        do {
            config = try await client.mergePreset(named: name)
            statusMessage = "Merged '\(name)'"
            await loadDigest(refresh: true)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Zotero

    /// Whether the server can save to Zotero (Web API key present). Refreshed by
    /// `refreshZoteroAvailability`; drives whether the detail view offers the action.
    var zoteroAvailability: ZoteroSaveAvailability = .unavailable

    func refreshZoteroAvailability() async {
        let status = (try? await client.zoteroStatus()) ?? [:]
        zoteroAvailability = ZoteroPolicy.availability(from: status)
    }

    /// Save a paper to Zotero via the Web API. Only meaningful when
    /// `zoteroAvailability == .web`; otherwise the server has no key and the
    /// only alternative (a `zotero://select` deep-link) cannot create an item,
    /// so we surface guidance instead of firing a link that saves nothing.
    @discardableResult
    func saveToZotero(arxivId: String) async -> ZoteroSaveResult? {
        await refreshZoteroAvailability()
        guard zoteroAvailability == .web else {
            errorMessage = "Zotero saving isn't configured. Set ZOTERO_API_KEY and ZOTERO_LIBRARY_ID on the server."
            return nil
        }
        do {
            let result = try await client.saveToZotero(arxivId: arxivId, mode: .web)
            statusMessage = result.message
            return result
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    // MARK: - Score a paper

    /// Score a single paper by arXiv id/URL. Returns the result (paper +
    /// breakdown + optional absence reason), or nil on failure (with
    /// `errorMessage` set). Used by the Score tab and the paper detail view.
    func requestScore(arxivId: String) async -> ScoreResult? {
        errorMessage = nil
        do {
            return try await client.score(arxivId: arxivId)
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }
}
