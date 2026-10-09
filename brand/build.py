"""NotFlix's logo masters, drawn from geometry (python3 brand/build.py).

The mark ("Catchlight"): a screen that looks back with an anime eye's highlights. A rounded
16:12 screen with two catchlights: a tilted oval and a small round one, down and to the right.
The wordmark NOTFLIX is constructed from rectangles, diagonals and one ring (no font).

Writes the masters into brand/logo/ (colour, one-colour, small-size cut, lockups); the web icons
and other variants are exported from them (see brand/README.md).
"""

import math
from pathlib import Path

OUT = Path(__file__).parent / "logo"

ROSE = "#E11D5C"  # Catchlight Rose: the brand colour
ROSE_DARK = "#B0124A"
INK = "#141414"
WHITE = "#FFFFFF"


def svg(view, body, title, w=None, h=None):
    x, y, vw, vh = view
    size = f' width="{w or vw}" height="{h or vh}"'
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x} {y} {vw} {vh}"{size}>'
        f"<title>{title}</title>{body}</svg>\n"
    )


def rrect(x0, y0, x1, y1, r):
    return (
        f"M{x0 + r} {y0}H{x1 - r}A{r} {r} 0 0 1 {x1} {y0 + r}V{y1 - r}A{r} {r} 0 0 1 {x1 - r} {y1}"
        f"H{x0 + r}A{r} {r} 0 0 1 {x0} {y1 - r}V{y0 + r}A{r} {r} 0 0 1 {x0 + r} {y0}Z"
    )


def circle(cx, cy, r, reverse=False):
    s = 1 if reverse else 0
    return f"M{cx - r} {cy}A{r} {r} 0 1 {s} {cx + r} {cy}A{r} {r} 0 1 {s} {cx - r} {cy}Z"


def ellipse(cx, cy, rx, ry, rot):
    a = math.radians(rot)
    dx, dy = rx * math.cos(a), rx * math.sin(a)
    return (
        f"M{cx - dx:.2f} {cy - dy:.2f}A{rx} {ry} {rot} 1 0 {cx + dx:.2f} {cy + dy:.2f}"
        f"A{rx} {ry} {rot} 1 0 {cx - dx:.2f} {cy - dy:.2f}Z"
    )


# The mark on a 256 grid. Regular: for 48 px and up. Small: bigger catchlights, a fuller screen,
# for favicons and anything under 48 px (the small catchlight would vanish otherwise).
MARK = {
    "regular": dict(
        screen=rrect(20, 46, 236, 210, 46),
        lights=[ellipse(98, 106, 34, 25, -35), circle(146, 141, 12)],
    ),
    "small": dict(
        screen=rrect(12, 38, 244, 218, 50),
        lights=[ellipse(98, 104, 44, 32, -35), circle(160, 153, 20)],
    ),
}


def mark(cut="regular", screen=ROSE, lights=WHITE):
    """The mark in two colours (catchlights drawn on top), or one colour (lights=None: real holes)."""
    m = MARK[cut]
    if lights is None:
        return f'<path fill="{screen}" fill-rule="evenodd" d="{m["screen"]}{"".join(m["lights"])}"/>'
    return f'<path fill="{screen}" d="{m["screen"]}"/><path fill="{lights}" d="{"".join(m["lights"])}"/>'


# --- The wordmark: cap height 96 (y 80-176), stroke 24, letter gap 14 ---
S, TOP, BOT, GAP = 24, 80, 176, 14


def _rect(x, y, w, h):
    return f"M{x} {y}h{w}v{h}h{-w}Z"


def _poly(*pts):
    return "M" + "L".join(f"{x:.2f} {y:.2f}" for x, y in pts) + "Z"


def wordmark_path():
    x, parts = 0, []
    parts += [_rect(x, TOP, S, 96), _rect(x + 48, TOP, S, 96),
              _poly((x, TOP), (x + 27, TOP), (x + 72, BOT), (x + 45, BOT))]  # N
    x += 72 + GAP
    parts += [circle(x + 49, 128, 50), circle(x + 49, 128, 26, reverse=True)]  # O (overshoot)
    x += 98 + GAP
    parts += [_rect(x, TOP, 72, S), _rect(x + 24, TOP, S, 96)]  # T
    x += 72 + GAP
    parts += [_rect(x, TOP, S, 96), _rect(x, TOP, 62, S), _rect(x, 118, 52, 22)]  # F
    x += 62 + GAP
    parts += [_rect(x, TOP, S, 96), _rect(x, BOT - S, 58, S)]  # L
    x += 58 + GAP
    parts += [_rect(x, TOP, S, 96)]  # I
    x += S + GAP
    parts += [_poly((x, TOP), (x + 27, TOP), (x + 78, BOT), (x + 51, BOT)),
              _poly((x + 51, TOP), (x + 78, TOP), (x + 27, BOT), (x, BOT))]  # X
    x += 78
    return " ".join(parts), x


WORD, WORD_W = wordmark_path()
LOCKUP_GAP = 32  # symbol to wordmark: a third of the cap height
STACK_DY = 172  # stacked: wordmark caps start 42 below the screen


def word(fill, dx=0, dy=0):
    return f'<path transform="translate({dx} {dy})" fill="{fill}" d="{WORD}"/>'


