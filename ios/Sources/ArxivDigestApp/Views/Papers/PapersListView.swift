import SwiftUI
import ArxivDigestCore

/// The Papers tab, mirroring the web GUI's: the ranked digest for the saved
/// timeframe / Top N, a day picker for past-week fetches, search over title /
/// authors / abstract, a "Removed papers" section with Restore, swipe to
/// remove, and Markdown / JSON export. Pull to refresh fetches from arXiv again.
struct PapersListView: View {
    @Environment(AppModel.self) private var model
    @Binding var path: NavigationPath
    @State private var query = ""
    @State private var showRemoved = false

    private var papers: [Paper] {
        PaperSearch.filter(model.digest?.papers ?? [], query: query)
    }

    var body: some View {
        NavigationStack(path: $path) {
            content
                .navigationTitle("arXiv Digest")
                .navigationDestination(for: Paper.self) { PaperDetailView(paper: $0) }
                .toolbar { toolbar }
        }
    }

    @ViewBuilder
    private var content: some View {
        if let digest = model.digest {
            list(digest)
        } else if model.isLoading {
            VStack(spacing: 14) {
                ProgressView().controlSize(.large)
                Text("Fetching from arXiv…").font(.headline)
                Text("The first past-week fetch queries each feed and can take about half a minute. Later loads come from the server's cache.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 40)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            ContentUnavailableView {
                Label("Can't load the digest", systemImage: "wifi.exclamationmark")
            } description: {
                Text(model.digestError ?? "Pull to refresh.")
            } actions: {
                Button("Try again") { Task { await model.bootstrap() } }
                    .buttonStyle(.borderedProminent)
                Text("Check the server address in Settings, or switch to Demo mode to explore with sample papers.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func list(_ digest: Digest) -> some View {
        let maxScore = digest.papers.map(\.score).max() ?? 0
        return List {
            Section {
                header(digest)
                    .listRowSeparator(.hidden)
                if !digest.availableDays.isEmpty {
                    DayPicker(days: digest.availableDays, selected: model.selectedDay) { day in
                        Task { await model.selectDay(day) }
                    }
                    .listRowInsets(EdgeInsets(top: 4, leading: 0, bottom: 8, trailing: 0))
                    .listRowSeparator(.hidden)
                }
                ForEach(digest.notices, id: \.self) { notice in
                    Callout(style: .warning) { Text(notice) }
                        .listRowSeparator(.hidden)
                }
                if let error = model.digestError {
                    Callout(style: .error) { Text(error) }
                        .listRowSeparator(.hidden)
                }
                if !digest.removed.isEmpty {
                    removedSection(digest.removed)
                        .listRowSeparator(.hidden)
                }
            }

            Section {
                if digest.papers.isEmpty {
                    ContentUnavailableView {
                        Label("No papers left", systemImage: "line.3.horizontal.decrease.circle")
                    } description: {
                        Text("No papers left after filtering. Pick another day, include replacement submissions"
                             + (digest.removed.isEmpty ? "." : ", or restore removed papers."))
                    }
                } else if papers.isEmpty {
                    ContentUnavailableView.search(text: query)
                }
                ForEach(papers) { paper in
                    NavigationLink(value: paper) {
                        PaperRowView(paper: paper, config: model.config, maxScore: maxScore)
                    }
                    .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                        Button(role: .destructive) {
                            Task { await model.remove(paper) }
                        } label: {
                            Label("Remove", systemImage: "eye.slash")
                        }
                    }
                    .swipeActions(edge: .leading) {
                        if model.zoteroAvailability == .web {
                            Button {
                                Task { await model.saveToZotero(paper.id) }
                            } label: {
                                Label("Zotero", systemImage: "books.vertical")
                            }
                            .tint(.indigo)
                        }
                    }
                    .contextMenu { PaperContextMenu(paper: paper) }
                }
            } footer: {
                if !digest.papers.isEmpty {
                    Text(digest.caption(showing: papers.count))
                        .font(.footnote)
                        .padding(.top, 6)
                }
            }
        }
        .listStyle(.plain)
        .searchable(text: $query, prompt: "Search title / authors / abstract")
        .refreshable { await model.loadDigest(refresh: true) }
        .animation(.default, value: digest.papers.map(\.id))
    }

    /// "Past week · 3 feeds · fetched 12 min ago".
    private func header(_ digest: Digest) -> some View {
        var parts = [digest.timeframe == "today" ? "Today" : "Past week"]
        if !digest.feeds.isEmpty {
            parts.append(digest.feeds.count == 1 ? digest.feeds[0] : "\(digest.feeds.count) feeds")
        }
        parts.append("top \(digest.requestedTop)")
        if let date = digest.fetchedDate { parts.append("fetched \(date.relativeDescription)") }
        return Text(parts.joined(separator: " · "))
            .font(.footnote)
            .foregroundStyle(.secondary)
    }

    /// The GUI's "Removed papers (n)" expander.
    private func removedSection(_ removed: [Paper]) -> some View {
        DisclosureGroup(isExpanded: $showRemoved) {
            VStack(alignment: .leading, spacing: 10) {
                Text("Only papers that would otherwise appear in this ranking are listed. Removed papers stay hidden across reloads and later fetches.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                ForEach(removed) { p in
                    HStack {
                        Text(p.title).font(.subheadline).lineLimit(2)
                        Spacer()
                        Button("Restore") { Task { await model.restore([p.id]) } }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                    }
                }
                if removed.count > 1 {
                    Button("Restore all") { Task { await model.restore(removed.map(\.id)) } }
                        .font(.subheadline.weight(.semibold))
                }
            }
            .padding(.top, 6)
        } label: {
            Label("Removed papers (\(removed.count))", systemImage: "eye.slash")
                .font(.subheadline.weight(.medium))
        }
        .buttonStyle(.borderless)
    }

    @ToolbarContentBuilder
    private var toolbar: some ToolbarContent {
        ToolbarItem(placement: .topBarLeading) {
            Menu {
                Picker("Timeframe", selection: timeframeBinding) {
                    Label("Today", systemImage: "sun.max").tag("today")
                    Label("Past week", systemImage: "calendar").tag("pastweek")
                }
                Picker("Top N", selection: topNBinding) {
                    ForEach(topNOptions, id: \.self) { Text("Top \($0)").tag($0) }
                }
                .pickerStyle(.menu)
                if let digest = model.digest, !digest.papers.isEmpty {
                    Divider()
                    ShareLink(item: DigestFile.markdown(digest), preview: SharePreview(DigestExport.fileName(ext: "md"))) {
                        Label("Export Markdown", systemImage: "doc.plaintext")
                    }
                    ShareLink(item: DigestFile.json(digest), preview: SharePreview(DigestExport.fileName(ext: "json"))) {
                        Label("Export JSON", systemImage: "curlybraces")
                    }
                }
            } label: {
                Label("View options", systemImage: "line.3.horizontal.decrease.circle")
            }
        }
        ToolbarItem(placement: .topBarTrailing) {
            if model.isLoading {
                ProgressView()
            } else {
                Button {
                    Task { await model.loadDigest(refresh: true) }
                } label: {
                    Label("Fetch from arXiv", systemImage: "arrow.clockwise")
                }
            }
        }
    }

    private var topNOptions: [Int] {
        Array(Set([5, 10, 15, 20, 25, 30, 50, 100, model.savedConfig.topN])).sorted()
    }

    private var timeframeBinding: Binding<String> {
        Binding(
            get: { model.savedConfig.timeframe },
            set: { tf in Task { await model.setFetchOptions(timeframe: tf) } })
    }

    private var topNBinding: Binding<Int> {
        Binding(
            get: { model.savedConfig.topN },
            set: { n in Task { await model.setFetchOptions(topN: n) } })
    }
}

/// Horizontal chips: "All days" plus each announcement day in the fetch
/// (the GUI's Day picker; arXiv has no URL for older days).
struct DayPicker: View {
    let days: [String]
    let selected: String?
    let select: (String?) -> Void

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    chip("All days", day: nil)
                    ForEach(days, id: \.self) { chip(Self.short($0), day: $0) }
                }
                .padding(.horizontal, 16)
            }
            .onAppear { proxy.scrollTo(selected ?? "all", anchor: .center) }
            .onChange(of: selected) {
                withAnimation { proxy.scrollTo(selected ?? "all", anchor: .center) }
            }
        }
    }

    private func chip(_ label: String, day: String?) -> some View {
        let isOn = selected == day
        return Button { select(day) } label: {
            Text(label)
                .font(.subheadline.weight(isOn ? .semibold : .regular))
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(Capsule().fill(isOn ? Color.accentColor : Color.secondary.opacity(0.12)))
                .foregroundStyle(isOn ? Color.white : Color.primary)
        }
        .buttonStyle(.plain)
        .id(day ?? "all")
        .accessibilityAddTraits(isOn ? .isSelected : [])
    }

    /// "Fri, 02 Oct 2026" → "Fri 2 Oct".
    static func short(_ label: String) -> String {
        let parts = label.replacingOccurrences(of: ",", with: "").split(separator: " ")
        guard parts.count >= 3, let dayNum = Int(parts[1]) else { return label }
        return "\(parts[0]) \(dayNum) \(parts[2])"
    }
}
