"""Generates the PWA icons (requires Pillow: pip install pillow)."""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "apps" / "web" / "public" / "icons"
INK, PAPER, EMBER = (27, 25, 22), (250, 248, 245), (226, 86, 43)
SS = 4  # supersampling


def icon(size: int, *, maskable: bool = False) -> Image.Image:
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if maskable:
        d.rectangle([0, 0, s, s], fill=INK)
        scale = 0.62  # keep the glyph inside the safe zone
    else:
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.225), fill=INK)
        scale = 0.78
    cx = cy = s / 2
    r = s * 0.5 * scale * 0.62
    w = max(2, int(s * 0.07 * scale))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=PAPER, width=w)
    dr = s * 0.065 * scale * 1.3
    ex, ey = cx + r * 0.72, cy - r * 0.72
    d.ellipse([ex - dr, ey - dr, ex + dr, ey + dr], fill=EMBER)
    return img.resize((size, size), Image.LANCZOS)


OUT.mkdir(parents=True, exist_ok=True)
icon(192).save(OUT / "icon-192.png")
icon(512).save(OUT / "icon-512.png")
icon(512, maskable=True).save(OUT / "maskable-512.png")
icon(180).save(OUT / "apple-touch-icon.png")
icon(32).save(OUT / "favicon-32.png")
print("icons written to", OUT)
