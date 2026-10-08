import XCTest
@testable import ArxivDigestCore

/// The config file copied between the Mac GUI (Profiles → Export / Import
/// profile from JSON) and the iPhone (Settings → Export / Import config):
/// the engine's `Config` fields as one flat JSON object.
final class ConfigFileTests: XCTestCase {
    func testReadsAGUIProfileExport() throws {
        let gui = """
        {"core_keywords": ["floquet"], "named_authors": ["Ada Lovelace"], "top_n": 25,
         "weights": {"core_keyword": 6}, "feeds": {"quant-ph": "https://arxiv.org/list/quant-ph/new"},
         "word_boundary_matching": true}
        """
        let cfg = try ConfigFile.read(Data(gui.utf8))
        XCTAssertEqual(cfg.coreKeywords, ["floquet"])
        XCTAssertEqual(cfg.namedAuthors, ["Ada Lovelace"])
        XCTAssertEqual(cfg.topN, 25)
    }

    func testAcceptsTheServersWrappedShape() throws {
        let cfg = try ConfigFile.read(Data(#"{"data": {"core_keywords": ["anyon"]}}"#.utf8))
        XCTAssertEqual(cfg.coreKeywords, ["anyon"])
    }

    func testRoundTrip() throws {
        var cfg = DigestConfig()
        cfg.coreKeywords = ["floquet", "anyon"]
        cfg.topN = 12
        let back = try ConfigFile.read(ConfigFile.write(cfg))
        XCTAssertEqual(back, cfg)
        // Flat, human-readable JSON like the GUI's export.
        let text = String(decoding: try ConfigFile.write(cfg), as: UTF8.self)
        XCTAssertTrue(text.contains("\"core_keywords\""))
        XCTAssertFalse(text.contains("\"data\""))
    }

    func testRejectsNonConfigFiles() {
        XCTAssertThrowsError(try ConfigFile.read(Data("not json".utf8)))
        XCTAssertThrowsError(try ConfigFile.read(Data("[1, 2]".utf8)))
        XCTAssertThrowsError(try ConfigFile.read(Data(#"{"hello": "world"}"#.utf8)))
    }
}
