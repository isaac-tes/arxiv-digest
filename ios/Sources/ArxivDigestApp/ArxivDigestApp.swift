import SwiftUI
import ArxivDigestCore

/// The arXiv Digest iOS app.
///
/// This is the thin SwiftUI target. The logic lives in `ArxivDigestCore` (an
/// SPM library that builds from VS Code); this target is opened in Xcode for
/// simulator/device runs, asset catalogs, and code signing.
@main
struct ArxivDigestApp: App {
    @State private var appModel = AppModel()
    @AppStorage("appearanceMode") private var appearanceRaw = AppearanceMode.system.rawValue

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(appModel)
                .preferredColorScheme(AppearanceMode.from(appearanceRaw).colorScheme)
        }
    }
}
