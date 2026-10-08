import SwiftUI
import WebKit
import ArxivDigestCore

/// The paper page's abstract typeset with bundled KaTeX (offline).
///
/// Performance: only abstracts that contain math use this (the rest stay
/// native `Text`), the list never does, and one web view with KaTeX already
/// loaded is kept warm and reused between paper pages, so opening a paper only
/// swaps the content. The Unicode version shows until KaTeX has rendered.
struct MathAbstractView: View {
    let abstract: String
    let config: DigestConfig
    let underline: Bool

    @State private var height: CGFloat = 0

    private var html: String {
        let spans = config.highlightTermsAbstract
            ? HighlightEngine.spans(in: abstract, keywords: config.coreKeywords,
                                    lowPriority: config.lowPriorityKeywords, wordBoundary: config.wordBoundaryMatching)
            : []
        return MathText.html(abstract, spans: spans)
    }

    var body: some View {
        ZStack(alignment: .topLeading) {
            Text(Highlight.terms(abstract, enabled: config.highlightTermsAbstract, config: config, underline: underline))
                .font(.body)
                .fixedSize(horizontal: false, vertical: true)
                .opacity(height > 0 ? 0 : 1)
            KaTeXWebView(html: html, css: KaTeXWebView.css(config: config, underline: underline), height: $height)
                .frame(height: height)
                .opacity(height > 0 ? 1 : 0)
        }
        .frame(height: height > 0 ? height : nil, alignment: .top)
    }
}

/// A non-scrolling `WKWebView` showing HTML with KaTeX math; reports its
/// content height. Backed by a one-view pool (see `prewarm()`).
struct KaTeXWebView: UIViewRepresentable {
    let html: String
    let css: String
    @Binding var height: CGFloat

    // MARK: Pool

    @MainActor private static var spare: WKWebView?

    /// Load KaTeX into a spare web view ahead of the first paper page.
    @MainActor static func prewarm() {
        if spare == nil { spare = makeWebView() }
    }

    @MainActor private static func makeWebView() -> WKWebView {
        let web = WKWebView(frame: .zero, configuration: WKWebViewConfiguration())
        web.isOpaque = false
        web.backgroundColor = .clear
        web.scrollView.isScrollEnabled = false
        web.scrollView.backgroundColor = .clear
        if let dir = Bundle.main.url(forResource: "KaTeX", withExtension: nil) {
            web.loadHTMLString(template, baseURL: dir)
        }
        return web
    }

    // MARK: UIViewRepresentable

    func makeCoordinator() -> Coordinator { Coordinator(height: $height) }

    func makeUIView(context: Context) -> WKWebView {
        let web = Self.spare ?? Self.makeWebView()
        Self.spare = nil
        let messages = web.configuration.userContentController
        messages.removeScriptMessageHandler(forName: "height")
        messages.add(WeakHandler(context.coordinator), name: "height")
        web.navigationDelegate = context.coordinator
        context.coordinator.web = web
        return web
    }

    func updateUIView(_ web: WKWebView, context: Context) {
        context.coordinator.height = $height
        context.coordinator.show(html: html, css: css)
    }

    static func dismantleUIView(_ web: WKWebView, coordinator: Coordinator) {
        web.configuration.userContentController.removeScriptMessageHandler(forName: "height")
        web.navigationDelegate = nil
        web.evaluateJavaScript("show('', '')")
        if spare == nil { spare = web }  // reuse: KaTeX stays loaded
    }

    @MainActor final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        var height: Binding<CGFloat>
        weak var web: WKWebView?
        private var shown: String?
        private var pending: (html: String, css: String)?

        init(height: Binding<CGFloat>) { self.height = height }

        func show(html: String, css: String) {
            let key = css + "\u{0}" + html
            guard key != shown else { return }
            shown = key
            pending = (html, css)
            flush()
        }

        /// Sends pending content once the template (and KaTeX) has loaded;
        /// a pooled view has, so it renders at once.
        private func flush() {
            guard let web, let p = pending, !web.isLoading,
                  let args = try? JSONEncoder().encode([p.html, p.css]),
                  let json = String(data: args, encoding: .utf8) else { return }
            pending = nil
            web.evaluateJavaScript("show(...\(json))")
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) { flush() }

        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                     decisionHandler: @escaping @MainActor (WKNavigationActionPolicy) -> Void) {
            decisionHandler(action.navigationType == .other ? .allow : .cancel)  // no link navigation
        }

        func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
            if let h = message.body as? Double, h > 0 { height.wrappedValue = CGFloat(h) }
        }
    }

    /// Breaks the user-content-controller → handler retain cycle.
    private final class WeakHandler: NSObject, WKScriptMessageHandler {
        weak var target: (any WKScriptMessageHandler)?
        init(_ target: any WKScriptMessageHandler) { self.target = target }
        func userContentController(_ c: WKUserContentController, didReceive m: WKScriptMessage) {
            target?.userContentController(c, didReceive: m)
        }
    }

    // MARK: HTML and CSS

    /// Highlight colors as in the native text: a faint aspect background,
    /// tinted text (darkened in light mode) when "Tint font" is on, an optional
    /// dotted underline.
    static func css(config: DigestConfig, underline: Bool) -> String {
        var light = "", dark = ""
        for aspect in [HighlightAspect.keyword, .lowPriority] {
            let hex = config.color(for: aspect)
            let base = ".hl.\(aspect.rawValue){background:\(hex)24;"
                + (underline ? "text-decoration:underline dotted \(hex);" : "")
            let tint = config.fontColor(for: aspect)
            light += base + (tint ? "color:\(ColorContrast.readableOnWhite(hex));" : "") + "}"
            dark += base + (tint ? "color:\(hex);" : "") + "}"
        }
        return light + "@media (prefers-color-scheme:dark){\(dark)}"
    }

    private static let template = """
    <!doctype html><html><head>
    <meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
    <link rel="stylesheet" href="katex.min.css">
    <style>
    :root{color-scheme:light dark}
    html,body{margin:0;padding:0;background:transparent}
    body{font:-apple-system-body;color:#000;-webkit-text-size-adjust:100%;overflow-wrap:break-word}
    @media (prefers-color-scheme:dark){body{color:#fff}}
    .katex{font-size:1.05em}
    .hl{border-radius:3px}
    </style><style id="hl"></style>
    <script src="katex.min.js"></script><script src="auto-render.min.js"></script>
    </head><body><div id="c"></div><script>
    const c = document.getElementById('c');
    function post(){ webkit.messageHandlers.height && webkit.messageHandlers.height.postMessage(c.getBoundingClientRect().height); }
    function show(html, css){
      document.getElementById('hl').textContent = css;
      c.innerHTML = html;
      if (html) renderMathInElement(c, {delimiters:[
        {left:'$$',right:'$$',display:false},{left:'$',right:'$',display:false},
        {left:'\\\\(',right:'\\\\)',display:false}], throwOnError:false});
      post();
    }
    new ResizeObserver(post).observe(c);
    </script></body></html>
    """
}
