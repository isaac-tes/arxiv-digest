"""Record the README/docs promo assets from the live apps.

Web (hero banner + zooming tour as GIF and MP4):

    uv run --group dev --with playwright --with imageio-ffmpeg python scripts/record_showcase.py
    (first time: uv run --with playwright playwright install chromium-headless-shell)

iOS (phone clip for docs/ios-app.md), with the app built and installed on a
booted simulator (see ios/HANDOFF.md):

    uv run --group dev --with imageio-ffmpeg python scripts/record_showcase.py --ios <simulator-udid>

Both drive the real apps against live arXiv with the generic
`open-quantum-systems` preset and the dark theme; the web run uses a throwaway
HOME and a copy of the app with its own arxiv_config.json, so no personal
profiles or settings appear or change. Screenshots go to WORK; the
finished assets to docs/assets/. `--render-only` re-renders from WORK.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import arxiv_digest as ad  # noqa: E402

ASSETS = ROOT / "docs" / "assets"
WORK = Path("/tmp/arxiv-digest-showcase")
DEMO_HOME = Path("/tmp/arxiv-digest-demo-home")  # short path: it can show in the GUI
PORT = 8799
VIEW = (1440, 900)  # CSS px; screenshots are 2x
SCALE = 2
FPS = 30
BG = (14, 17, 23)  # Streamlit dark background
INDIGO, NAVY = (49, 46, 129), (15, 23, 42)
PRESET = "open-quantum-systems"

Rect = tuple[float, float, float, float]  # x, y, w, h in CSS px


def demo_config() -> ad.Config:
    cfg = ad.preset_config(PRESET)
    cfg.timeframe, cfg.top_n = "pastweek", 10
    return cfg


@dataclass
class Beat:
    caption: str
    before: str  # screenshot file
    target: tuple[float, float]  # cursor click point
    after: str
    focus: Rect
    click: bool = True


@dataclass
class Capture:
    beats: list[Beat] = field(default_factory=list)


# ────────────────────────── Web capture ──────────────────────────

def _union(*boxes: dict) -> Rect:
    x0 = min(b["x"] for b in boxes)
    y0 = min(b["y"] for b in boxes)
    x1 = max(b["x"] + b["width"] for b in boxes)
    y1 = max(b["y"] + b["height"] for b in boxes)
    return (x0, y0, x1 - x0, y1 - y0)


def _center(box: dict) -> tuple[float, float]:
    return (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


# The bordered card around a paper row: the nearest ancestor with a border.
_CARD_JS = """row => { let e = row; while (e && getComputedStyle(e).borderTopWidth === '0px') e = e.parentElement;
  const r = e.getBoundingClientRect(); return {x: r.x, y: r.y, width: r.width, height: r.height}; }"""


def capture(out: Path) -> Capture:
    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    # Run a copy of the app, so its arxiv_config.json (next to the code) is not the user's.
    app = out / "app"
    app.mkdir(exist_ok=True)
    for src in ROOT.glob("*.py"):
        shutil.copy2(src, app)
    demo_config().dump(app / "arxiv_config.json")
    for stale in (DEMO_HOME / ".arxiv_scraper").glob("removed*.json"):  # keep the fetch cache only
        stale.unlink()
    DEMO_HOME.mkdir(exist_ok=True)
    server = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(app / "arxiv_gui.py"),
         "--server.headless", "true", "--server.port", str(PORT),
         "--theme.base", "dark", "--client.toolbarMode", "viewer"],
        env={**os.environ, "HOME": str(DEMO_HOME)},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    cap = Capture()
    n = 0
    try:
        time.sleep(4)
        with sync_playwright() as p:
            page = p.chromium.launch().new_page(viewport={"width": VIEW[0], "height": VIEW[1]},
                                                device_scale_factor=SCALE)

            def settle(ms: int = 700) -> None:
                try:
                    page.wait_for_function(
                        "() => !document.querySelector('[data-stale=\"true\"]')"
                        " && !document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout=60_000)
                except Exception:  # noqa: BLE001 - a slow rerun just means a longer wait
                    pass
                page.wait_for_timeout(ms)

            def shot() -> str:
                nonlocal n
                settle()
                n += 1
                name = f"{n:02d}.png"
                page.screenshot(path=out / name)
                return name

            def box(locator) -> dict:
                locator.scroll_into_view_if_needed()
                return locator.bounding_box()

            def card(i: int = 0) -> dict:
                return page.locator("[class*='st-key-paper_row_']").nth(i).evaluate(_CARD_JS)

            def beat(caption: str, target, after_action, focus_fn, click: bool = True) -> None:
                before = shot()
                pt = _center(box(target))
                if click:
                    target.click()
                if after_action:
                    after_action()
                after = shot()
                cap.beats.append(Beat(caption, before, pt, after, focus_fn(), click))

            page.goto(f"http://localhost:{PORT}")
            page.get_by_role("button", name="Fetch papers").wait_for()
            page.add_style_tag(content="[data-testid='stToast']{display:none}")

            why = page.get_by_text("Why this score?").first
            beat("Papers ranked by your keywords, authors and categories",
                 page.get_by_role("button", name="Fetch papers"),
                 lambda: why.wait_for(timeout=180_000),
                 lambda: _union(card(0)))
            beat("Every score explained",
                 why, None,
                 lambda: _union(box(page.locator("[data-testid='stExpanderDetails']").first)))
            why.click()
            add = page.get_by_role("button", name="Add author").first
            popover = page.locator("[data-testid='stPopoverBody']")
            beat("Follow an author in one click",
                 add, lambda: popover.wait_for(),
                 lambda: _union(popover.bounding_box(), add.bounding_box()))
            unsaved = page.locator(".st-key-unsaved_box")
            beat("Unsaved changes stay visible until you save",
                 popover.locator("button").first,
                 lambda: unsaved.wait_for(),
                 lambda: _union(box(unsaved), page.locator(".paper-authors").first.bounding_box()))
            beat("Saved: their papers now rank higher",
                 unsaved.locator("button").last, lambda: unsaved.wait_for(state="detached"),
                 lambda: _union(card(0)))
            beat("Open the PDF or save it to Zotero",
                 page.get_by_role("link", name="Open PDF").first, None,
                 lambda: _union(page.locator("[class*='st-key-paper_side_']").first.bounding_box()),
                 click=False)
            first_title = page.locator(".paper-title").first.inner_text()
            first_link = page.locator("a[href*='arxiv.org/abs/']").first.get_attribute("href") or ""
            beat("Remove what you've read; the next paper moves up",
                 page.get_by_role("button", name="Remove").first,
                 lambda: page.wait_for_function(
                     "t => document.querySelector('.paper-title')?.innerText !== t", arg=first_title),
                 lambda: _union(page.get_by_text("Removed papers (1)").bounding_box(), card(0)))
            page.get_by_role("tab", name="Score a paper").click()
            page.get_by_label("arXiv link or ID").fill(first_link)
            page.keyboard.press("Enter")
            beat("Score any arXiv link and see why it is or isn't listed",
                 page.get_by_role("button", name="Score this paper"),
                 lambda: page.get_by_text("Why it did").wait_for(timeout=60_000),
                 lambda: _union(page.locator("[data-testid='stMetric']:visible").first.bounding_box(),
                                box(page.locator("[data-testid='stAlert']:visible").first)))

            # Hero card: the second-ranked paper with its first and last author followed.
            page.get_by_role("tab", name="Papers").click()
            settle()
            row = page.locator("[class*='st-key-paper_row_']").nth(1)
            hero = page.locator(".st-key-paper_row_" + row.get_attribute("class").split("st-key-paper_row_")[1].split()[0])
            for last in (False, True):
                if not popover.is_visible():  # it stays open after adding an author
                    hero.get_by_role("button", name="Add author").click()
                    popover.wait_for()
                names = popover.locator("button")
                names.nth(names.count() - 1 if last else 0).click()
                settle()
            unsaved.locator("button").last.click()
            unsaved.wait_for(state="detached")
            settle(1200)
            hero.scroll_into_view_if_needed()
            settle()
            page.screenshot(path=out / "hero.png", clip=hero.evaluate(_CARD_JS))
    finally:
        server.terminate()
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


def ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def encode(frames, size: tuple[int, int], mp4: Path, gif: Path, gif_width: int) -> None:
    """RGB frames → H.264 MP4, then a palette-optimised 12 fps GIF from it."""
    proc = subprocess.Popen(
        [ffmpeg(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{size[0]}x{size[1]}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart", str(mp4)],
        stdin=subprocess.PIPE)
    assert proc.stdin
    for f in frames:
        proc.stdin.write(f.tobytes())
    proc.stdin.close()
    proc.wait()
    subprocess.run(
        [ffmpeg(), "-y", "-loglevel", "error", "-i", str(mp4), "-vf",
         f"fps=12,scale={gif_width}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];"
         "[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle", str(gif)], check=True)
    print(f"{gif.name}: {gif.stat().st_size // 1024} KiB, {mp4.name}: {mp4.stat().st_size // 1024} KiB")


# ────────────────────────── Web tour ──────────────────────────

@dataclass
class Frame:
    a: str  # screenshot
    b: str | None  # crossfade target
    mix: float
    cam: Rect
    cursor: tuple[float, float]
    ripple: float | None
    caption: str
    caption_alpha: float


FULL: Rect = (0.0, 0.0, float(VIEW[0]), float(VIEW[1]))
TOUR = (1280, 800)


def timeline(cap: Capture) -> list[Frame]:
    """Per beat: zoom out while the cursor glides to the target, click,
    crossfade to the result, zoom in on the focus, hold."""
    frames: list[Frame] = []
    cam, cursor, shown = FULL, (VIEW[0] * .6, VIEW[1] * .55), cap.beats[0].before

    def run(seconds: float, fn) -> None:
        k = max(1, round(seconds * FPS))
        frames.extend(fn((i + 1) / k) for i in range(k))

    for bt in cap.beats:
        start_cam, start_cur, prev = cam, cursor, shown
        focus = fit(bt.focus, TOUR[0] / TOUR[1], 24, 520)
        run(.6, lambda t: Frame(prev, bt.before, ease(t * 4) if prev != bt.before else 0,
                                lerp(start_cam, FULL, ease(t)), lerp(start_cur, bt.target, ease(t)),
                                None, bt.caption, ease(t * 2)))
        cursor = bt.target
        run(.2, lambda t: Frame(bt.before, None, 0, FULL, cursor, t if bt.click else None, bt.caption, 1))
        run(.25, lambda t: Frame(bt.before, bt.after, ease(t), FULL, cursor, None, bt.caption, 1))
        run(.6, lambda t: Frame(bt.after, None, 0, lerp(FULL, focus, ease(t)), cursor, None, bt.caption, 1))
        run(1.1, lambda _: Frame(bt.after, None, 0, focus, cursor, None, bt.caption, 1))
        cam, shown = focus, bt.after
    last = cap.beats[-1].caption
    run(.6, lambda t: Frame(shown, None, 0, lerp(cam, FULL, ease(t)), cursor, None, last, 1 - t))
    run(.6, lambda _: Frame(shown, None, 0, FULL, cursor, None, "", 0))
    return frames


def render_tour(cap: Capture, work: Path) -> None:
    shots: dict[str, Image.Image] = {}

    def shot(name: str) -> Image.Image:
        if name not in shots:
            shots[name] = Image.open(work / name).convert("RGB")
        return shots[name]

    def compose(f: Frame) -> Image.Image:
        x, y, w, h = f.cam
        crop = tuple(round(v * SCALE) for v in (x, y, x + w, y + h))
        img = shot(f.a).crop(crop).resize(TOUR, Image.Resampling.LANCZOS)
        if f.b and f.mix > 0:
            img = Image.blend(img, shot(f.b).crop(crop).resize(TOUR, Image.Resampling.LANCZOS), f.mix)
        img = img.convert("RGBA")
        s = TOUR[0] / w
        draw_cursor(img, ((f.cursor[0] - x) * s, (f.cursor[1] - y) * s), max(1.0, s * .9), f.ripple)
        caption_pill(img, f.caption, TOUR[0] // 2, TOUR[1] - 80, 24, f.caption_alpha)
        return img.convert("RGB")

    encode((compose(f) for f in timeline(cap)), TOUR, ASSETS / "showcase.mp4", ASSETS / "showcase.gif", 800)


def render_hero(work: Path) -> None:
    """Name and tagline over a gradient, the hero card floating below."""
    card = Image.open(work / "hero.png").convert("RGBA")
    w, title_h = card.width + 240, 330
    out = gradient((w, title_h + card.height + 120), INDIGO, NAVY).convert("RGBA")
    d = ImageDraw.Draw(out)
    for text, f, y, col in (("arXiv Digest", font(104, True), 60, (255, 255, 255)),
                            ("Your arXiv, ranked by rules you control", font(46), 190, (226, 232, 240)),
                            ("Web app  ·  iPhone app  ·  CLI    —    free and open source", font(34), 262,
                             (165, 180, 252))):
        d.text(((w - d.textlength(text, font=f)) / 2, y), text, font=f, fill=col)
    out.alpha_composite(shadow(card.size, 18, 30, 170), (120 - 90, title_h - 90))
    out.alpha_composite(rounded(card, 18), (120, title_h))
    out = out.convert("RGB")
    out = out.resize((1600, round(out.height * 1600 / out.width)), Image.Resampling.LANCZOS)
    out.save(ASSETS / "hero.png", optimize=True)
    print(f"hero.png: {(ASSETS / 'hero.png').stat().st_size // 1024} KiB")


# ────────────────────────── iOS ──────────────────────────

IOS_SCREENS = [  # (file, launch options, caption)
    ("01-papers.png", ["-tab", "papers"], "Your ranked digest, on your iPhone"),
    ("02-detail.png", ["-open-paper", "2"], "Highlights, PDF and Zotero in one tap"),
    ("03-score.png", ["-tab", "score", "-score", "TOP"], "Score any paper"),
    ("04-config.png", ["-tab", "config", "-dirty"], "Edit keywords, authors and feeds"),
    ("05-removed.png", ["-remove", "1"], "Remove what you've read"),  # last: the removal persists
]
BUNDLE = "com.arxivdigest.app"


def capture_ios(udid: str, out: Path) -> None:
    """Standalone mode with the demo preset written into the app's store, one launch per screen."""
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
    # "Score any paper" scores this week's #1; the Swift scorer is parity-tested against this engine.
    cfg = demo_config()
    end = datetime.now(UTC)
    papers = ad.filter_papers(ad.fetch_pastweek(cfg.default_feeds, end - timedelta(days=7), end),
                              include_replacements=False)
    top_id = ad.build_ranked_entries(papers, cfg, 1)[0]["id"]
    for name, opts, _ in IOS_SCREENS:
        subprocess.run(["xcrun", "simctl", "terminate", udid, BUNDLE], capture_output=True)
        opts = [top_id if o == "TOP" else o for o in opts]
        simctl("launch", udid, BUNDLE, "-standalone", *opts)
        time.sleep(25)  # live fetch from arXiv's export API
        simctl("io", udid, "screenshot", "--type=png", str(out / name))


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


