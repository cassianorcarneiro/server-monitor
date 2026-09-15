#!/usr/bin/env python3
"""Generates the "install as app" icon set from the same design already used
for the browser-tab favicon (the inline SVG in static/index.html's <head>).

The tab icon was never the problem — Chrome already shows it. What's missing
is everything a browser's "Install as app" / "Add to Home Screen" flow reads
instead: a manifest.json with an icons array, and PNG assets at the sizes
that array declares. Without them, the installed app falls back to a generic
icon or a cropped screenshot.

Run once at design time (`python3 generate_icons.py`) from the project root;
commit the PNGs/ICO it writes to static/. Pillow is only needed for this
script — not a runtime dependency of monitor_server.py.
"""

from PIL import Image, ImageDraw

BG = "#09090b"
GREEN = "#22d87a"
BASELINE = "#2a2a32"

# Bar heights and x-positions, in the original 32x32 viewBox's coordinate
# system (baseline at y=22). Kept as literal numbers rather than re-deriving
# them, so this stays a direct match for the existing favicon rather than a
# reinterpretation of it.
_BARS_32 = [(8, 16), (12, 10), (16, 14), (20, 8), (24, 13)]  # (x, top_y)
_BASELINE_Y = 22
_BASELINE_X = (6, 26)


def draw_icon(size: int, frame: bool = True) -> Image.Image:
    """Renders the bar-graph glyph at `size`, scaled up from the 32px design."""
    scale = size / 32
    img = Image.new("RGB", (size, size), BG)
    draw = ImageDraw.Draw(img)

    if frame:
        inset = round(3 * scale)
        radius = round(4 * scale)
        draw.rounded_rectangle(
            [inset, inset, size - inset, size - inset],
            radius=radius,
            outline=GREEN,
            width=max(1, round(1.5 * scale)),
        )

    baseline_y = round(_BASELINE_Y * scale)
    draw.line(
        [(round(_BASELINE_X[0] * scale), baseline_y), (round(_BASELINE_X[1] * scale), baseline_y)],
        fill=BASELINE,
        width=max(1, round(scale)),
    )

    bar_width = max(2, round(2 * scale))
    for x, top_y in _BARS_32:
        px, py_top, py_bottom = round(x * scale), round(top_y * scale), baseline_y
        draw.line([(px, py_bottom), (px, py_top)], fill=GREEN, width=bar_width)
        # Round line caps, matching the SVG's stroke-linecap="round".
        r = bar_width / 2
        draw.ellipse([px - r, py_top - r, px + r, py_top + r], fill=GREEN)
        draw.ellipse([px - r, py_bottom - r, px + r, py_bottom + r], fill=GREEN)

    return img


def rounded(img: Image.Image, radius_ratio: float = 0.19) -> Image.Image:
    """Rounds the outer corners; used for the tab favicon only. iOS/Android
    apply their own mask to home-screen icons, so those stay square."""
    size = img.size[0]
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size, size], radius=round(size * radius_ratio), fill=255
    )
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, mask=mask)
    return out


if __name__ == "__main__":
    base = draw_icon(512)

    rounded(base, 0.19).resize((512, 512)).save(
        "static/favicon.ico", sizes=[(s, s) for s in (16, 32, 48)]
    )
    draw_icon(192).save("static/icon-192.png")
    draw_icon(512).save("static/icon-512.png")
    # iOS does not mask this one itself and expects full opacity.
    draw_icon(180).save("static/apple-touch-icon.png")

    print("Generated: static/favicon.ico, icon-192.png, icon-512.png, apple-touch-icon.png")
