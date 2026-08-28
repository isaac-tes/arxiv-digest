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

    func loadDigest(timeframe: String = "pastweek", topN: Int? = nil, refresh: Bool = false) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            digest = try await client.fetchDigest(timeframe: timeframe, topN: topN, refresh: refresh)
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

    func saveConfig() async {
        do {
            config = try await client.putConfig(config)
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
        } catch {
            errorMessage = error.localizedDescription
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
