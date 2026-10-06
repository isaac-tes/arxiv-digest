import SwiftUI
import ArxivDigestCore

/// The score badge on each card: the GUI's "Score" metric, with a fill that
/// grows with the score relative to the digest's best paper.
struct ScoreBadge: View {
    let score: Int
    var maxScore: Int = 0
    var large = false

    private var fraction: Double {
        guard maxScore > 0 else { return 1 }
        return min(max(Double(score) / Double(maxScore), 0), 1)
    }

    var body: some View {
        VStack(spacing: 1) {
            Text("\(score)")
                .font(large ? .title.weight(.bold) : .title3.weight(.bold))
                .monospacedDigit()
            Text("score")
                .font(.system(size: large ? 11 : 9, weight: .semibold))
                .textCase(.uppercase)
                .foregroundStyle(.secondary)
        }
        .frame(minWidth: large ? 72 : 52)
        .padding(.vertical, large ? 10 : 6)
        .background {
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(Color.accentColor.opacity(0.08 + 0.22 * fraction))
        }
        .overlay {
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .strokeBorder(Color.accentColor.opacity(0.25 + 0.5 * fraction), lineWidth: 1)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Score \(score)")
    }
}

/// Renders markdown with `**bold**` / `*italic*` (absence reasons are
/// written that way by the server, mirroring the GUI).
struct MarkdownText: View {
    let markdown: String
    init(_ markdown: String) { self.markdown = markdown }

    var body: some View {
        Text((try? AttributedString(markdown: markdown, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)))
             ?? AttributedString(markdown))
    }
}

/// A colored callout, like Streamlit's st.info / st.success / st.warning.
struct Callout<Content: View>: View {
    enum Style {
        case info, success, warning, error

        var color: Color {
            switch self {
            case .info: return .blue
            case .success: return .green
            case .warning: return .orange
            case .error: return .red
            }
        }

        var icon: String {
            switch self {
            case .info: return "info.circle.fill"
            case .success: return "checkmark.circle.fill"
            case .warning: return "exclamationmark.triangle.fill"
            case .error: return "xmark.octagon.fill"
            }
        }
    }

    let style: Style
    @ViewBuilder let content: Content

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Image(systemName: style.icon).foregroundStyle(style.color)
            content.frame(maxWidth: .infinity, alignment: .leading)
        }
        .font(.callout)
        .padding(12)
        .background(style.color.opacity(0.12), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }
}

/// The transient confirmation at the bottom of the screen ("Saved ✓",
/// "Removed … Undo").
struct ToastView: View {
    let toast: Toast
    let dismiss: () -> Void

    private var icon: String {
        switch toast.kind {
        case .success: return "checkmark.circle.fill"
        case .info: return "info.circle.fill"
        case .error: return "exclamationmark.triangle.fill"
        }
    }

    private var tint: Color {
        switch toast.kind {
        case .success: return .green
        case .info: return .accentColor
        case .error: return .red
        }
    }

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: icon).foregroundStyle(tint)
            Text(toast.message)
                .font(.subheadline.weight(.medium))
                .lineLimit(2)
                .frame(maxWidth: .infinity, alignment: .leading)
            if let title = toast.actionTitle, let action = toast.action {
                Button(title) {
                    action()
                    dismiss()
                }
                .font(.subheadline.weight(.semibold))
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(.regularMaterial, in: Capsule())
        .overlay(Capsule().strokeBorder(.quaternary))
        .shadow(color: .black.opacity(0.15), radius: 12, y: 4)
        .padding(.horizontal, 16)
        .onTapGesture { if toast.action == nil { dismiss() } }
        .accessibilityElement(children: .combine)
    }
}

/// "Unsaved changes · Discard · Save", pinned above the tab bar in the
/// Config and Settings tabs while the working config differs from the saved one.
struct SaveBar: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "pencil.circle.fill").foregroundStyle(.orange)
            Text("Unsaved changes").font(.subheadline.weight(.medium))
            Spacer()
            Button("Discard", role: .destructive) { model.discardChanges() }
                .font(.subheadline)
            Button {
                Task { await model.saveConfig() }
            } label: {
                if model.isSaving {
                    ProgressView().controlSize(.small)
                } else {
                    Text("Save").font(.subheadline.weight(.semibold))
                }
            }
            .buttonStyle(.borderedProminent)
            .disabled(model.isSaving)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(.regularMaterial)
        .overlay(alignment: .top) { Divider() }
    }
}

/// A simple flow layout that wraps chips onto multiple lines.
struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let maxWidth = proposal.width ?? .infinity
        var x: CGFloat = 0, y: CGFloat = 0, rowHeight: CGFloat = 0, widest: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > maxWidth, x > 0 {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            x += size.width + spacing
            widest = max(widest, x - spacing)
            rowHeight = max(rowHeight, size.height)
        }
        return CGSize(width: proposal.width ?? widest, height: y + rowHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX, y = bounds.minY, rowHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > bounds.maxX, x > bounds.minX {
                x = bounds.minX
                y += rowHeight + spacing
                rowHeight = 0
            }
            subview.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
    }
}

/// A small rounded chip.
struct Chip: View {
    let text: String
    var color: Color = .secondary

    var body: some View {
        Text(text)
            .font(.caption.weight(.medium))
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(Capsule().fill(color.opacity(0.16)))
            .overlay(Capsule().strokeBorder(color.opacity(0.45), lineWidth: 0.5))
    }
}

extension Date {
    /// "12 min ago"-style relative time.
    var relativeDescription: String {
        let f = RelativeDateTimeFormatter()
        f.unitsStyle = .short
        return f.localizedString(for: self, relativeTo: Date())
    }
}
