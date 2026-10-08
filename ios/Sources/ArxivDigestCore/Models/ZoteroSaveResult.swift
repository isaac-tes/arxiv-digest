import Foundation

/// Whether a paper can be saved to Zotero through the server, derived from
/// `GET /zotero/status`. Web API only (ADR 0005, amended); without a key the
/// app offers the share sheet (Share to Zotero), which needs no server.
public enum ZoteroSaveAvailability: Sendable, Equatable {
    /// The server has a Zotero Web API key — `POST /zotero/save` will create a
    /// `preprint` item.
    case web
    /// No Web API key on the server. The app offers Share to Zotero instead.
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

    public init(ok: Bool, mode: String, message: String) {
        self.ok = ok
        self.mode = mode
        self.message = message
    }
}
