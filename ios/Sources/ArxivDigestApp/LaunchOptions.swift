import Foundation

/// Command-line launch options, used by `ios/scripts/screenshots.sh` to open
/// a specific screen deterministically (e.g. `xcrun simctl launch … -demo
/// -tab score -score 2609.21188`). Harmless in normal use: nothing passes them.
struct LaunchOptions {
    /// Force demo mode for this launch (does not change the saved preference).
    var demo = false
    /// Force Standalone mode (on-device fetch and scoring) for this launch.
    var standalone = false
    /// Initial tab.
    var tab: AppTab?
    /// Push the detail of the paper at this 1-based rank.
    var openPaperRank: Int?
    /// Prefill and run Score-a-paper with this id.
    var scoreID: String?
    /// Open a Config sub-page.
    var configPage: ConfigPage?
    /// Remove the paper at this rank on launch (shows the Removed section).
    var removeRank: Int?
    /// Pick the n-th available day (1-based) on launch.
    var dayIndex: Int?
    /// Make a harmless config edit so the unsaved-changes bar shows.
    var dirty = false

    static let current = LaunchOptions(arguments: ProcessInfo.processInfo.arguments)

    init(arguments: [String]) {
        var it = arguments.dropFirst().makeIterator()
        while let arg = it.next() {
            switch arg {
            case "-demo": demo = true
            case "-standalone": standalone = true
            case "-dirty": dirty = true
            case "-tab": tab = it.next().flatMap(AppTab.init(rawValue:))
            case "-open-paper": openPaperRank = it.next().flatMap(Int.init)
            case "-score": scoreID = it.next()
            case "-config-page": configPage = it.next().flatMap(ConfigPage.init(rawValue:))
            case "-remove": removeRank = it.next().flatMap(Int.init)
            case "-day": dayIndex = it.next().flatMap(Int.init)
            default: break
            }
        }
    }
}

enum AppTab: String, Hashable, CaseIterable {
    case papers, score, config, settings
}

enum ConfigPage: String, Hashable, CaseIterable, Identifiable {
    case keywords, authors, lowPriority = "low-priority", feeds, scoring, presets

    var id: String { rawValue }

    var title: String {
        switch self {
        case .keywords: return "Keywords"
        case .authors: return "Authors"
        case .lowPriority: return "Low priority"
        case .feeds: return "Feeds"
        case .scoring: return "Scoring"
        case .presets: return "Starter presets"
        }
    }

    var systemImage: String {
        switch self {
        case .keywords: return "text.magnifyingglass"
        case .authors: return "person.2"
        case .lowPriority: return "arrow.down.circle"
        case .feeds: return "dot.radiowaves.up.forward"
        case .scoring: return "slider.horizontal.3"
        case .presets: return "sparkles"
        }
    }
}
