"""Build clean DealSig.AI brand lockups from the flawed source art.

DealSigAI.PNG is a 1254px square whose "transparent" background is actually a
drawn checkerboard, and whose glyph sits stacked above the wordmark. This keys
the checkerboard out, then recomposes glyph + wordmark into a horizontal
lockup that stays legible at nav height.
"""
from PIL import Image
import numpy as np

SRC = "DealSigAI.PNG"
OUT_LIGHT = "app/static/brand-lockup.png"
OUT_DARK = "app/static/brand-lockup-dark.png"

SCALE = 3          # export @3x, displayed at 1/3 size
GLYPH_H = 34 * SCALE
GAP = 11 * SCALE
WORD_RATIO = 0.60  # wordmark height as a fraction of glyph height


def keyed_rgba(path: str) -> Image.Image:
    """Drop the drawn checkerboard, keeping antialiased edges."""
    a = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    chroma = a.max(axis=2) - a.min(axis=2)

    bg = 250.0
    alpha = np.clip(np.maximum(np.clip((bg - lum) / bg, 0, 1) * 1.35, chroma / 120.0), 0, 1)
    # The checkerboard is light AND neutral; the logo is dark or chromatic.
    # Without this the faint 245/254 tiles survive as a ghost rectangle.
    alpha[(lum > 220) & (chroma < 30)] = 0.0
    alpha[alpha < 0.12] = 0.0

    # Un-premultiply: the observed pixel is logo over a light background, so
    # recover the logo's own colour instead of baking a pale halo into edges.
    safe = np.maximum(alpha, 1e-3)[..., None]
    rgb = np.clip((a - (1 - safe) * bg) / safe, 0, 255)
    return Image.fromarray(
        np.dstack([rgb.astype(np.uint8), (alpha * 255).astype(np.uint8)]), "RGBA"
    )


def lighten(img: Image.Image) -> Image.Image:
    """Raise lightness, keep hue — so it reads on a dark background."""
    a = np.asarray(img).astype(np.float32) / 255.0
    rgb, alpha = a[..., :3], a[..., 3]
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    lum, delta = (mx + mn) / 2, mx - mn

    sat = np.where(delta == 0, 0, delta / np.maximum(1 - np.abs(2 * lum - 1), 1e-6))
    new_lum = 0.68 + 0.22 * lum

    c = (1 - np.abs(2 * new_lum - 1)) * np.clip(sat, 0, 1)
    m = new_lum - c / 2
    # Recover hue sector from the original channel ordering.
    hue = np.zeros_like(lum)
    nz = delta > 1e-6
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    hue = np.where(nz & (mx == r), ((g - b) / np.maximum(delta, 1e-6)) % 6, hue)
    hue = np.where(nz & (mx == g), (b - r) / np.maximum(delta, 1e-6) + 2, hue)
    hue = np.where(nz & (mx == b), (r - g) / np.maximum(delta, 1e-6) + 4, hue)

    x = c * (1 - np.abs((hue % 2) - 1))
    zeros = np.zeros_like(c)
    sectors = [(c, x, zeros), (x, c, zeros), (zeros, c, x),
               (zeros, x, c), (x, zeros, c), (c, zeros, x)]
    out = np.zeros_like(rgb)
    idx = np.floor(hue).astype(int) % 6
    for i, (rr, gg, bb) in enumerate(sectors):
        sel = idx == i
        out[..., 0] = np.where(sel, rr, out[..., 0])
        out[..., 1] = np.where(sel, gg, out[..., 1])
        out[..., 2] = np.where(sel, bb, out[..., 2])
    out += m[..., None]

    return Image.fromarray(
        np.dstack([np.clip(out, 0, 1) * 255, alpha * 255]).astype(np.uint8), "RGBA"
    )


def solid_bbox(img: Image.Image):
    """Bounding box of confidently-opaque pixels, ignoring any faint residue."""
    mask = np.asarray(img.getchannel("A")) > 128
    ys, xs = np.nonzero(mask)
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def compose(src: Image.Image) -> Image.Image:
    """Glyph left, wordmark right, vertically centred."""
    full = src.crop(solid_bbox(src))
    # The source stacks glyph over wordmark with a clean empty band between;
    # split on the widest run of empty rows.
    rows = (np.asarray(full.getchannel("A")) > 128).sum(axis=1)
    runs, start = [], None
    for y, n in enumerate(rows):
        if n == 0 and start is None:
            start = y
        elif n and start is not None:
            runs.append((y - start, start, y))
            start = None
    if not runs:
        raise SystemExit("no gap found between glyph and wordmark")
    _, gap_start, gap_end = max(runs)

    glyph = full.crop((0, 0, full.width, gap_start))
    word = full.crop((0, gap_end, full.width, full.height))
    glyph = glyph.crop(solid_bbox(glyph))
    word = word.crop(solid_bbox(word))

    gw = round(glyph.width * GLYPH_H / glyph.height)
    glyph = glyph.resize((gw, GLYPH_H), Image.LANCZOS)
    wh = round(GLYPH_H * WORD_RATIO)
    ww = round(word.width * wh / word.height)
    word = word.resize((ww, wh), Image.LANCZOS)

    canvas = Image.new("RGBA", (gw + GAP + ww, GLYPH_H), (0, 0, 0, 0))
    canvas.alpha_composite(glyph, (0, 0))
    canvas.alpha_composite(word, (gw + GAP, (GLYPH_H - wh) // 2))
    return canvas


keyed = keyed_rgba(SRC)
light = compose(keyed)
dark = compose(lighten(keyed))
light.save(OUT_LIGHT)
dark.save(OUT_DARK)
print(f"{OUT_LIGHT} {light.size}  -> css height {GLYPH_H // SCALE}px")
print(f"{OUT_DARK} {dark.size}")
