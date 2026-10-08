import Foundation

/// Display-only rendering of the inline LaTeX in arXiv titles and abstracts.
///
/// SwiftUI `Text` can't typeset math, so `$…$`, `$$…$$` and `\(…\)` become
/// Unicode: blackboard / calligraphic letters, Greek, sub- and superscripts
/// (when every character has a Unicode form, else `_x` / `_(xy)`), common
/// operators, `\frac`, `\sqrt` and accents. Outside math only text-mode
/// commands (`\textit{…}`, `\emph{…}`, …) and escapes (`\%`, `\&`, `\$`) are
/// touched. Scoring and search keep the raw text; this is for the screen.
///
/// ponytail: Unicode approximation, not a typesetter. Fractions, matrices and
/// big operators read as plain text; a KaTeX web view is the upgrade path.
public enum MathText {
    public static func render(_ text: String) -> String {
        guard text.contains("$") || text.contains("\\") else { return text }
        let c = Array(text)
        return segments(c).map { seg in
            seg.isMath ? math(Array(c[seg.content])) : textMode(Array(c[seg.whole]))
        }.joined()
    }

    /// The inline math regions (`$…$`, `$$…$$`, `\(…\)`), delimiters included.
    public static func mathRanges(in text: String) -> [Range<String.Index>] {
        let c = Array(text)
        return segments(c).filter(\.isMath).map { seg in
            text.index(text.startIndex, offsetBy: seg.whole.lowerBound)..<text.index(text.startIndex, offsetBy: seg.whole.upperBound)
        }
    }

    /// The paper page's abstract as HTML for KaTeX's auto-render: math kept
    /// verbatim with its delimiters, text-mode commands rendered, everything
    /// HTML-escaped, and `spans` (ranges of `text`) wrapped in
    /// `<span class="hl <aspect>">`. A span touching math is dropped: KaTeX
    /// can't render math split by markup.
    public static func html(_ text: String, spans: [HighlightSpan]) -> String {
        let c = Array(text)
        let offsets = spans.map {
            (text.distance(from: text.startIndex, to: $0.range.lowerBound),
             text.distance(from: text.startIndex, to: $0.range.upperBound), $0.aspect)
        }.sorted { $0.0 < $1.0 }
        var out = ""
        for seg in segments(c) {
            if seg.isMath { out += escape(String(c[seg.whole])); continue }
            var i = seg.whole.lowerBound
            for (lo, hi, aspect) in offsets where lo >= i && hi <= seg.whole.upperBound {
                out += escape(textMode(Array(c[i..<lo])))
                out += "<span class=\"hl \(aspect.rawValue)\">" + escape(textMode(Array(c[lo..<hi]))) + "</span>"
                i = hi
            }
            out += escape(textMode(Array(c[i..<seg.whole.upperBound])))
        }
        return out
    }

    private static func escape(_ s: String) -> String {
        s.replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
    }

    /// Text and math runs covering `c`; `content` excludes the delimiters.
    private struct Segment { let whole: Range<Int>; let content: Range<Int>; let isMath: Bool }

    private static func segments(_ c: [Character]) -> [Segment] {
        var out: [Segment] = []
        var textStart = 0, i = 0
        func emitText(upTo end: Int) {
            if end > textStart { out.append(Segment(whole: textStart..<end, content: textStart..<end, isMath: false)) }
        }
        while i < c.count {
            var delims: (open: Int, close: [Character])?
            if c[i] == "\\", i + 1 < c.count, c[i + 1] == "(" {
                delims = (2, ["\\", ")"])
            } else if c[i] == "\\" {
                i += 2  // an escape like \$ is text
                continue
            } else if c[i] == "$" {
                let double = i + 1 < c.count && c[i + 1] == "$"
                delims = (double ? 2 : 1, double ? ["$", "$"] : ["$"])
            }
            if let d = delims, let close = find(c, from: i + d.open, closer: d.close) {
                emitText(upTo: i)
                let end = close + d.close.count
                out.append(Segment(whole: i..<end, content: (i + d.open)..<close, isMath: true))
                textStart = end
                i = end
            } else {
                i += 1
            }
        }
        emitText(upTo: c.count)
        return out
    }

    private static func textMode(_ c: [Character]) -> String {
        var out = "", i = 0
        while i < c.count {
            if c[i] == "\\" {
                let (s, next) = textCommand(c, at: i)
                out += s
                i = next
            } else {
                out.append(c[i])
                i += 1
            }
        }
        return out
    }

    // MARK: - Scanning

    /// Index of the next unescaped `closer` sequence at or after `from`.
    private static func find(_ c: [Character], from: Int, closer: [Character]) -> Int? {
        var i = from
        while i + closer.count <= c.count {
            if Array(c[i..<(i + closer.count)]) == closer { return i }
            i += c[i] == "\\" && closer.first != "\\" ? 2 : 1  // skip \$ inside $…$
        }
        return nil
    }

