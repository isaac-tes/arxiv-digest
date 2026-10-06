import SwiftUI
import UniformTypeIdentifiers
import UIKit
import ArxivDigestCore

/// The arXiv abstract page, used for Open / Share / Share to Zotero.
func absURL(_ link: String) -> URL? {
    URL(string: link)
}

/// Long-press menu on a paper card: open, share, copy, Zotero, remove.
struct PaperContextMenu: View {
    let paper: Paper
    @Environment(AppModel.self) private var model
    @Environment(\.openURL) private var openURL

    var body: some View {
        if let url = absURL(paper.link) {
            Button { openURL(url) } label: { Label("Open on arXiv", systemImage: "safari") }
        }
        if let pdf = paper.pdfURL {
            Button { openURL(pdf) } label: { Label("Open PDF", systemImage: "doc.richtext") }
        }
        if let url = absURL(paper.link) {
            ShareLink(item: url, subject: Text(paper.title)) {
                Label("Share…", systemImage: "square.and.arrow.up")
            }
        }
        Button {
            UIPasteboard.general.string = paper.id
            model.showToast("Copied \(paper.id)")
        } label: {
            Label("Copy arXiv ID", systemImage: "doc.on.doc")
        }
        if model.zoteroAvailability == .web {
            Button {
                Task { await model.saveToZotero(paper.id) }
            } label: {
                Label("Save to Zotero", systemImage: "books.vertical")
            }
        }
        Divider()
        Button(role: .destructive) {
            Task { await model.remove(paper) }
        } label: {
            Label("Remove from digest", systemImage: "eye.slash")
        }
    }
}

/// Save to Zotero (server Web API key) or, without a key, Share to Zotero via
/// the share sheet (ADR 0005 amendment).
struct ZoteroButton: View {
    let arxivId: String
    let link: String
    let title: String
    @Environment(AppModel.self) private var model
    @State private var isSaving = false
    @State private var savedAt: Date?

    var body: some View {
        switch model.zoteroAvailability {
        case .web:
            Button {
                Task {
                    isSaving = true
                    if await model.saveToZotero(arxivId) { savedAt = Date() }
                    isSaving = false
                }
            } label: {
                if isSaving {
                    ProgressView().controlSize(.small)
                } else if savedAt != nil {
                    Label("Saved ✓", systemImage: "checkmark")
                } else {
                    Label("Save to Zotero", systemImage: "books.vertical")
                }
            }
            .disabled(isSaving)
            .task(id: savedAt) {
                // The GUI's "Saved ✓" expires after 30 s so the paper can be re-saved.
                guard savedAt != nil else { return }
                try? await Task.sleep(for: .seconds(30))
                savedAt = nil
            }
        case .unavailable:
            if let url = absURL(link) {
                ShareLink(item: url, subject: Text(title)) {
                    Label("Share to Zotero", systemImage: "books.vertical")
                }
            }
        }
    }
}

/// A digest export (Markdown or JSON) written to a temp file when shared, so
/// it arrives as `digest-YYYY-MM-DD.md` / `.json` like the GUI downloads.
struct DigestFile: Transferable {
    let data: Data
    let fileName: String
    let type: UTType

    static func markdown(_ digest: Digest) -> DigestFile {
        DigestFile(data: Data(DigestExport.markdown(digest).utf8),
                   fileName: DigestExport.fileName(ext: "md"),
                   type: UTType(filenameExtension: "md") ?? .plainText)
    }

    static func json(_ digest: Digest) -> DigestFile {
        DigestFile(data: (try? DigestExport.json(digest)) ?? Data(),
                   fileName: DigestExport.fileName(ext: "json"), type: .json)
    }

    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(exportedContentType: .data) { file in
            let url = FileManager.default.temporaryDirectory.appendingPathComponent(file.fileName)
            try file.data.write(to: url, options: .atomic)
            return SentTransferredFile(url)
        }
    }
}
