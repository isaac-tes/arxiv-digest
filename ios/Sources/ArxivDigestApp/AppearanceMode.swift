import SwiftUI

/// The user's appearance preference, persisted in `UserDefaults` under
/// `appearanceMode` and applied via `.preferredColorScheme`. `system` follows
/// the device setting (light/dark), the other two force a scheme.
enum AppearanceMode: String, CaseIterable, Identifiable {
    case system
    case light
    case dark

    var id: String { rawValue }

    var label: String {
        switch self {
        case .system: return "System"
        case .light: return "Light"
        case .dark: return "Dark"
        }
    }

    /// The scheme to force, or nil to follow the system.
    var colorScheme: ColorScheme? {
        switch self {
        case .system: return nil
        case .light: return .light
        case .dark: return .dark
        }
    }

    /// The stored raw value → mode, defaulting to `.system`.
    static func from(_ raw: String) -> AppearanceMode {
        AppearanceMode(rawValue: raw) ?? .system
    }
}