    /// The `{…}` group starting at `i` (after optional spaces): its content and
    /// the index after it. A bare token counts as a one-character group.
    private static func group(_ c: [Character], at start: Int) -> ([Character], Int) {
        var i = start
        while i < c.count, c[i] == " " { i += 1 }
        guard i < c.count else { return ([], i) }
        if c[i] == "{" {
            var depth = 0, j = i
            while j < c.count {
                if c[j] == "\\" { j += 2; continue }
                if c[j] == "{" { depth += 1 }
                if c[j] == "}" { depth -= 1; if depth == 0 { return (Array(c[(i + 1)..<j]), j + 1) } }
                j += 1
            }
            return (Array(c[(i + 1)...]), c.count)
        }
        if c[i] == "\\" {
            let (name, next) = commandName(c, at: i)
            return (Array("\\" + name), next)
        }
        return ([c[i]], i + 1)
    }

    private static func commandName(_ c: [Character], at i: Int) -> (String, Int) {
        var j = i + 1
        while j < c.count, c[j].isLetter { j += 1 }
        if j == i + 1 { return (j < c.count ? String(c[j]) : "", min(j + 1, c.count)) }
        return (String(c[(i + 1)..<j]), j)
    }

    // MARK: - Text mode

    private static let textGroups: Set<String> = ["textit", "textbf", "emph", "textrm", "texttt", "textsc", "textsf", "text", "mbox"]

    private static func textCommand(_ c: [Character], at i: Int) -> (String, Int) {
        let (name, next) = commandName(c, at: i)
        if "$%&_#{}".contains(name), name.count == 1 { return (name, next) }
        if textGroups.contains(name) {
            let (arg, after) = group(c, at: next)
            return (render(String(arg)), after)
        }
        return (String(c[i..<next]), next)  // unknown: leave as typed
    }

    // MARK: - Math mode

    private static func math(_ c: [Character]) -> String {
        var out = ""
        var i = 0
        while i < c.count {
            let ch = c[i]
            switch ch {
            case "\\":
                let (name, next) = commandName(c, at: i)
                let (s, after) = command(name, c, next)
                out += s
                i = after
            case "_", "^":
                let (arg, next) = group(c, at: i + 1)
                out += script(math(arg), sub: ch == "_")
                i = next
            case "{", "}":
                i += 1
            case "~":
                out += " "
                i += 1
            default:
                out.append(ch)
                i += 1
            }
        }
        return out
    }

    private static func command(_ name: String, _ c: [Character], _ next: Int) -> (String, Int) {
        if let s = symbols[name] { return (s, next) }
        switch name {
        case "mathbb", "mathbbm":
            let (arg, after) = group(c, at: next)
            return (String(math(arg).map { doubleStruck($0) }), after)
        case "mathcal", "mathscr":
            let (arg, after) = group(c, at: next)
            return (String(math(arg).map { script($0) }), after)
        case "mathrm", "mathit", "mathbf", "mathsf", "mathtt", "boldsymbol", "bm", "text", "textrm",
             "textit", "textbf", "operatorname", "mbox":
            let (arg, after) = group(c, at: next)
            return (math(arg), after)
        case "frac", "dfrac", "tfrac":
            let (num, a1) = group(c, at: next)
            let (den, a2) = group(c, at: a1)
            return (wrap(math(num)) + "/" + wrap(math(den)), a2)
        case "sqrt":
            let (arg, after) = group(c, at: next)
            return ("√" + wrap(math(arg)), after)
        case "left", "right", "big", "Big", "bigg", "Bigg", "displaystyle", "limits", "nolimits":
            return ("", next)
        case ",", ":", ";", " ", "quad", "qquad":
            return (" ", next)
        case "!":
            return ("", next)
        default:
            if let mark = accents[name] {
                let (arg, after) = group(c, at: next)
                return (math(arg) + mark, after)
            }
            if name.count == 1 { return (name, next) }  // \{ \} \% \$ \_ …
            return (name, next)                          // \log, \sin, unknown → word
        }
    }

    /// `ab` → `(ab)` so `\frac{a+b}{2}` reads `(a+b)/2`.
    private static func wrap(_ s: String) -> String { s.count > 1 ? "(\(s))" : s }

    private static func script(_ s: String, sub: Bool) -> String {
        let map = sub ? subscripts : superscripts
        let mapped = s.map { map[$0] ?? (",′†*".contains($0) ? $0 : nil) }
        if !s.isEmpty, mapped.allSatisfy({ $0 != nil }) { return String(mapped.map { $0! }) }
        return (sub ? "_" : "^") + wrap(s)
    }

    // MARK: - Tables