def write(name, content):
    (OUT / name).write_text(content)


def build():
    OUT.mkdir(exist_ok=True)
    # Symbol (padded 256 square).
    sq = (0, 0, 256, 256)
    write("notflix-symbol.svg", svg(sq, mark(), "NotFlix"))
    write("notflix-symbol-black.svg", svg(sq, mark(screen="#000000", lights=None), "NotFlix"))
    write("notflix-symbol-white.svg", svg(sq, mark(screen=WHITE, lights=None), "NotFlix"))
    write("notflix-symbol-rose.svg", svg(sq, mark(lights=None), "NotFlix"))
    write("notflix-symbol-small.svg", svg(sq, mark("small"), "NotFlix (small sizes)"))
    write("notflix-symbol-small-black.svg",
          svg(sq, mark("small", screen="#000000", lights=None), "NotFlix (small sizes)"))
    # App icon: the small cut on an ink tile.
    tile = f'<rect width="256" height="256" rx="56" fill="{INK}"/>'
    icon = f'<g transform="translate(128 128) scale(0.74) translate(-128 -128)">{mark("small")}</g>'
    write("notflix-app-icon.svg", svg(sq, tile + icon, "NotFlix"))
    # Maskable (Android): full-bleed ink, the mark inside the safe zone (80 %).
    mask = f'<g transform="translate(128 128) scale(0.6) translate(-128 -128)">{mark("small")}</g>'
    write("notflix-maskable.svg", svg(sq, f'<rect width="256" height="256" fill="{INK}"/>' + mask, "NotFlix"))
    # Favicon: the small cut, cropped to the screen (more pixels for the mark in a browser tab).
    write("notflix-favicon.svg", svg((8, 8, 240, 240), mark("small"), "NotFlix"))

    # Horizontal lockup: tight box (screen 46..210 high), wordmark centred on the screen.
    x0, w = 20, 236 - 20 + LOCKUP_GAP + WORD_W
    view = (x0, 46, w, 164)
    wx = 236 + LOCKUP_GAP
    for name, screen, lights, ink in [
        ("notflix-horizontal.svg", ROSE, WHITE, WHITE),  # on dark
        ("notflix-horizontal-on-light.svg", ROSE, WHITE, INK),
        ("notflix-horizontal-black.svg", "#000000", None, "#000000"),
        ("notflix-horizontal-white.svg", WHITE, None, WHITE),
    ]:
        write(name, svg(view, mark(screen=screen, lights=lights) + word(ink, wx), "NotFlix"))

    # Stacked lockup: the mark centred over the wordmark.
    sx = (WORD_W - 256) / 2
    stacked_body = lambda screen, lights, ink: (  # noqa: E731
        f'<g transform="translate({sx} 0)">{mark(screen=screen, lights=lights)}</g>'
        + word(ink, 0, STACK_DY)
    )
    # (wordmark caps at 80 + STACK_DY .. 176 + STACK_DY; 2 for the O's overshoot)
    sview = (0, 46, WORD_W, 176 + STACK_DY + 2 - 46)
    write("notflix-stacked.svg", svg(sview, stacked_body(ROSE, WHITE, WHITE), "NotFlix"))
    write("notflix-stacked-on-light.svg", svg(sview, stacked_body(ROSE, WHITE, INK), "NotFlix"))
    write("notflix-stacked-black.svg", svg(sview, stacked_body("#000000", None, "#000000"), "NotFlix"))

    # Wordmark alone.
    wview = (0, 78, WORD_W, 100)
    write("notflix-wordmark.svg", svg(wview, word(WHITE), "NOTFLIX"))
    write("notflix-wordmark-on-light.svg", svg(wview, word(INK), "NOTFLIX"))
    sync_apps()
    print(f"masters written to {OUT}; logo paths synced into the apps")


ROOT = Path(__file__).resolve().parent.parent


def sync_apps():
    """The logo's geometry for the web app (an inline SVG that takes the design's colours) and the
    desktop app's splash screen."""
    m = MARK["regular"]
    ts = f"""// Generated by brand/build.py: the NotFlix logo's geometry (edit it there, not here).

/** The mark ("Catchlight") on a 256 grid: the screen, and its two catchlights. */
export const MARK_SCREEN = "{m["screen"]}";
export const MARK_LIGHTS = "{"".join(m["lights"])}";
/** The NOTFLIX wordmark: caps 80-176 on the same grid, {WORD_W} wide. */
export const WORDMARK = "{WORD}";
export const WORDMARK_WIDTH = {WORD_W};
/** Horizontal lockup: the wordmark starts this far right of the symbol's origin. */
export const LOCKUP_WORD_X = {236 + LOCKUP_GAP};
/** The horizontal lockup's tight box (x, y, width, height). */
export const LOCKUP_VIEWBOX = "20 46 {236 - 20 + LOCKUP_GAP + WORD_W} 164";
"""
    (ROOT / "frontend" / "src" / "lib" / "logo.ts").write_text(ts)
    icons = ROOT / "desktop" / "icons"
    icons.mkdir(exist_ok=True)
    (icons / "notflix-horizontal.svg").write_text((OUT / "notflix-horizontal.svg").read_text())


if __name__ == "__main__":
    build()
