import Foundation

/// The config as a file, for copying between devices by hand: the same flat
/// JSON object the Mac GUI writes (Profiles → Export) and reads (Import
/// profile from JSON), i.e. the engine's `Config` fields.
public enum ConfigFile {
    public static let fileName = "arxiv-digest-config.json"

    public enum ReadError: LocalizedError {
        case notAConfig
        public var errorDescription: String? {
            "That file isn't an arXiv Digest config (expected the JSON exported by the app or the GUI's Profiles tab)."
        }
    }

    /// Fields every engine config has; a file with none of them isn't one.
    private static let knownKeys: Set<String> = [
        "core_keywords", "named_authors", "low_priority_kw", "feeds", "default_feeds",
        "weights", "feed_weights", "top_n", "timeframe",
    ]

    /// Reads a GUI/app export (or the server's `{"data": {...}}` shape).
    public static func read(_ data: Data) throws -> DigestConfig {
        guard var object = try? JSONDecoder().decode([String: JSONValue].self, from: data) else {
            throw ReadError.notAConfig
        }
        if case .object(let inner)? = object["data"], object.count == 1 { object = inner }
        guard !knownKeys.isDisjoint(with: object.keys) else { throw ReadError.notAConfig }
        return DigestConfig(data: object)
    }

    /// Pretty-printed with sorted keys, so exports diff cleanly.
    public static func write(_ config: DigestConfig) throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        return try encoder.encode(config.data)
    }
}
