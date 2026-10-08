import XCTest
@testable import ArxivDigestCore
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

/// Config hydration and preset merging, pinned to `Config.from_json` /
/// `merge_preset` by `ConfigParityFixture`.
final class EngineConfigParityTests: XCTestCase {
    struct Fixture: Decodable {
        struct Hydrate: Decodable { let input: [String: JSONValue]; let expected: [String: JSONValue] }
        struct Merge: Decodable { let base: [String: JSONValue]; let preset: String; let expected: [String: JSONValue] }
        let hydrate: [Hydrate]
        let invalid: [[String: JSONValue]]
        let merge: [Merge]
    }

    let fixture = try! JSONDecoder().decode(Fixture.self, from: Data(ConfigParityFixture.json.utf8))

    func testHydrateMatchesEngine() throws {
        XCTAssertEqual(fixture.hydrate.count, 7)
        for (i, c) in fixture.hydrate.enumerated() {
            let got = try EngineConfig.hydrate(c.input)
            for key in Set(got.keys).union(c.expected.keys) {
                XCTAssertEqual(got[key], c.expected[key], "case \(i) key \(key)")
            }
        }
    }

    func testInvalidConfigsThrow() {
        for blob in fixture.invalid {
            XCTAssertThrowsError(try EngineConfig.hydrate(blob), "\(blob)")
        }
    }

    func testMissingListGetsDefaultsButEmptyListStaysEmpty() throws {
        let defaults = EngineConfig.defaults
        XCTAssertEqual(try EngineConfig.hydrate([:]), defaults)
        XCTAssertEqual(try EngineConfig.hydrate(["named_authors": .null])["named_authors"], defaults["named_authors"])
        XCTAssertEqual(try EngineConfig.hydrate(["named_authors": .array([])])["named_authors"], .array([]))
    }

    func testMergeMatchesEngine() {
        XCTAssertEqual(fixture.merge.count, 3)
        for c in fixture.merge {
            let got = EngineConfig.merge(c.base, preset: EngineConfig.presets[c.preset]!.config)
            XCTAssertEqual(got, c.expected, c.preset)
        }
    }
}

/// Standalone persistence: config, removed papers and the fetch cache survive
/// a relaunch (a new router/source over the same directory).
final class StandaloneStoreTests: XCTestCase {
    private var dir: URL!

    override func setUp() {
        super.setUp()
        dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    }

    override func tearDown() {
        try? FileManager.default.removeItem(at: dir)
        super.tearDown()
    }

    private func client(fetcher: @escaping LiveSource.Fetcher = { _, _, _ in .init(papers: StandaloneTests.papers) }) -> APIClient {
        StandaloneBackend.shared.install(StandaloneBackend.makeRouter(store: LocalStore(directory: dir), fetcher: fetcher))
        return APIClient(baseURL: LocalURLProtocol.baseURL, session: LocalURLProtocol.makeSession())
    }

    func testFirstRunStartsFromEngineDefaultsAndPresets() async throws {
        let api = client()
        let cfg = try await api.getConfig()
        XCTAssertEqual(cfg.data, EngineConfig.defaults)
        let defaults = try await api.defaultConfig()
        XCTAssertEqual(defaults.data, EngineConfig.defaults)
        let info = try await api.presetInfo()
        XCTAssertEqual(info.map(\.name), EngineConfig.presets.keys.sorted())
        let loaded = try await api.loadPreset(named: info[0].name, save: false)
        XCTAssertEqual(loaded.data, EngineConfig.presets[info[0].name]!.config)
        let unchanged = try await api.getConfig()
        XCTAssertEqual(unchanged.data, EngineConfig.defaults)
    }

    /// Every Display toggle (incl. "Highlight keywords in summaries") survives
    /// Save and a relaunch.
    func testDisplayTogglesPersistAcrossLaunches() async throws {
        var api = client()
        var cfg = try await api.getConfig()
        XCTAssertFalse(cfg.highlightTermsSummary)
        cfg.highlightTermsSummary = true
        cfg.highlightAuthors = false
        let saved = try await api.putConfig(cfg)
        XCTAssertTrue(saved.highlightTermsSummary)

        api = client()
        let reloaded = try await api.getConfig()
        XCTAssertTrue(reloaded.highlightTermsSummary)
        XCTAssertFalse(reloaded.highlightAuthors)
    }

    func testConfigAndRemovalsPersistAcrossLaunches() async throws {
        var api = client()
        var cfg = try await api.getConfig()
        cfg.coreKeywords = []
        cfg.namedAuthors = ["okafor"]
        let saved = try await api.putConfig(cfg)
        XCTAssertEqual(saved.coreKeywords, [])  // explicitly empty stays empty
        _ = try await api.fetchDigest()
        try await api.removePaper(arxivId: "2610.00001")

        api = client(fetcher: { _, _, _ in throw URLError(.notConnectedToInternet) })
        let reloaded = try await api.getConfig()
        XCTAssertEqual(reloaded.coreKeywords, [])
        XCTAssertEqual(reloaded.namedAuthors, ["okafor"])
        let removed = try await api.removedPapers()
        XCTAssertEqual(removed, ["2610.00001"])
        // The fetch cache survived too, so no network is needed within the hour.
        let digest = try await api.fetchDigest()
        XCTAssertEqual(digest.removed.map(\.id), ["2610.00001"])
    }

    func testPutHydratesAndRejectsInvalid() async throws {
        let api = client()
        let partial = try await api.putConfig(DigestConfig(data: ["named_authors": .array([.string("okafor")])]))
        XCTAssertEqual(partial.topN, 20)
        XCTAssertEqual(partial.coreKeywords, DigestConfig(data: EngineConfig.defaults).coreKeywords)
        do {
            _ = try await api.putConfig(DigestConfig(data: ["top_n": .string("abc")]))
            XCTFail("expected 422")
        } catch {
            guard case .http(422, let detail)? = error as? APIError else { return XCTFail("\(error)") }
            XCTAssertTrue(detail.hasPrefix("Invalid config"), detail)
        }
        let patched = try await api.patchConfig(["top_n": .int(5)])
        XCTAssertEqual(patched.topN, 5)
        XCTAssertEqual(patched.namedAuthors, ["okafor"])
    }
}
