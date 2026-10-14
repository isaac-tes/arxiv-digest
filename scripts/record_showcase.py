"""Record the README/docs promo assets from the live apps.

Web (hero banner + tour of the web app):

    uv run --group dev --with playwright --with imageio-ffmpeg python scripts/record_showcase.py
    (first time: uv run --with playwright playwright install chromium-headless-shell)

iOS (tour of the iPhone app), with the app built and installed on a booted
simulator (see ios/HANDOFF.md):

    uv run --group dev --with imageio-ffmpeg python scripts/record_showcase.py --ios <simulator-udid>

Both drive the real apps against live arXiv with `demo_config()` (topological
matter, well-known authors) in dark mode. The web run uses a copy of the app
with its own config, a throwaway HOME and a stand-in for Zotero's local API with
generic collections, so nothing personal appears and none of your files change.

Screenshots go to WORK. `--options` renders every design into WORK/options with
a preview page; otherwise the chosen design (`--design` for the web tour,
`--ios-design` for the iPhone clip) goes to docs/assets. `--render-only`
re-renders from the screenshots in WORK.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import arxiv_digest as ad  # noqa: E402

ASSETS = ROOT / "docs" / "assets"
WORK = Path("/tmp/arxiv-digest-showcase")
OPTIONS = WORK / "options"
DEMO_HOME = Path("/tmp/arxiv-digest-demo-home")  # short path: it can show in the GUI
PORT, ZOTERO_PORT = 8799, 8798
VIEW = (1440, 900)  # CSS px; screenshots are 2x
SCALE = 2
FPS = 30
BG = (14, 17, 23)  # Streamlit dark background
INDIGO, NAVY = (49, 46, 129), (15, 23, 42)
ACCENT, GREEN, MUTED = (165, 180, 252), (74, 222, 128), (100, 116, 139)
Rect = tuple[float, float, float, float]  # x, y, w, h in CSS px


def demo_config() -> ad.Config:
    """Topological-matter interests with well-known authors, so the cards look like real use.

    Showcase-only: starter presets stay generic and free of named groups."""
    cfg = ad.preset_config("floquet-topological")
    cfg.core_keywords = [
        "chern", "fractional chern", "flat band", "quantum hall", "magnon", "moiré",
        "topological", "berry curvature", "anyons", "ising", "floquet", "twisted",
    ]
    cfg.named_authors = ["bernevig", "regnault", "vishwanath", "fu", "neupert", "sondhi", "goldman"]
    names = ["cond-mat.str-el", "cond-mat.mes-hall", "cond-mat.quant-gas"]
    cfg.feeds = {n: f"https://arxiv.org/list/{n}/new" for n in names}
    cfg.default_feeds = names
    cfg.feed_weights = {"cond-mat.str-el": 4, "cond-mat.mes-hall": 4, "cond-mat.quant-gas": 2}
    cfg.timeframe, cfg.top_n = "pastweek", 10
    cfg.highlight_terms_summary = True
    return cfg


# What the web tour shows, in order. Each beat ticks the features it shows.
WEB_FEATURES = {
    "fetch": "Fetch any arXiv category",
    "rank": "Ranked by your own rules",
    "highlight": "Matches highlighted",
    "why": "Every score explained",
    "day": "Filter by day",
    "search": "Search",
    "export": "Markdown and JSON export",
    "zotero": "Save to Zotero",
    "pdf": "Open the PDF",
    "author": "Follow authors from a paper",
    "unsaved": "Unsaved changes, one Save",
    "remove": "Remove and restore papers",
    "score": "Score any arXiv link",
    "lists": "Keywords, authors, low priority",
    "weights": "Weights and category bonuses",
    "presets": "Starter presets and profiles",
    "json": "Config as JSON",
    "sync": "Sync with the iPhone app",
    "display": "Highlight colors",
}
CHAPTERS = ["Read", "Curate", "Tune and sync"]


@dataclass
class Beat:
    caption: str
    before: str  # screenshot file
    target: tuple[float, float]  # cursor click point
    after: str
    focus: Rect  # what to show after the action
    click: bool = True
    target_box: Rect = (0.0, 0.0, 0.0, 0.0)  # the clicked element, for framing
    features: list[str] = field(default_factory=list)
    chapter: int = 0
    steps: list[str] = field(default_factory=list)  # screenshots between click and result (typing)
    new_tab: bool = False  # the result is another browser tab (PDF, downloaded file)
    sub: bool = False  # a quick intermediate step (opening a dropdown or popover)


@dataclass
class Capture:
    beats: list[Beat] = field(default_factory=list)


# ────────────────────────── Geometry ──────────────────────────

def _union(*boxes: dict) -> Rect:
    x0 = min(b["x"] for b in boxes)
    y0 = min(b["y"] for b in boxes)
    x1 = max(b["x"] + b["width"] for b in boxes)
    y1 = max(b["y"] + b["height"] for b in boxes)
    return (x0, y0, x1 - x0, y1 - y0)


def _rect(r: Rect) -> dict:
    return {"x": r[0], "y": r[1], "width": r[2], "height": r[3]}


def _center(box: dict) -> tuple[float, float]:
    return (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def clip(r: Rect) -> Rect:
    """`r` cut to the viewport (tall elements extend past it)."""
    x0, y0 = max(r[0], 0.0), max(r[1], 0.0)
    x1, y1 = min(r[0] + r[2], VIEW[0]), min(r[1] + r[3], VIEW[1])
    return (x0, y0, max(1.0, x1 - x0), max(1.0, y1 - y0))


def fit(rect: Rect, aspect: float, pad: float, min_w: float) -> Rect:
    """Pad `rect`, grow it to `aspect` (w/h) and at least `min_w`, keep it on screen."""
    x, y, w, h = rect
    x, y, w, h = x - pad, y - pad, w + 2 * pad, h + 2 * pad
    cx, cy = x + w / 2, y + h / 2
    w = max(w, h * aspect, min_w)
    h = w / aspect
    if w > VIEW[0]:
        w, h = VIEW[0], VIEW[0] / aspect
    if h > VIEW[1]:
        h, w = VIEW[1], VIEW[1] * aspect
    x = min(max(cx - w / 2, 0), VIEW[0] - w)
    y = min(max(cy - h / 2, 0), VIEW[1] - h)
    return (x, y, w, h)


# ────────────────────────── Web capture ──────────────────────────

# The bordered card around a paper row: the nearest ancestor with a border.
_CARD_JS = """row => { let e = row; while (e && getComputedStyle(e).borderTopWidth === '0px') e = e.parentElement;
  const r = e.getBoundingClientRect(); return {x: r.x, y: r.y, width: r.width, height: r.height}; }"""


class _FakeZotero(BaseHTTPRequestHandler):
    """Stands in for Zotero 10's local API (the calls zotero_bridge makes), so a
    running Zotero's real library never shows and a demo save changes nothing."""

    COLLECTIONS = [{"key": f"DEMO{i}", "data": {"name": n}}
                   for i, n in enumerate(["Reading list", "Chern insulators", "Group meeting"])]

    def _reply(self, status: int, body) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Zotero-Server-ID", "demo")  # marks a writable Zotero 10+
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        path = self.path.split("?")[0]
        if path == "/api/users/0/collections":
            self._reply(200, self.COLLECTIONS)
        elif path == "/api/users/0/items":  # duplicate check: nothing saved yet
            self._reply(200, [])
        elif path in ("/api", "/api/"):
            self._reply(200, {})
        else:
            self._reply(404, {})

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path == "/api/local/authorize":
            self._reply(200, {"key": "demo"})
        elif self.path == "/api/users/0/items":
            self._reply(200, [{"key": "DEMOITEM"}])
        else:
            self._reply(404, {})

    def log_message(self, *args) -> None:
        pass


def _prepare_app(out: Path) -> Path:
    """A copy of the app with the demo config and the stand-in Zotero."""
    app = out / "app"
    app.mkdir(parents=True, exist_ok=True)
    for src in ROOT.glob("*.py"):
        shutil.copy2(src, app)
    demo_config().dump(app / "arxiv_config.json")
    bridge = app / "zotero_bridge.py"
    text = bridge.read_text()
    assert 'ZOTERO_LOCAL_BASE = "http://localhost:23119/api"' in text, "zotero_bridge changed; update the demo"
    bridge.write_text(text.replace("localhost:23119", f"127.0.0.1:{ZOTERO_PORT}"))
    # Fresh state each run except the fetch cache (it spares arXiv's rate limit).
    state = DEMO_HOME / ".arxiv_scraper"
    if state.exists():
        for p in state.iterdir():
            if p.name != "cache":
                shutil.rmtree(p) if p.is_dir() else p.unlink()
    DEMO_HOME.mkdir(exist_ok=True)
    return app


