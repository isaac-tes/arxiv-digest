import SwiftUI
import ArxivDigestCore

/// The root tabs, mirroring the web GUI: Papers, Score a paper, Config (the
/// GUI's Keywords / Authors / Low priority / Feeds / Scoring / Profiles tabs)
/// and Settings (connection + the sidebar's Display section).
struct RootView: View {
    @Environment(AppModel.self) private var model
    @State private var tab: AppTab = .papers
    @State private var papersPath = NavigationPath()
    @State private var configPath: [ConfigPage] = []
    @State private var scoreInput = ""
    @State private var scoreRun = 0

    private let launch = LaunchOptions.current

    var body: some View {
        TabView(selection: $tab) {
            PapersListView(path: $papersPath)
                .tabItem { Label("Papers", systemImage: "doc.text.magnifyingglass") }
                .tag(AppTab.papers)

            ScoreView(input: $scoreInput, runRequest: $scoreRun)
                .tabItem { Label("Score", systemImage: "gauge.with.dots.needle.67percent") }
                .tag(AppTab.score)

            ConfigView(path: $configPath)
                .tabItem { Label("Config", systemImage: "slider.horizontal.3") }
                .tag(AppTab.config)
                .badge(model.isDirty ? Text("•") : nil)

            SettingsView()
                .tabItem { Label("Settings", systemImage: "gearshape") }
                .tag(AppTab.settings)
        }
        .overlay(alignment: .bottom) {
            if let toast = model.toast {
                ToastView(toast: toast) { model.toast = nil }
                    .padding(.bottom, 64)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .animation(.spring(duration: 0.35), value: model.toast)
        // A config .json opened from AirDrop / Files: import it and show Config.
        .onOpenURL { url in
            guard url.isFileURL, let data = try? Data(contentsOf: url) else { return }
            if model.importConfig(from: data) { tab = .config }
        }
        .task {
            KaTeXWebView.prewarm()  // KaTeX loaded before the first paper page
            await model.bootstrap()
            await applyLaunchOptions()
        }
    }

    /// Screenshot / deep-link options (see `LaunchOptions`).
    private func applyLaunchOptions() async {
        if let i = launch.dayIndex, let days = model.digest?.availableDays, days.indices.contains(i - 1) {
            await model.selectDay(days[i - 1])
        }
        if let r = launch.removeRank, let p = model.digest?.papers.first(where: { $0.rank == r }) {
            await model.remove(p)
            model.toast = nil
        }
        if launch.dirty {
            var kws = model.config.coreKeywords
            DigestConfig.append("quantum geometry", to: &kws)
            model.config.coreKeywords = kws
        }
        if let tab = launch.tab { self.tab = tab }
        if let page = launch.configPage {
            tab = .config
            configPath = [page]
        }
        if let r = launch.openPaperRank, let p = model.digest?.papers.first(where: { $0.rank == r }) {
            tab = .papers
            papersPath.append(p)
        }
        if let id = launch.scoreID {
            tab = .score
            scoreInput = id
            scoreRun += 1
        }
    }
}