    private static func doubleStruck(_ ch: Character) -> Character {
        let special: [Character: Character] = ["C": "ℂ", "H": "ℍ", "N": "ℕ", "P": "ℙ", "Q": "ℚ", "R": "ℝ", "Z": "ℤ", "1": "𝟙"]
        if let s = special[ch] { return s }
        return offset(ch, upper: 0x1D538, lower: 0x1D552, digit: 0x1D7D8)
    }

    private static func script(_ ch: Character) -> Character {
        let special: [Character: Character] = ["B": "ℬ", "E": "ℰ", "F": "ℱ", "H": "ℋ", "I": "ℐ", "L": "ℒ", "M": "ℳ", "R": "ℛ"]
        if let s = special[ch] { return s }
        return offset(ch, upper: 0x1D49C, lower: nil, digit: nil)
    }

    private static func offset(_ ch: Character, upper: UInt32, lower: UInt32?, digit: UInt32?) -> Character {
        guard let v = ch.unicodeScalars.first?.value, ch.unicodeScalars.count == 1 else { return ch }
        let base: UInt32?
        switch v {
        case 65...90: base = upper + (v - 65)
        case 97...122: base = lower.map { $0 + (v - 97) }
        case 48...57: base = digit.map { $0 + (v - 48) }
        default: base = nil
        }
        return base.flatMap(Unicode.Scalar.init).map(Character.init) ?? ch
    }

    private static func table(_ keys: String, _ values: String) -> [Character: Character] {
        precondition(keys.count == values.count, "MathText table out of step")
        return Dictionary(uniqueKeysWithValues: zip(keys, values))
    }

    private static let superscripts = table(
        "0123456789+-=()abcdefghijklmnoprstuvwxyzABDEGHIJKLMNOPRTUVWβγδθιφϕχ",
        "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻᴬᴮᴰᴱᴳᴴᴵᴶᴷᴸᴹᴺᴼᴾᴿᵀᵁⱽᵂᵝᵞᵟᶿᶥᵠᵠᵡ")

    private static let subscripts = table(
        "0123456789+-=()aehijklmnoprstuvxβγρφϕχ",
        "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓᵦᵧᵨᵩᵩᵪ")

    private static let accents: [String: String] = [
        "hat": "\u{0302}", "widehat": "\u{0302}", "tilde": "\u{0303}", "widetilde": "\u{0303}",
        "bar": "\u{0304}", "overline": "\u{0305}", "vec": "\u{20D7}", "dot": "\u{0307}", "ddot": "\u{0308}",
    ]

    private static let symbols: [String: String] = [
        // Greek
        "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ϵ", "varepsilon": "ε",
        "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "ϑ", "iota": "ι", "kappa": "κ",
        "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "varpi": "ϖ", "rho": "ρ",
        "varrho": "ϱ", "sigma": "σ", "varsigma": "ς", "tau": "τ", "upsilon": "υ", "phi": "ϕ",
        "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
        "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π",
        "Sigma": "Σ", "Upsilon": "Υ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
        // Operators and relations
        "times": "×", "cdot": "·", "pm": "±", "mp": "∓", "div": "÷", "ast": "∗", "star": "⋆",
        "circ": "∘", "otimes": "⊗", "oplus": "⊕", "wedge": "∧", "vee": "∨", "cup": "∪", "cap": "∩",
        "to": "→", "rightarrow": "→", "leftarrow": "←", "leftrightarrow": "↔", "Rightarrow": "⇒",
        "Leftarrow": "⇐", "Leftrightarrow": "⇔", "mapsto": "↦", "longrightarrow": "⟶",
        "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "neq": "≠", "ne": "≠", "approx": "≈",
        "simeq": "≃", "sim": "∼", "cong": "≅", "equiv": "≡", "propto": "∝", "ll": "≪", "gg": "≫",
        "lesssim": "≲", "gtrsim": "≳", "in": "∈", "notin": "∉", "ni": "∋", "subset": "⊂",
        "subseteq": "⊆", "supset": "⊃", "perp": "⊥", "parallel": "∥", "mid": "∣",
        // Misc symbols
        "infty": "∞", "partial": "∂", "nabla": "∇", "hbar": "ℏ", "ell": "ℓ", "dagger": "†",
        "ddagger": "‡", "prime": "′", "langle": "⟨", "rangle": "⟩", "sum": "∑", "prod": "∏",
        "int": "∫", "oint": "∮", "cdots": "⋯", "ldots": "…", "dots": "…", "forall": "∀",
        "exists": "∃", "neg": "¬", "emptyset": "∅", "varnothing": "∅", "Re": "ℜ", "Im": "ℑ",
        "aleph": "ℵ", "degree": "°", "lvert": "|", "rvert": "|", "vert": "|", "Vert": "‖",
        "lbrace": "{", "rbrace": "}",
    ]
}
