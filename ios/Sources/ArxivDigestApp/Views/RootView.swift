import SwiftUI
import ArxivDigestCore

/// The root navigation, mirroring the web GUI: a ranked Papers list, a
/// Score-a-paper tab, and Settings (config + display + server).
struct RootView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        TabView {
            PapersListView()
                .tabItem { Label("Papers", systemImage: "list.bullet.rectangle") }

            ScoreView()
                .tabItem { Label("Score", systemImage: "number.circle") }

            SettingsView()
                .tabItem { Label("Settings", systemImage: "gearshape") }
        }
        .task {
            await model.loadConfig()
            await model.loadPresets()
            await model.loadDigest()
        }
    }
}
