import Foundation

/// How to save a paper to Zotero (ADR 0005).
public enum ZoteroMode: String, Sendable {
    case web        // Zotero Web API (server needs an API key)
    case deeplink   // hand off to the Zotero iOS app via a zotero:// link
}

/// Whether a paper can actually be saved to Zotero, derived from
/// `GET /zotero/status`.
public enum ZoteroSaveAvailability: Sendable, Equatable {
    /// The server has a Zotero Web API key — `POST /zotero/save` will create a
    /// `preprint` item.
    case web
    /// No Web API key. Saving is not offered: the server's `deeplink` mode only
    /// returns a `zotero://select/...` link, which selects a *pre-existing*
    /// item and cannot create one from an arXiv id (Zotero URI scheme docs).
    case unavailable
}

/// Decides how (whether) a paper can be saved to Zotero from the current server
/// configuration. Kept pure so it is unit-testable without a live server.
public enum ZoteroPolicy {
    public static func availability(from status: [String: Bool]) -> ZoteroSaveAvailability {
        (status["web_api_available"] ?? false) ? .web : .unavailable
    }
}

/// Response from `POST /zotero/save`.
public struct ZoteroSaveResult: Codable, Sendable {
    public let ok: Bool
    public let mode: String
    public let message: String
    public let deepLink: String?

    enum CodingKeys: String, CodingKey {
        case ok, mode, message
        case deepLink = "deep_link"
    }

    public init(ok: Bool, mode: String, message: String, deepLink: String? = nil) {
        self.ok = ok
        self.mode = mode
        self.message = message
        self.deepLink = deepLink
    }
}
