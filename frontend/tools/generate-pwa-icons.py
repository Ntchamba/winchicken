"""Generate the PWA icons in public/icons/ from the brand mark (public/logo-mark.png).

Re-run after the logo changes: `python3 tools/generate-pwa-icons.py` (needs Pillow).

Two families, because launchers treat them differently:
- "any": the mark on the sidebar navy, filling ~72% of the square. Shown as-is (desktop,
  Chrome's app list), so it can use most of the tile.
- "maskable": same, but the mark kept inside the central 80% safe zone (~56% here). Android
  crops these to a circle/squircle; anything outside the safe zone may be cut off.
"""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
NAVY = (13, 27, 40, 255)  # #0d1b28 — .sidebar / .dashboard-topbar background, manifest theme_color
MARK = Image.open(ROOT / "public" / "logo-mark.png").convert("RGBA")
OUT = ROOT / "public" / "icons"


def tile(size: int, mark_ratio: float) -> Image.Image:
    """Navy square with the mark centred, scaled by its longer side."""
    canvas = Image.new("RGBA", (size, size), NAVY)
    target = round(size * mark_ratio)
    scale = target / max(MARK.size)
    mark = MARK.resize((round(MARK.width * scale), round(MARK.height * scale)), Image.LANCZOS)
    canvas.alpha_composite(mark, ((size - mark.width) // 2, (size - mark.height) // 2))
    return canvas.convert("RGB")


OUT.mkdir(exist_ok=True)
for size in (192, 512):
    tile(size, 0.72).save(OUT / f"icon-{size}.png", optimize=True)
    tile(size, 0.56).save(OUT / f"icon-maskable-{size}.png", optimize=True)
print("wrote", sorted(p.name for p in OUT.iterdir()))