def push(a: Image.Image, b: Image.Image, t: float) -> Image.Image:
    """iOS-style push: b slides in from the right while a drifts left."""
    out = a.copy()
    out.paste(a, (-round(a.width * .3 * t), 0))
    out.paste(b, (round(a.width * (1 - t)), 0))
    return out


def render_ios(work: Path) -> None:
    screens = [(Image.open(work / f).convert("RGB"), cap) for f, _, cap in IOS_SCREENS]
    size, hold, move = (1080, 1350), 2.0, .45
    bg = gradient(size, INDIGO, NAVY).convert("RGBA")
    title = font(56, True)

    def compose(screen: Image.Image, cap: str, alpha: float) -> Image.Image:
        canvas = bg.copy()
        ph = phone(screen, 520)
        x = (size[0] - ph.width) // 2
        canvas.alpha_composite(shadow(ph.size, 80, 30, 160), (x - 90, 250 - 90))
        canvas.alpha_composite(ph, (x, 250))
        d = ImageDraw.Draw(canvas)
        d.text(((size[0] - d.textlength(cap, font=title)) / 2, 110), cap, font=title,
               fill=(255, 255, 255, int(255 * alpha)))
        return canvas.convert("RGB")

    def frames():
        for i, (img, cap) in enumerate(screens):
            for k in range(round(hold * FPS)):
                yield compose(img, cap, min(1.0, (k + 1) / (FPS * .25)))
            nxt = screens[(i + 1) % len(screens)][0]
            k_max = round(move * FPS)
            for k in range(k_max):
                yield compose(push(img, nxt, ease((k + 1) / k_max)), cap, 1 - (k + 1) / k_max)

    encode(frames(), size, WORK / "ios-showcase.mp4", ASSETS / "ios-showcase.gif", 540)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--render-only", action="store_true", help="re-render from the screenshots in WORK")
    ap.add_argument("--ios", metavar="UDID", help="record the iOS clip from this booted simulator")
    args = ap.parse_args()
    if args.ios:
        if not args.render_only:
            capture_ios(args.ios, WORK / "ios")
        render_ios(WORK / "ios")
        return
    if args.render_only:
        cap = Capture([Beat(**b) for b in json.loads((WORK / "capture.json").read_text())["beats"]])
    else:
        cap = capture(WORK)
    render_hero(WORK)
    render_tour(cap, WORK)


if __name__ == "__main__":
    main()