def capture(out: Path) -> Capture:
    from playwright.sync_api import sync_playwright

    app = _prepare_app(out)
    zotero = ThreadingHTTPServer(("127.0.0.1", ZOTERO_PORT), _FakeZotero)
    threading.Thread(target=zotero.serve_forever, daemon=True).start()
    env = {k: v for k, v in os.environ.items() if not k.startswith("ARXIV_DIGEST_")}  # never sync
    server = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(app / "arxiv_gui.py"),
         "--server.headless", "true", "--server.port", str(PORT),
         "--theme.base", "dark", "--client.toolbarMode", "viewer"],
        env={**env, "HOME": str(DEMO_HOME)}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    cap = Capture()
    n = 0
    try:
        time.sleep(4)
        with sync_playwright() as p:
            # Real Chrome: unlike Chromium's headless shell it shows PDFs in its viewer.
            browser = p.chromium.launch(channel="chrome")
            ctx = browser.new_context(viewport={"width": VIEW[0], "height": VIEW[1]}, device_scale_factor=SCALE,
                                      color_scheme="dark", accept_downloads=True)
            page = ctx.new_page()

            def settle(ms: int = 700) -> None:
                try:
                    page.wait_for_function(
                        "() => !document.querySelector('[data-stale=\"true\"]')"
                        " && !document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout=60_000)
                except Exception:  # noqa: BLE001 - a slow rerun just means a longer wait
                    pass
                page.wait_for_timeout(ms)

            def snap(target_page=None, wait: bool = True) -> str:
                nonlocal n
                if wait:
                    settle()
                n += 1
                name = f"{n:02d}.png"
                (target_page or page).screenshot(path=out / name)
                return name

            def in_view(locator) -> None:
                """Centre `locator` if it is cut off or under Streamlit's top bar."""
                locator.evaluate("e => { const r = e.getBoundingClientRect();"
                                 " if (r.top < 70 || r.bottom > innerHeight - 16) e.scrollIntoView({block: 'center'}); }")

            def bb(locator) -> dict:
                b = locator.bounding_box()
                assert b, f"not visible: {locator}"
                return b

            def card(i: int = 0) -> dict:
                return page.locator("[class*='st-key-paper_row_']").nth(i).evaluate(_CARD_JS)

            def details(scope, title: str):
                """The open body of the expander titled `title`."""
                return (scope.locator("[data-testid='stExpander']").filter(has_text=title).first
                        .locator("[data-testid='stExpanderDetails']"))

            def panel() -> Rect:
                return clip(_union(page.locator("[role='tabpanel']").filter(visible=True).first.bounding_box()))

            def beat(chapter: int, features: list[str], caption: str, target, focus_fn=None, action=None,
                     click: bool = True, sub: bool = False, expect=None) -> None:
                """One action: `target` is scrolled into view, screenshot, clicked (or hovered),
                `action` runs, then `focus_fn` measures the result and the result is screenshot.

                `expect` wraps the click (a download or a new tab); `action(extra, value)` gets
                the waited-for value and can record typing frames (`extra["steps"]`) or the
                screenshot of another tab with its focus (`extra["after"]`, `extra["focus"]`)."""
                in_view(target)
                page.mouse.move(VIEW[0] - 8, VIEW[1] - 8)  # a previous hover's tooltip fades as the cursor leaves
                before = snap()
                tb = bb(target)
                centred_label = target.evaluate("e => e.tagName === 'BUTTON'")
                extra = {"steps": [], "after": None, "focus": None}
                value = None
                if expect:
                    with expect() as info:
                        target.click()
                    value = info.value
                elif click:
                    target.click()
                else:
                    target.hover()
                if action:
                    try:
                        action(extra, value)
                    except Exception:
                        page.screenshot(path=out / "debug-failed-beat.png")
                        raise
                if click:  # park the real mouse so its hover can't pop up a stray tooltip
                    page.mouse.move(VIEW[0] - 8, VIEW[1] - 8)
                if extra["after"]:
                    after, focus = extra["after"], extra["focus"]
                else:
                    settle()
                    try:
                        focus = focus_fn()
                    except Exception:
                        page.screenshot(path=out / "debug-failed-beat.png")
                        raise
                    after = snap()
                # Wide rows (dropdown options, inputs) are clicked near their text, as a person would;
                # buttons centre their label.
                wide = tb["width"] >= 400 and not centred_label
                point = (tb["x"] + 110, tb["y"] + tb["height"] / 2) if wide else _center(tb)
                cap.beats.append(Beat(caption, before, point, after, clip(focus), click,
                                      (tb["x"], tb["y"], tb["width"], tb["height"]), features, chapter,
                                      extra["steps"], bool(extra["after"]), sub))

            def type_into(text: str):
                def run(extra, _value) -> None:
                    for ch in text:
                        page.keyboard.type(ch)
                        page.wait_for_timeout(60)
                        extra["steps"].append(snap(wait=False))
                    page.keyboard.press("Enter")
                return run

            page.goto(f"http://localhost:{PORT}")
            fetch = page.get_by_role("button", name="Fetch papers")
            fetch.wait_for()
            page.add_style_tag(content="[data-testid='stToast']{display:none}")
            sidebar = page.locator("[data-testid='stSidebar']")
            popover = page.locator("[data-testid='stPopoverBody']").filter(visible=True)
            rows = page.locator("[class*='st-key-paper_row_']")
            first_title = rows.first.locator(".paper-title")

            # ── Chapter 1: Read ──
            why = page.get_by_text("Why this score?").first
            beat(0, ["fetch", "rank"], "Fetch the past week from the categories you follow", fetch,
                 lambda: _union(card(0)), lambda e, v: why.wait_for(timeout=180_000))
            if "(" in page.locator(".paper-subjects").first.inner_text():
                shutil.rmtree(DEMO_HOME / ".arxiv_scraper" / "cache", ignore_errors=True)
                raise SystemExit("arXiv's export API is rate-limiting (the GUI fell back to the HTML "
                                 "listing). Wait a few minutes and run again.")
            # Hero: the top card as it first appears, fully in view.
            rows.first.evaluate("e => e.scrollIntoView({block: 'center'})")
            settle(400)
            page.screenshot(path=out / "hero.png", clip=card(0))
            top_link = page.locator("a[href*='arxiv.org/abs/']").first.get_attribute("href") or ""
            top_id = top_link.rstrip("/").rsplit("/", 1)[-1]  # typed into Score a paper later
            assert re.fullmatch(r"\d{4}\.\d{4,5}(v\d+)?", top_id), f"unexpected arXiv link {top_link!r}"
            (out / "top_link.txt").write_text(top_link)

            # Hover a title keyword, an author and an abstract keyword: each shows its bonus.
            hl_caption = "Your keywords and authors, highlighted"
            for feats, hl in ((["highlight"], first_title.locator(".hl-term").first),
                              ([], rows.first.locator(".paper-authors .hl-author").first),
                              ([], rows.first.locator(".hl-term:not(.paper-title *)").first)):
                beat(0, feats, hl_caption, hl,
                     lambda hl=hl: _union(bb(hl), bb(hl.locator(".hl-tip")), bb(first_title)), click=False)
            beat(0, ["why"], "Every score explained", why,
                 lambda: _union(bb(details(page, "Why this score?")), bb(why)))

            day_select = (page.locator("[data-testid='stSelectbox']").filter(has=page.get_by_text("Day", exact=True))
                          .first.locator("[data-baseweb='select']"))
            day = rows.first.get_by_text(re.compile(r"^Section: ")).first.inner_text().removeprefix("Section: ").strip()
            day_option = page.get_by_role("option", name=day, exact=True)
            beat(0, ["day"], "Show a single day", day_select,
                 lambda: _union(bb(day_select), bb(day_option)), lambda e, v: day_option.wait_for(), sub=True)
            beat(0, [], "Show a single day", day_option,
                 lambda: _union(bb(day_select), bb(first_title)))
            search = page.get_by_label("Search title / authors / abstract")
            beat(0, ["search"], "Search titles, authors and abstracts", search,
                 lambda: _union(bb(search), bb(first_title)), type_into("chern"))

            def show_download(extra, download) -> None:
                md = out / download.suggested_filename
                download.save_as(md)
                tab = ctx.new_page()
                tab.goto(md.as_uri())
                tab.wait_for_timeout(600)
                extra["after"] = snap(tab, wait=False)
                extra["focus"] = (0.0, 0.0, 860.0, 538.0)  # the file's first lines, large enough to read
                tab.close()

            markdown = page.get_by_role("button", name="Markdown", exact=True)
            beat(0, ["export"], "Export the list as Markdown or JSON", markdown,
                 action=show_download, expect=page.expect_download)

            zotero_btn = rows.first.get_by_role("button", name="Save to Zotero", exact=True)
            collection = popover.locator("[data-baseweb='select']")
            chern_option = page.get_by_role("option", name="Chern insulators", exact=True)
            beat(0, ["zotero"], "Save to Zotero, into any collection", zotero_btn,
                 lambda: _union(bb(popover), bb(zotero_btn)), lambda e, v: popover.wait_for(), sub=True)
            beat(0, [], "Save to Zotero, into any collection", collection,
                 lambda: _union(bb(popover), bb(chern_option)), lambda e, v: chern_option.wait_for(), sub=True)
            beat(0, [], "Save to Zotero, into any collection", chern_option,
                 lambda: _union(bb(popover)), sub=True)
            saved = rows.first.get_by_text("Saved ✓")
            beat(0, [], "Save to Zotero, into any collection", popover.get_by_role("button", name="Save", exact=True),
                 lambda: _union(bb(saved), bb(rows.first.locator("[class*='st-key-paper_side_']"))),
                 lambda e, v: saved.wait_for(timeout=90_000))

            def show_pdf(extra, tab) -> None:
                tab.wait_for_load_state()
                tab.wait_for_timeout(4500)  # Chrome's PDF viewer renders the first page
                extra["after"] = snap(tab, wait=False)
                extra["focus"] = (440.0, 56.0, 860.0, 520.0)  # the first page's title block in Chrome's viewer
                tab.close()

            pdf = rows.first.get_by_role("link", name=re.compile("Open PDF"))
            beat(0, ["pdf"], "Open the PDF", pdf, action=show_pdf, expect=ctx.expect_page)

            # ── Chapter 2: Curate ──
            add = rows.first.get_by_role("button", name="Add author", exact=True)
            beat(1, ["author"], "Follow an author in one click", add,
                 lambda: _union(bb(popover), bb(add)), lambda e, v: popover.wait_for(), sub=True)
            unsaved = page.locator(".st-key-unsaved_box")
            beat(1, ["unsaved"], "Scores update at once; the change stays unsaved", popover.locator("button").first,
                 lambda: _union(bb(unsaved), bb(rows.first.locator(".paper-authors"))),
                 lambda e, v: unsaved.wait_for())
            beat(1, [], "Keep it with one click, or Discard", unsaved.locator("button").last,
                 lambda: _union(card(0)), lambda e, v: unsaved.wait_for(state="detached"))
            removed_title = first_title.inner_text()
            remove = rows.first.locator("[class*='st-key-remove_'] button").first  # the icon's text is in its name
            removed = page.locator("[data-testid='stExpander']").filter(has_text="Removed papers (1)").first
            beat(1, ["remove"], "Remove what you've read; the next paper moves up", remove,
                 lambda: _union(bb(removed), bb(first_title)),
                 lambda e, v: page.wait_for_function(
                     "t => document.querySelector('.paper-title')?.innerText !== t", arg=removed_title))
            restore = page.locator("[class*='st-key-restore_']:not(.st-key-restore_all) button").first
            beat(1, [], "Restore it any time", removed.locator("summary"),
                 lambda: _union(bb(removed)), lambda e, v: restore.wait_for(), sub=True)
            beat(1, [], "Restore it any time", restore,
                 lambda: _union(bb(first_title)),
                 lambda e, v: page.get_by_text("Removed papers (1)").wait_for(state="detached"))

            score_tab = page.get_by_role("tab", name="Score a paper")
            link_box = page.get_by_label("arXiv link or ID")
            score_btn = page.get_by_role("button", name="Score this paper")
            verdict = page.get_by_text("Why it did / didn't appear in the digest", exact=True)
            verdict_box = page.locator("[data-testid='stAlert']").filter(visible=True).first
            # The tab's own "Score a paper" subheader is the first h3; the paper's title is the second.
            paper_h3 = page.locator("[role='tabpanel']").filter(visible=True).locator("h3").nth(1)
            beat(1, ["score"], "Score any arXiv link and see why it is or isn't listed", score_tab,
                 lambda: _union(bb(link_box), bb(score_tab)), sub=True)
            beat(1, [], "Score any arXiv link and see why it is or isn't listed", link_box,
                 lambda: _union(bb(link_box), bb(score_btn)), type_into(top_id))

            def scored(extra, _value) -> None:
                """Score a paper asks the export API; retry if arXiv rate-limits, then show the verdict."""
                for _ in range(4):
                    page.get_by_text("Failed to fetch paper").or_(verdict).first.wait_for(timeout=90_000)
                    if verdict.is_visible():
                        settle()
                        verdict_box.evaluate("e => { e.style.scrollMarginBottom = '24px';"
                                             " e.scrollIntoView({block: 'end'}); }")
                        return
                    page.wait_for_timeout(20_000)
                    score_btn.click()
                raise SystemExit("arXiv kept rate-limiting Score a paper; run again later.")

            beat(1, [], "Score any arXiv link and see why it is or isn't listed", score_btn,
                 lambda: _union(bb(paper_h3), bb(verdict_box)), scored)

            # ── Chapter 3: Tune and sync ──
            for tab, feats, caption in (
                ("Keywords", ["lists"], "Edit keywords, authors and low-priority terms"),
                ("Scoring", ["weights"], "Tune weights and per-category bonuses"),
                ("Profiles", ["presets"], "Start from a preset, save profiles"),
            ):
                beat(2, feats, caption, page.get_by_role("tab", name=tab), panel)
            json_title = page.get_by_text("Copy working config (JSON)")
            json_body = details(page, "Copy working config (JSON)")
            beat(2, ["json"], "Copy or download your config as JSON", json_title,
                 lambda: _union(bb(json_title), bb(json_body),
                                bb(page.get_by_role("button", name="Download working config (JSON)"))),
                 lambda e, v: json_body.wait_for())
            sync = sidebar.get_by_text("Sync with server")
            sync_body = details(sidebar, "Sync with server")
            beat(2, ["sync"], "Sync your settings with the iPhone app", sync,
                 lambda: _union(bb(sync_body), bb(sync)), lambda e, v: sync_body.wait_for())
            swatch = sidebar.locator("[data-testid='stColorPicker']").first
            picker = page.locator("[data-baseweb='popover']").filter(visible=True).last
            beat(2, ["display"], "Choose your highlight colors", swatch.locator("[data-testid='stColorPickerBlock']"),
                 lambda: _union(bb(swatch), bb(picker)), lambda e, v: picker.wait_for())
    finally:
        server.terminate()
        zotero.shutdown()
    shown = [f for b in cap.beats for f in b.features]
    assert shown == list(WEB_FEATURES), f"beats and WEB_FEATURES disagree: {shown}"
    (out / "capture.json").write_text(json.dumps(asdict(cap), indent=1))
    return cap


# ────────────────────────── Drawing helpers ──────────────────────────

def font(size: int, bold: bool = False):
    try:
        f = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", size)
        f.set_variation_by_name("Bold" if bold else "Regular")
        return f
    except Exception:  # noqa: BLE001 - not macOS: fall back to Pillow's font
        return ImageFont.load_default(size)


def ease(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return 4 * t ** 3 if t < .5 else 1 - (-2 * t + 2) ** 3 / 2


def lerp(a, b, t):
    if isinstance(a, (tuple, list)):
        return tuple(lerp(x, y, t) for x, y in zip(a, b))
    return a + (b - a) * t


def rounded(img: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius, fill=255)
    out = Image.new("RGBA", img.size)
    out.paste(img, (0, 0), mask)
    return out


def shadow(size: tuple[int, int], radius: int, blur: int, alpha: int = 150) -> Image.Image:
    pad = blur * 3
    sh = Image.new("RGBA", (size[0] + 2 * pad, size[1] + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((pad, pad + blur // 2, pad + size[0], pad + size[1] + blur // 2),
                                         radius, fill=(0, 0, 0, alpha))
    return sh.filter(ImageFilter.GaussianBlur(blur))


def gradient(size: tuple[int, int], top: tuple, bottom: tuple) -> Image.Image:
    g = Image.linear_gradient("L").resize(size)
    return Image.composite(Image.new("RGB", size, bottom), Image.new("RGB", size, top), g)


_CURSOR = [(0, 0), (0, 17), (4.5, 13), (7.5, 20), (10, 19), (7, 12.5), (12.5, 12.5)]


def draw_cursor(canvas: Image.Image, pos: tuple[float, float], scale: float, ripple: float | None) -> None:
    d = ImageDraw.Draw(canvas, "RGBA")
    x, y = pos
    if ripple is not None:
        r = (8 + 26 * ripple) * scale
        d.ellipse((x - r, y - r, x + r, y + r), outline=(255, 255, 255, int(220 * (1 - ripple))),
                  width=max(2, int(3 * scale)))
    pts = [(x + px * scale * 1.4, y + py * scale * 1.4) for px, py in _CURSOR]
    d.polygon(pts, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=max(1, int(1.5 * scale)))


def wrapped(d: ImageDraw.ImageDraw, text: str, f, x: float, y: float, max_w: float, line_h: float,
            fill, center: bool = False) -> None:
    """`text` broken into lines no wider than `max_w`; `x` is the centre when `center`."""
    lines, line = [], ""
    for word in text.split():
        if line and d.textlength(f"{line} {word}", font=f) > max_w:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    lines.append(line)
    for k, ln in enumerate(lines):
        d.text((x - d.textlength(ln, font=f) / 2 if center else x, y + k * line_h), ln, font=f, fill=fill)


def caption_pill(canvas: Image.Image, text: str, center_x: int, y: int, size: int, alpha: float) -> None:
    if alpha <= 0 or not text:
        return
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f = font(size, bold=True)
    w = d.textlength(text, font=f)
    px, py = size * .9, size * .55
    box = (center_x - w / 2 - px, y, center_x + w / 2 + px, y + size + 2 * py)
    d.rounded_rectangle(box, radius=int((size + 2 * py) / 2), fill=(20, 22, 30, int(215 * alpha)),
                        outline=(255, 255, 255, int(40 * alpha)), width=1)
    d.text((center_x - w / 2, y + py - size * .08), text, font=f, fill=(255, 255, 255, int(255 * alpha)))
    canvas.alpha_composite(layer)


def checklist(canvas: Image.Image, origin: tuple[int, int], items: list[str], ticked: int,
              current: set[int], size: int, step: int, width: int) -> None:
    """Feature list: the first `ticked` items ticked, `current` highlighted, the rest muted."""
    d = ImageDraw.Draw(canvas, "RGBA")
    x, y = origin
    regular, bold = font(size), font(size, True)
    r = size * .42
    for i, label in enumerate(items):
        top = y + i * step
        if i in current:
            d.rounded_rectangle((x - 10, top - 5, x + width, top + step - 7), radius=8, fill=INDIGO + (255,))
        cx, cy = x + r, top + size * .62
        if i < ticked:
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=GREEN + (255,))
            d.line([(cx - r * .5, cy), (cx - r * .1, cy + r * .45), (cx + r * .55, cy - r * .45)],
                   fill=BG + (255,), width=max(2, size // 9))
        else:
            d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=MUTED + (255,), width=2)
        d.text((x + 2 * r + 12, top), label, font=bold if i in current else regular,
               fill=(255, 255, 255) if i < ticked else MUTED)


def tick_state(feature_lists: list[list[str]], step: int) -> tuple[int, set[int]]:
    """(items ticked, items highlighted) while showing step `step` of a tour whose
    steps show `feature_lists` in checklist order (-1 intro, len() outro)."""
    if step < 0:
        return 0, set()
    if step >= len(feature_lists):
        return sum(map(len, feature_lists)), set()
    done = sum(len(f) for f in feature_lists[:step])
    now = len(feature_lists[step])
    return done + now, set(range(done, done + now)) if now else {done - 1}


def ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def encode(frames, size: tuple[int, int], mp4: Path, gif: Path, gif_width: int, gif_fps: int = 12) -> None:
    """RGB frames → H.264 MP4, then a palette-optimised GIF from it."""
    proc = subprocess.Popen(
        [ffmpeg(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{size[0]}x{size[1]}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", "-movflags", "+faststart", str(mp4)],
        stdin=subprocess.PIPE)
    assert proc.stdin
    for f in frames:
        proc.stdin.write(f.tobytes())
    proc.stdin.close()
    proc.wait()
    while True:  # narrower until the GIF fits GitHub's 10 MB limit
        subprocess.run(
            [ffmpeg(), "-y", "-loglevel", "error", "-i", str(mp4), "-vf",
             f"fps={gif_fps},scale={gif_width}:-1:flags=lanczos,split[a][b];"
             "[a]palettegen=max_colors=128:stats_mode=diff[p];"
             "[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle", str(gif)], check=True)
        if gif.stat().st_size < 9.5 * 2**20:
            break
        gif_width = round(gif_width * .92 / 2) * 2
    print(f"{gif.name}: {gif.stat().st_size // 1024} KiB ({gif_width} px), {mp4.name}: {mp4.stat().st_size // 1024} KiB")


# ────────────────────────── Web tour ──────────────────────────

@dataclass
class Frame:
    a: str  # screenshot
    b: str | None  # crossfade target
    mix: float
    cam: Rect
    cursor: tuple[float, float] | None  # None: no cursor (another tab is shown)
    ripple: float | None
    caption: str
    caption_alpha: float
    beat: int  # -1 intro, len(beats) outro
    card: int | None = None  # chapter title card
    card_alpha: float = 0.0
    cam_b: Rect | None = None  # the crossfade target's camera, when it differs (another tab)


FULL: Rect = (0.0, 0.0, float(VIEW[0]), float(VIEW[1]))


def glide(a: Rect, b: Rect, t: float, aspect: float) -> Rect:
    """Camera path a → b that pulls back just enough to keep both in shot
    (a quadratic Bézier through the smallest frame holding both)."""
    mid = fit(_union(_rect(a), _rect(b)), aspect, 0, 0)
    e = ease(t)
    return lerp(lerp(a, mid, e), lerp(mid, b, e), e)


def _close(a: Rect, b: Rect) -> bool:
    return all(abs(x - y) < 8 for x, y in zip(a, b))


# Web-tour pacing in seconds: intro, camera move, typing per character, hold on a result
# (sub step / normal), other-tab hold, outro zoom-out / final hold.
PACE = dict(intro=.4, move=.7, type=.05, sub=.45, hold=.65, tab=1.0, zoom=.7, end=.6)


def timeline(cap: Capture, aspect: float, chapter_cards: bool = False) -> list[Frame]:
    """An establishing shot, then per beat one camera move that frames the clicked
    element together with its result, while the cursor travels there; click,
    result, hold. Another tab (PDF, downloaded file) is cut to and back."""
    frames: list[Frame] = []
    beats, end = cap.beats, len(cap.beats)
    cam, cursor, shown, caption = FULL, (VIEW[0] * .55, VIEW[1] * .5), beats[0].before, ""

    def run(seconds: float, fn) -> None:
        k = max(1, round(seconds * FPS))
        frames.extend(fn((i + 1) / k) for i in range(k))

    run(PACE["intro"], lambda _: Frame(shown, None, 0, FULL, cursor, None, "", 0, -1))
    chapter = None
    for i, bt in enumerate(beats):
        if chapter_cards and bt.chapter != chapter:
            run(1.4, lambda t: Frame(shown, None, 0, cam, None, None, "", 0, i - 1, bt.chapter,
                                     min(1.0, t / .2, (1 - t) / .2)))
        chapter = bt.chapter
        rects = [bt.target_box] if bt.new_tab else [bt.target_box, bt.focus]
        shot = fit(clip(_union(*map(_rect, rects))), aspect, 60, 1050)
        start_cam, start_cur, prev = cam, cursor or bt.target, shown
        new_cap = bt.caption != caption
        run(PACE["move"], lambda t: Frame(prev, bt.before, ease(t * 4) if prev != bt.before else 0,
                                 glide(start_cam, shot, t, aspect) if not _close(start_cam, shot) else shot,
                                 lerp(start_cur, bt.target, ease(t)), None, bt.caption,
                                 ease(t * 2) if new_cap else 1, i))
        cursor, caption = bt.target, bt.caption
        run(.22, lambda t: Frame(bt.before, None, 0, shot, cursor, t if bt.click else None, bt.caption, 1, i))
        last = bt.before
        for s in bt.steps:  # typing, one frame per character
            run(PACE["type"], lambda _, s=s: Frame(s, None, 0, shot, cursor, None, bt.caption, 1, i))
            last = s
        if bt.new_tab:  # cut to the other tab, framed on its content, then back to the app
            tab_cam = fit(clip(bt.focus), aspect, 40, 960)
            back = beats[i + 1].before if i + 1 < end else last
            run(.3, lambda t: Frame(last, bt.after, ease(t), shot, None, None, bt.caption, 1, i, cam_b=tab_cam))
            run(PACE["tab"], lambda _: Frame(bt.after, None, 0, tab_cam, None, None, bt.caption, 1, i))
            run(.3, lambda t: Frame(bt.after, back, ease(t), tab_cam, None, None, bt.caption, 1, i, cam_b=shot))
            shown = back
        else:
            run(.12, lambda t: Frame(last, bt.after, ease(t), shot, cursor, None, bt.caption, 1, i))
            run(PACE["sub"] if bt.sub else PACE["hold"], lambda _: Frame(bt.after, None, 0, shot, cursor, None, bt.caption, 1, i))
            shown = bt.after
        cam = shot
    run(PACE["zoom"], lambda t: Frame(shown, None, 0, lerp(cam, FULL, ease(t)), cursor, None, caption, 1 - t, end))
    run(PACE["end"], lambda _: Frame(shown, None, 0, FULL, cursor, None, "", 0, end))
    return frames


class Shots(dict):
    def __init__(self, folder: Path):
        super().__init__()
        self.folder = folder

    def __missing__(self, name: str) -> Image.Image:
        self[name] = Image.open(self.folder / name).convert("RGB")
        return self[name]


def _crop(shots: Shots, name: str, cam: Rect, size: tuple[int, int]) -> Image.Image:
    x, y, w, h = cam
    box = tuple(round(v * SCALE) for v in (x, y, x + w, y + h))
    return shots[name].crop(box).resize(size, Image.Resampling.LANCZOS)


def app_view(shots: Shots, f: Frame, size: tuple[int, int]) -> Image.Image:
    """The camera's crop of the app at `size`, with the cursor."""
    img = _crop(shots, f.a, f.cam, size)
    if f.b and f.mix > 0:
        img = Image.blend(img, _crop(shots, f.b, f.cam_b or f.cam, size), f.mix)
    img = img.convert("RGBA")
    if f.cursor and not (f.cam_b and f.mix > .5):
        x, y, w, _ = f.cam
        s = size[0] / w
        draw_cursor(img, ((f.cursor[0] - x) * s, (f.cursor[1] - y) * s), max(1.0, s * .9), f.ripple)
    return img


def web_cinematic(cap: Capture, shots: Shots):
    """Edge to edge, the camera follows the cursor, a caption pill at the bottom."""
    size = (1280, 800)

    def compose(f: Frame) -> Image.Image:
        img = app_view(shots, f, size)
        caption_pill(img, f.caption, size[0] // 2, size[1] - 80, 24, f.caption_alpha)
        return img.convert("RGB")

    return size, size[0] / size[1], False, compose, 600


def web_chapters(cap: Capture, shots: Shots):
    """The app in a window on a gradient; chapter title cards, caption and a chapter progress bar."""
    size, win = (1280, 800), (1088, 680)
    wx, wy = (size[0] - win[0]) // 2, 22
    bg = gradient(size, INDIGO, NAVY).convert("RGBA")
    sh = shadow(win, 14, 18)
    starts = [next(i for i, b in enumerate(cap.beats) if b.chapter == c) for c in range(len(CHAPTERS))]

    def compose(f: Frame) -> Image.Image:
        canvas = bg.copy()
        canvas.alpha_composite(sh, (wx - 54, wy - 54))
        canvas.alpha_composite(rounded(app_view(shots, f, win), 12), (wx, wy))
        d = ImageDraw.Draw(canvas, "RGBA")
        d.text((wx, wy + win[1] + 12), f.caption, font=font(24, True),
               fill=(255, 255, 255, int(255 * f.caption_alpha)))
        # Chapter progress: one segment per chapter, filled as its beats pass.
        seg_w, gap, y = (win[0] - 2 * 16) / 3, 16, size[1] - 26
        for c, name in enumerate(CHAPTERS):
            x0 = wx + c * (seg_w + gap)
            end = starts[c + 1] if c + 1 < len(starts) else len(cap.beats)
            frac = min(max((f.beat + 1 - starts[c]) / (end - starts[c]), 0), 1)
            d.rounded_rectangle((x0, y, x0 + seg_w, y + 6), radius=3, fill=(255, 255, 255, 50))
            if frac > 0:
                d.rounded_rectangle((x0, y, x0 + seg_w * frac, y + 6), radius=3, fill=ACCENT + (255,))
            d.text((x0 + seg_w - d.textlength(name, font=font(16)), y - 24), name, font=font(16),
                   fill=(255, 255, 255, 220 if frac > 0 else 110))
        if f.card is not None and f.card_alpha > 0:
            overlay = gradient(size, INDIGO, NAVY).convert("RGBA")
            o = ImageDraw.Draw(overlay)
            o.text((120, 230), f"{f.card + 1}", font=font(120, True), fill=ACCENT)
            o.text((230, 250), CHAPTERS[f.card], font=font(84, True), fill=(255, 255, 255))
            feats = [WEB_FEATURES[k] for b in cap.beats if b.chapter == f.card for k in b.features]
            per_col = -(-len(feats) // 2)  # two balanced columns
            for j, label in enumerate(feats):
                o.text((236 + (j // per_col) * 460, 380 + (j % per_col) * 46), "·  " + label,
                       font=font(28), fill=(226, 232, 240))
            overlay.putalpha(int(255 * f.card_alpha))
            canvas.alpha_composite(overlay)
        return canvas.convert("RGB")

    return size, win[0] / win[1], True, compose, 640


def web_checklist(cap: Capture, shots: Shots):
    """The feature list on the left ticks off as the app on the right shows each one."""
    size, view_size = (1280, 720), (820, 512)
    vx, vy = 420, 70
    base = Image.new("RGBA", size, NAVY + (255,))
    b = ImageDraw.Draw(base)
    b.rectangle((0, 0, 392, size[1]), fill=(11, 16, 32))
    b.text((36, 34), "arXiv Digest", font=font(34, True), fill=(255, 255, 255))
    b.text((36, 80), "Web app · iPhone app · CLI", font=font(18), fill=ACCENT)
    b.text((36, size[1] - 40), "github.com/isaac-tes/arxiv-digest", font=font(16), fill=MUTED)
    base.alpha_composite(shadow(view_size, 12, 18), (vx - 54, vy - 54))
    items = list(WEB_FEATURES.values())
    feature_lists = [b.features for b in cap.beats]

    def compose(f: Frame) -> Image.Image:
        canvas = base.copy()
        checklist(canvas, (40, 128), items, *tick_state(feature_lists, f.beat), 21, 28, 330)
        canvas.alpha_composite(rounded(app_view(shots, f, view_size), 12), (vx, vy))
        caption_pill(canvas, f.caption, vx + view_size[0] // 2, vy + view_size[1] + 30, 22, f.caption_alpha)
        return canvas.convert("RGB")

    return size, view_size[0] / view_size[1], False, compose, 800


WEB_DESIGNS = {"cinematic": web_cinematic, "chapters": web_chapters, "checklist": web_checklist}


def render_web(cap: Capture, work: Path, name: str, mp4: Path, gif: Path) -> None:
    shots = Shots(work)
    size, aspect, cards, compose, gif_width = WEB_DESIGNS[name](cap, shots)
    encode((compose(f) for f in timeline(cap, aspect, cards)), size, mp4, gif, gif_width, gif_fps=8)


def render_hero(work: Path, out: Path) -> None:
    """Name and tagline over a gradient, the hero card floating below."""
    card = Image.open(work / "hero.png").convert("RGBA")
    w, title_h = card.width + 240, 330
    img = gradient((w, title_h + card.height + 120), INDIGO, NAVY).convert("RGBA")
    d = ImageDraw.Draw(img)
    for text, f, y, col in (("arXiv Digest", font(104, True), 60, (255, 255, 255)),
                            ("Your arXiv, ranked by rules you control", font(46), 190, (226, 232, 240)),
                            ("Web app  ·  iPhone app  ·  CLI    —    free and open source", font(34), 262,
                             ACCENT)):
        d.text(((w - d.textlength(text, font=f)) / 2, y), text, font=f, fill=col)
    img.alpha_composite(shadow(card.size, 18, 30, 170), (120 - 90, title_h - 90))
    img.alpha_composite(rounded(card, 18), (120, title_h))
    img = img.convert("RGB")
    img.resize((1600, round(img.height * 1600 / img.width)), Image.Resampling.LANCZOS).save(out, optimize=True)
    print(f"{out.name}: {out.stat().st_size // 1024} KiB")


def render_social(work: Path, out: Path) -> None:
    """GitHub's social preview (1280×640, under 1 MB): name and tagline, the hero card below."""
    w, h = 1280, 640
    img = gradient((w, h), INDIGO, NAVY).convert("RGBA")
    d = ImageDraw.Draw(img)
    for text, f, y, col in (("arXiv Digest", font(72, True), 44, (255, 255, 255)),
                            ("Your arXiv, ranked by rules you control", font(34), 134, (226, 232, 240)),
                            ("Web app  ·  iPhone app  ·  CLI", font(26), 186, ACCENT)):
        d.text(((w - d.textlength(text, font=f)) / 2, y), text, font=f, fill=col)
    card = Image.open(work / "hero.png").convert("RGBA")
    cw = 1080
    card = card.resize((cw, round(card.height * cw / card.width)), Image.Resampling.LANCZOS)
    x, y = (w - cw) // 2, 248
    img.alpha_composite(shadow(card.size, 14, 24, 170), (x - 72, y - 72))
    img.alpha_composite(rounded(card, 14), (x, y))  # runs off the bottom edge: a glimpse is enough
    img.convert("RGB").save(out, optimize=True)
    print(f"{out.name}: {out.stat().st_size // 1024} KiB")
    assert out.stat().st_size < 2**20, "GitHub's social preview must be under 1 MB"


# ────────────────────────── iOS ──────────────────────────
# The iPhone tour is built from simulator screenshots (one launch per screen, the
# app's launch options open each one). Vision OCR finds the elements by their
# text, so a finger can tap the real element, the screen pushes, pops or switches
# tab like the app, and the camera pans to what each screen shows (one move per step).

IOS_FEATURES = {
    "digest": "Ranked digest",
    "detail": "Highlights, PDF, Zotero",
    "remove": "Remove and restore",
    "day": "Filter by day",
    "score": "Score any arXiv link",
    "unsaved": "Unsaved changes, one Save",
    "lists": "Keywords and authors",
    "feeds": "Your arXiv categories",
    "weights": "Weights and bonuses",
    "presets": "Starter presets",
    "modes": "On its own or with a server",
    "json": "Config as JSON",
}
# Screens in capture order (it matters: -remove persists). -dirty adds an unsaved keyword.
IOS_CAPTURES = [
    ("01-papers.png", ["-tab", "papers"]),
    ("03-detail.png", ["-open-paper", "1"]),
    ("05-removed.png", ["-remove", "1"]),
    ("02-day.png", ["-day", "1"]),
    ("04-score.png", ["-tab", "score", "-score", "TOP"]),
    ("06-config.png", ["-tab", "config", "-dirty"]),
    ("07-keywords.png", ["-config-page", "keywords", "-dirty"]),
    ("08-authors.png", ["-config-page", "authors", "-dirty"]),
    ("09-feeds.png", ["-config-page", "feeds", "-dirty"]),
    ("10-scoring.png", ["-config-page", "scoring", "-dirty"]),
    ("11-presets.png", ["-config-page", "presets", "-dirty"]),
    ("12-settings.png", ["-tab", "settings", "-dirty"]),
]


@dataclass
class IOSStep:
    screen: str
    caption: str
    features: list[str]
    focus: tuple[str, int, int] | None  # (anchor text, px above, px below) to frame; None: just the tap
    action: tuple[str, str] | None  # ("push"|"pop"|"tab"|"tap"|"swipe", element text)
    hold: float  # seconds on the screen before the action: time to read it
    frame: tuple[int, int] | None = None  # a fixed camera band (screen px), shared by steps so it stays put


BACK = "‹back›"  # the navigation bar's back button (no text)
DAY = "‹first day›"  # the first day chip after "All days"
CONFIG = (0, 2130)  # one camera for the Config tab and its pages: the back button and every row
IOS_STEPS = [
    IOSStep("01-papers.png", "Your ranked digest, on your iPhone", ["digest"],
            ("Symmetric Mode", -60, 760), ("push", "Symmetric Mode"), 1.3),
    IOSStep("03-detail.png", "Highlights, PDF and Zotero on every paper", ["detail"],
            ("PDF", -650, 600), ("pop", BACK), 1.8),
    IOSStep("01-papers.png", "Swipe away what you've read", [],
            ("Symmetric Mode", -60, 760), ("swipe", "Symmetric Mode"), .4),
    IOSStep("05-removed.png", "Removed papers stay one tap from Restore", ["remove"],
            ("Removed papers", -120, 760), ("tap", DAY), 1.3),
    IOSStep("02-day.png", "Filter by day", ["day"], ("Past week", -40, 900), ("tab", "Score"), 1.2),
    IOSStep("04-score.png", "Score any arXiv link, and see why it is or isn't listed", ["score"],
            ("Why it did", -700, 420), ("tab", "Config"), 1.9),
    IOSStep("06-config.png", "Edits wait until you tap Save", ["unsaved"],
            ("Unsaved changes", -520, 260), ("push", "Keywords"), 1.4),
    IOSStep("07-keywords.png", "Your keywords, one line to add more", ["lists"],
            ("Add keywords", -60, 1000), ("pop", BACK), 1.3, CONFIG),
    IOSStep("06-config.png", "…and the authors you follow", [], None, ("push", "Authors"), .4, CONFIG),
    IOSStep("08-authors.png", "…and the authors you follow", [], ("bernevig", -260, 860), ("pop", BACK), 1.1, CONFIG),
    IOSStep("06-config.png", "Pick your arXiv categories", [], None, ("push", "Feeds"), .4, CONFIG),
    IOSStep("09-feeds.png", "Pick your arXiv categories", ["feeds"], ("Include replacement", -80, 820),
            ("pop", BACK), 1.1, CONFIG),
    IOSStep("06-config.png", "Tune every weight", [], None, ("push", "Scoring"), .4, CONFIG),
    IOSStep("10-scoring.png", "Tune every weight", ["weights"], ("Weights", -60, 900), ("pop", BACK), 1.1, CONFIG),
    IOSStep("06-config.png", "Start from a preset", [], None, ("push", "Starter presets"), .4, CONFIG),
    IOSStep("11-presets.png", "Start from a preset", ["presets"], ("Floquet Topological", -80, 900),
            ("tab", "Settings"), 1.2),
    IOSStep("12-settings.png", "On its own or with your server; config as JSON", ["modes", "json"],
            ("Connection", -60, 1350), None, 2.0),
]
BUNDLE = "com.arxivdigest.app"


def capture_ios(udid: str, out: Path) -> None:
    """Standalone mode with the demo config written into the app's store, one launch per screen."""
    out.mkdir(parents=True, exist_ok=True)

    def simctl(*args: str) -> str:
        return subprocess.run(["xcrun", "simctl", *args], check=True, capture_output=True, text=True).stdout

    data = Path(simctl("get_app_container", udid, BUNDLE, "data").strip())
    store = data / "Library" / "Application Support" / "Standalone"
    store.mkdir(parents=True, exist_ok=True)
    demo_config().dump(store / "config.json")
    for f in store.glob("removed*.json"):
        f.unlink()
    simctl("status_bar", udid, "override", "--time", "9:41", "--batteryState", "charged",
           "--batteryLevel", "100", "--cellularBars", "4", "--wifiBars", "3")
    simctl("ui", udid, "appearance", "dark")
    # "Score any arXiv link" scores this week's #1: the paper the web run scored, else rank it here
    # (the Swift scorer is parity-tested against this engine).
    saved = WORK / "top_link.txt"
    if saved.exists() and saved.read_text().strip():
        top_id = saved.read_text().strip()
    else:
        cfg = demo_config()
        end = datetime.now(UTC)
        papers = ad.filter_papers(ad.fetch_pastweek(cfg.default_feeds, end - timedelta(days=7), end),
                                  include_replacements=False)
        top_id = ad.build_ranked_entries(papers, cfg, 1)[0]["id"]
    for name, opts in IOS_CAPTURES:
        subprocess.run(["xcrun", "simctl", "terminate", udid, BUNDLE], capture_output=True)
        simctl("launch", udid, BUNDLE, "-standalone", *[top_id if o == "TOP" else o for o in opts])
        time.sleep(25)  # live fetch from arXiv's export API on the first launch
        simctl("io", udid, "screenshot", "--type=png", str(out / name))
        print("captured", name)


_OCR_SWIFT = r"""
import AppKit
import Vision
for path in CommandLine.arguments.dropFirst() {
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = false
    try? VNImageRequestHandler(cgImage: cg).perform([req])
    var out: [[String: Any]] = []
    let w = Double(cg.width), h = Double(cg.height)
    for obs in req.results ?? [] {
        guard let c = obs.topCandidates(1).first else { continue }
        let b = obs.boundingBox
        out.append(["text": c.string, "x": b.minX * w, "y": (1 - b.maxY) * h, "w": b.width * w, "h": b.height * h])
    }
    let json = String(data: try! JSONSerialization.data(withJSONObject: out), encoding: .utf8)!
    print((path as NSString).lastPathComponent + "\t" + json)
}
"""


def ocr(folder: Path, names: list[str]) -> dict[str, list[dict]]:
    """Text boxes per screenshot via macOS Vision (screenshot pixels, top-left origin)."""
    src = folder / "ocr.swift"
    src.write_text(_OCR_SWIFT)
    res = subprocess.run(["xcrun", "swift", str(src), *[str(folder / n) for n in names]],
                         check=True, capture_output=True, text=True)
    return {line.split("\t")[0]: json.loads(line.split("\t")[1]) for line in res.stdout.splitlines() if "\t" in line}


class IOSScreens:
    """Screenshots plus where things are on them."""

    def __init__(self, folder: Path):
        names = sorted({s.screen for s in IOS_STEPS})
        self.img = {n: Image.open(folder / n).convert("RGB") for n in names}
        self.size = next(iter(self.img.values())).size
        self.boxes = ocr(folder, names)

    def find(self, screen: str, text: str) -> dict:
        """The box of `text` on `screen`: an exact label first, else the first line containing it
        (the tab bar's label, the lowest one, for tab names)."""
        boxes = self.boxes[screen]
        if text == DAY:
            all_days = self.find(screen, "All days")
            row = [b for b in boxes if abs(b["y"] - all_days["y"]) < all_days["h"]
                   and b["x"] > all_days["x"] + all_days["w"]]
            assert row, f"no day chip after 'All days' on {screen}"
            return min(row, key=lambda b: b["x"])
        exact = [b for b in boxes if b["text"].strip() == text]
        hits = exact or [b for b in boxes if text in b["text"]]
        assert hits, f"{text!r} not found on {screen}: {[b['text'] for b in boxes]}"
        return max(hits, key=lambda b: b["y"]) if text in ("Papers", "Score", "Config", "Settings") else \
            min(hits, key=lambda b: b["y"])

    def point(self, screen: str, text: str) -> tuple[float, float]:
        w, h = self.size
        if text == BACK:  # the circular back button, level with the navigation bar's other items
            return (w * .075, h * .078)
        b = self.find(screen, text)
        x = b["x"] + min(b["w"], w * .5) / 2  # long titles are tapped near their start
        return (x, b["y"] + b["h"] / 2)

    def band(self, screen: str, focus: tuple[str, int, int]) -> tuple[float, float]:
        b = self.find(screen, focus[0])
        return (max(0.0, b["y"] + focus[1]), min(float(self.size[1]), b["y"] + focus[2]))

    def row(self, screen: str, text: str) -> tuple[float, float]:
        """The list row whose title contains `text`: from its title to the next row's title."""
        top = self.find(screen, text)["y"] - 45
        below = [b["y"] for b in self.boxes[screen] if re.match(r"\d+\. ", b["text"]) and b["y"] > top + 100]
        assert below, f"no row below {text!r} on {screen}"
        return (top, min(below) - 45)


def swiped(img: Image.Image, y0: float, y1: float, dx: float) -> Image.Image:
    """`img` with the row y0..y1 slid `dx` px left, the red Remove action showing behind it."""
    out = img.copy()
    y0, y1, dx = round(y0), round(y1), round(dx)
    out.paste(img.crop((0, y0, img.width, y1)), (-dx, y0))
    if dx > 0:
        d = ImageDraw.Draw(out)
        d.rectangle((img.width - dx, y0, img.width, y1), fill=(235, 68, 58))
        if dx > 260:
            f = font(46, True)
            label = "Remove"
            d.text((img.width - dx / 2 - d.textlength(label, font=f) / 2, (y0 + y1) / 2 - 28), label,
                   font=f, fill=(255, 255, 255))
    return out


def collapsed(a: Image.Image, b: Image.Image, y0: float, y1: float, b_y: float, t: float,
              tab_top: float) -> Image.Image:
    """`a` with its row y0..y1 being deleted (t: 0..1): the rows below, taken from the next screen
    `b` (where they start at b_y), move up from y1 to b_y over a red gap that fades out; the
    floating tab bar stays put."""
    out = a.copy()
    y = round(lerp(y1, b_y, ease(t)))
    red = tuple(round(v) for v in lerp((235, 68, 58), (0, 0, 0), min(1.0, t * 2)))
    ImageDraw.Draw(out).rectangle((0, round(y0), a.width, y), fill=red)
    out.paste(b.crop((0, round(b_y), b.width, round(tab_top))), (0, y))
    out.paste(a.crop((0, round(tab_top), a.width, a.height)), (0, round(tab_top)))
    return out


class Phone:
    """An iPhone mock-up on a background canvas; the camera works in canvas pixels."""

    def __init__(self, screen_size: tuple[int, int], width: int, bg: Image.Image):
        self.sw, self.sh = screen_size
        self.width = width
        self.bez = max(8, width // 26)
        self.inner = width - 2 * self.bez
        self.scale = self.inner / self.sw
        self.height = round(self.sh * self.scale) + 2 * self.bez
        self.canvas_size = bg.size
        self.x0 = (bg.width - width) // 2
        self.y0 = (bg.height - self.height) // 2
        self.bg = bg
        self.cache: dict[str, Image.Image] = {}

    def to_canvas(self, p: tuple[float, float]) -> tuple[float, float]:
        return (self.x0 + self.bez + p[0] * self.scale, self.y0 + self.bez + p[1] * self.scale)

    def compose(self, screen: Image.Image, key: str | None = None) -> Image.Image:
        if key and key in self.cache:
            return self.cache[key].copy()
        canvas = self.bg.copy()
        ph = phone(screen, self.width)
        canvas.alpha_composite(shadow(ph.size, int(self.width * .16), 40, 170), (self.x0 - 120, self.y0 - 120))
        canvas.alpha_composite(ph, (self.x0, self.y0))
        if key:
            self.cache[key] = canvas
        return canvas.copy()

    def full(self, aspect: float) -> Rect:
        """The camera showing the whole phone."""
        h = self.height * 1.06
        w = h * aspect
        cw, ch = self.canvas_size
        return ((cw - w) / 2, (ch - h) / 2, w, h)

    def frame(self, y0: float, y1: float, aspect: float) -> Rect:
        """The camera on screen band y0..y1 (screen px): the phone's full width at least, so a
        close-up still reads as the phone; it stays on the phone."""
        top, bottom = self.to_canvas((0, y0))[1], self.to_canvas((0, y1))[1]
        w = max(self.width * 1.12, (bottom - top) * aspect)
        h = w / aspect
        lo, hi = self.y0 - 30, self.y0 + self.height + 30
        y = (top + bottom) / 2 - h / 2
        y = max(lo, min(y, hi - h)) if h < hi - lo else (lo + hi - h) / 2
        return (self.x0 + self.width / 2 - w / 2, y, w, h)


def phone(screen: Image.Image, width: int) -> Image.Image:
    """`screen` inside an iPhone-like bezel, `width` px wide."""
    bez = max(8, width // 26)
    sw = width - 2 * bez
    sh = round(screen.height * sw / screen.width)
    body = Image.new("RGBA", (width, sh + 2 * bez), (0, 0, 0, 0))
    d = ImageDraw.Draw(body)
    d.rounded_rectangle((0, 0, width - 1, body.height - 1), radius=int(width * .16), fill=(28, 28, 32),
                        outline=(70, 70, 78), width=max(2, width // 200))
    body.alpha_composite(rounded(screen.convert("RGBA").resize((sw, sh), Image.Resampling.LANCZOS),
                                 int(sw * .14)), (bez, bez))
    iw, ih = sw * .3, sw * .085
    d.rounded_rectangle(((width - iw) / 2, bez + sw * .03, (width + iw) / 2, bez + sw * .03 + ih),
                        radius=int(ih / 2), fill=(0, 0, 0))
    return body


def push(a: Image.Image, b: Image.Image, t: float, tab_top: float) -> Image.Image:
    """iOS-style push: b slides in from the right while a drifts left; the status and tab bars stay."""
    out = a.copy()
    out.paste(a, (-round(a.width * .3 * t), 0))
    out.paste(b, (round(a.width * (1 - t)), 0))
    out.paste(a.crop((0, 0, a.width, round(a.height * .06))), (0, 0))
    out.paste(a.crop((0, round(tab_top), a.width, a.height)), (0, round(tab_top)))
    return out


def draw_touch(canvas: Image.Image, pos: tuple[float, float], radius: float, alpha: float, press: float) -> None:
    """A finger: a soft white disc that shrinks a little when it presses, with a ripple."""
    if alpha <= 0:
        return
    d = ImageDraw.Draw(canvas, "RGBA")
    x, y = pos
    r = radius * (1 - .15 * min(press, 1))
    d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, int(110 * alpha)),
              outline=(255, 255, 255, int(220 * alpha)), width=max(3, int(radius / 12)))
    if 0 < press < 1:
        rr = radius * (1 + .9 * press)
        d.ellipse((x - rr, y - rr, x + rr, y + rr), outline=(255, 255, 255, int(200 * (1 - press))),
                  width=max(3, int(radius / 10)))


@dataclass
class IOSFrame:
    screen: Image.Image | str  # a screenshot name, or a composed transition image
    cam: Rect
    touch: tuple[float, float] | None  # canvas px
    touch_alpha: float
    press: float
    caption: str
    caption_alpha: float
    step: int


def ios_timeline(sc: IOSScreens, ph: Phone, aspect: float) -> list[IOSFrame]:
    """Like the web tour: per step one camera move that frames what the screen shows together
    with the element the finger taps; hold to read, tap, and the next screen pushes, pops or
    switches in under the still camera (a swiped row slides out, the rows below close the gap)."""
    frames: list[IOSFrame] = []
    full = ph.full(aspect)
    cam, caption = full, ""

    def run(seconds: float, fn) -> None:
        k = max(1, round(seconds * FPS))
        frames.extend(fn((i + 1) / k) for i in range(k))

    run(.6, lambda _: IOSFrame(IOS_STEPS[0].screen, full, None, 0, 0, "", 0, -1))
    for i, st in enumerate(IOS_STEPS):
        tap_y = sc.point(st.screen, st.action[1])[1] if st.action else None
        if st.frame:
            target = ph.frame(*st.frame, aspect)
        elif st.focus:
            y0, y1 = sc.band(st.screen, st.focus)
            if tap_y is not None:
                y0, y1 = min(y0, tap_y - 150), max(y1, tap_y + 150)
            target = ph.frame(y0, y1, aspect)
        else:  # a screen passed through: stay unless the tap is out of shot
            cy = ph.to_canvas((0, tap_y))[1]
            target = cam if cam[1] + cam[3] * .1 < cy < cam[1] + cam[3] * .9 else ph.frame(tap_y - 300, tap_y + 300, aspect)
        new_cap = st.caption != caption
        if new_cap and caption:
            run(.15, lambda t: IOSFrame(st.screen, cam, None, 0, 0, caption, 1 - t, i))
        if any(abs(x - y) > 4 for x, y in zip(cam, target)):
            start = cam
            run(.6, lambda t: IOSFrame(st.screen, lerp(start, target, ease(t)), None, 0, 0, st.caption,
                                       min(1.0, t * 2) if new_cap else 1, i))
        elif new_cap:
            run(.25, lambda t: IOSFrame(st.screen, cam, None, 0, 0, st.caption, ease(t), i))
        cam, caption = target, st.caption
        run(st.hold, lambda _: IOSFrame(st.screen, cam, None, 0, 0, st.caption, 1, i))
        if not st.action:
            continue
        kind, text = st.action
        nxt = IOS_STEPS[i + 1].screen
        a, b = sc.img[st.screen], sc.img[nxt]
        tab_top = sc.find(st.screen, "Papers")["y"] - 130  # the floating tab bar's top
        if kind == "swipe":  # the row follows the finger left over the red Remove action, then is deleted
            r0, r1 = sc.row(st.screen, text)
            sx, sy = sc.size[0] * .78, (r0 + r1) / 2
            run(.2, lambda t: IOSFrame(st.screen, cam, ph.to_canvas((sx, sy)), ease(t), 0, st.caption, 1, i))
            travel = sc.size[0] * .62
            run(.45, lambda t: IOSFrame(swiped(a, r0, r1, travel * ease(t)), cam,
                                        ph.to_canvas((sx - travel * ease(t), sy)), 1, 0, st.caption, 1, i))
            run(.18, lambda t: IOSFrame(swiped(a, r0, r1, travel + (sc.size[0] - travel) * ease(t)), cam,
                                        ph.to_canvas((sx - travel, sy)), 1 - t, 0, st.caption, 1, i))
            # The rows below close the gap, landing where the next screen has them; then it fades in.
            b_y = min(bx["y"] for bx in sc.boxes[nxt] if re.match(r"\d+\. ", bx["text"])) - 45
            run(.3, lambda t: IOSFrame(collapsed(a, b, r0, r1, b_y, t, tab_top), cam, None, 0, 0,
                                       st.caption, 1, i))
            gone = collapsed(a, b, r0, r1, b_y, 1, tab_top)
            run(.2, lambda t: IOSFrame(Image.blend(gone, b, ease(t)), cam, None, 0, 0, st.caption, 1, i))
            continue
        p = ph.to_canvas(sc.point(st.screen, text))
        run(.18, lambda t: IOSFrame(st.screen, cam, p, ease(t), 0, st.caption, 1, i))
        run(.15, lambda t: IOSFrame(st.screen, cam, p, 1, t, st.caption, 1, i))
        if kind == "push":
            run(.35, lambda t: IOSFrame(push(a, b, ease(t), tab_top), cam, p, 1 - t, 1, st.caption, 1, i))
        elif kind == "pop":
            run(.35, lambda t: IOSFrame(push(b, a, 1 - ease(t), tab_top), cam, p, 1 - t, 1, st.caption, 1, i))
        else:  # a tab switch or an in-place change is instant in iOS; the finger lifts
            run(.1, lambda t: IOSFrame(Image.blend(a, b, ease(t)), cam, p, 1, 1, st.caption, 1, i))
            run(.15, lambda t: IOSFrame(nxt, cam, p, 1 - t, 1, st.caption, 1, i))
    start = cam
    run(.8, lambda t: IOSFrame(IOS_STEPS[-1].screen, lerp(start, full, ease(t)), None, 0, 0, caption, 1 - t,
                               len(IOS_STEPS)))
    run(.7, lambda _: IOSFrame(IOS_STEPS[-1].screen, full, None, 0, 0, "", 0, len(IOS_STEPS)))
    return frames


def ios_view(sc: IOSScreens, ph: Phone, f: IOSFrame, size: tuple[int, int]) -> Image.Image:
    """The camera's crop of the phone canvas at `size`."""
    if isinstance(f.screen, str):
        canvas = ph.compose(sc.img[f.screen], key=f.screen)
    else:
        canvas = ph.compose(f.screen)
    if f.touch:
        draw_touch(canvas, f.touch, 44 * ph.scale * 3 / 2, f.touch_alpha, f.press)
    x, y, w, h = f.cam
    return canvas.crop((round(x), round(y), round(x + w), round(y + h))).resize(size, Image.Resampling.LANCZOS)


def ios_tick(step: int) -> tuple[int, set[int]]:
    return tick_state([s.features for s in IOS_STEPS], step)


def _ios_captioned(sc: IOSScreens, size: tuple[int, int], band: int, gif_width: int):
    """The iPhone under a caption band."""
    area = (size[0], size[1] - band)
    bg = Image.new("RGBA", size, NAVY + (255,))
    bg.paste(gradient((size[0], band), INDIGO, NAVY), (0, 0))  # the caption band fades into the flat stage
    ph = Phone(sc.size, 900, Image.new("RGBA", (2200, 2300), NAVY + (255,)))  # flat: small as GIF
    title = font(52, True)

    def compose(f: IOSFrame) -> Image.Image:
        canvas = bg.copy()
        canvas.paste(ios_view(sc, ph, f, area), (0, band))
        d = ImageDraw.Draw(canvas, "RGBA")
        wrapped(d, f.caption, title, size[0] / 2, 70, size[0] - 120, 62,
                (255, 255, 255, int(255 * f.caption_alpha)), center=True)
        return canvas.convert("RGB")

    return size, ph, area[0] / area[1], compose, gif_width


def ios_phone(sc: IOSScreens):
    """One iPhone (4:5), the caption above."""
    return _ios_captioned(sc, (1080, 1350), 230, 720)


def ios_checklist(sc: IOSScreens):
    """The feature list on the left ticks off as the iPhone on the right shows each one."""
    size, left = (1280, 800), 520
    area = (size[0] - left, size[1])
    base = Image.new("RGBA", size, NAVY + (255,))
    b = ImageDraw.Draw(base)
    b.rectangle((0, 0, left, size[1]), fill=(11, 16, 32))
    b.text((44, 40), "arXiv Digest for iPhone", font=font(34, True), fill=(255, 255, 255))
    b.text((44, size[1] - 44), "github.com/isaac-tes/arxiv-digest", font=font(18), fill=MUTED)
    ph = Phone(sc.size, 900, Image.new("RGBA", (2200, 2300), NAVY + (255,)))
    items = list(IOS_FEATURES.values())

    def compose(f: IOSFrame) -> Image.Image:
        canvas = base.copy()
        canvas.paste(ios_view(sc, ph, f, area), (left, 0))
        checklist(canvas, (48, 168), items, *ios_tick(f.step), 25, 44, 410)
        d = ImageDraw.Draw(canvas, "RGBA")
        wrapped(d, f.caption, font(22), 44, 92, left - 80, 27, ACCENT + (int(255 * f.caption_alpha),))
        return canvas.convert("RGB")

    return size, ph, area[0] / area[1], compose, 960


def ios_story(sc: IOSScreens):
    """9:16 for phones and social posts: a taller view of the iPhone, the caption above."""
    return _ios_captioned(sc, (1080, 1920), 250, 540)


IOS_DESIGNS = {"phone": ios_phone, "checklist": ios_checklist, "story": ios_story}


def render_ios(work: Path, name: str, mp4: Path, gif: Path, sc: IOSScreens | None = None) -> None:
    shown = [f for s in IOS_STEPS for f in s.features]
    assert shown == list(IOS_FEATURES), f"steps and IOS_FEATURES disagree: {shown}"
    sc = sc or IOSScreens(work)
    size, ph, aspect, compose, gif_width = IOS_DESIGNS[name](sc)
    encode((compose(f) for f in ios_timeline(sc, ph, aspect)), size, mp4, gif, gif_width, gif_fps=10)


# ────────────────────────── Options page ──────────────────────────

def write_options_page() -> None:
    def video(prefix: str, name: str, doc: str) -> str:
        gif = OPTIONS / f"{prefix}-{name}.gif"
        mb = gif.stat().st_size / 2**20 if gif.exists() else 0
        return (f'<figure><video src="{prefix}-{name}.mp4" autoplay loop muted playsinline controls></video>'
                f"<figcaption><b>{name}</b>: {doc} GIF {mb:.1f} MB</figcaption></figure>")

    rows = []
    for title, prefix, designs in (("Web app tour", "web", WEB_DESIGNS), ("iPhone app tour", "ios", IOS_DESIGNS)):
        if any((OPTIONS / f"{prefix}-{n}.mp4").exists() for n in designs):
            figs = "".join(video(prefix, n, (fn.__doc__ or "").strip()) for n, fn in designs.items())
            rows.append(f"<h2>{title}</h2><div class=row>{figs}</div>")
    (OPTIONS / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><title>arXiv Digest showcase options</title><style>"
        "body{background:#0d1117;color:#e6edf3;font:15px/1.5 -apple-system,sans-serif;margin:32px auto;"
        "max-width:1600px;padding:0 24px}h2{margin-top:40px}.row{display:grid;grid-template-columns:"
        "repeat(3,1fr);gap:20px;align-items:start}figure{margin:0;background:#161b22;border:1px solid "
        "#30363d;border-radius:10px;padding:10px}video,img{width:100%;border-radius:6px}figcaption{color:"
        "#8b949e;margin-top:6px}b{color:#e6edf3}</style><h1>arXiv Digest: showcase options</h1>"
        '<h2>Hero</h2><img src="hero.png" style="max-width:800px">' + "".join(rows))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--render-only", action="store_true", help="re-render from the screenshots in WORK")
    ap.add_argument("--options", action="store_true", help="render every design into WORK/options")
    ap.add_argument("--design", choices=list(WEB_DESIGNS), default="cinematic")
    ap.add_argument("--ios", metavar="UDID", nargs="?", const="",
                    help="the iPhone clip, captured from this booted simulator (omit with --render-only)")
    ap.add_argument("--ios-design", choices=list(IOS_DESIGNS), default="story")
    args = ap.parse_args()
    OPTIONS.mkdir(parents=True, exist_ok=True)
    if args.ios is not None:
        if not args.render_only:
            capture_ios(args.ios, WORK / "ios")
        sc = IOSScreens(WORK / "ios")
        for name in IOS_DESIGNS if args.options else [args.ios_design]:
            if args.options:
                render_ios(WORK / "ios", name, OPTIONS / f"ios-{name}.mp4", OPTIONS / f"ios-{name}.gif", sc)
            else:
                render_ios(WORK / "ios", name, WORK / "ios-showcase.mp4", ASSETS / "ios-showcase.gif", sc)
    else:
        if args.render_only:
            cap = Capture([Beat(**b) for b in json.loads((WORK / "capture.json").read_text())["beats"]])
        else:
            cap = capture(WORK)
        if args.options:
            render_hero(WORK, OPTIONS / "hero.png")
            for name in WEB_DESIGNS:
                render_web(cap, WORK, name, OPTIONS / f"web-{name}.mp4", OPTIONS / f"web-{name}.gif")
        else:
            render_hero(WORK, ASSETS / "hero.png")
            render_social(WORK, ASSETS / "social-preview.png")
            render_web(cap, WORK, args.design, ASSETS / "showcase.mp4", ASSETS / "showcase.gif")
    if args.options:
        write_options_page()
        print(f"options: {OPTIONS / 'index.html'}")


if __name__ == "__main__":
    main()
