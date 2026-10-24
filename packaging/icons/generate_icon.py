"""One-off script: draws the Simple-ElginFC app icon and exports every
size/format the platform installers need. Not part of the app itself and
not run automatically — re-run manually if the icon design ever changes.

Usage: venv/bin/python packaging/icons/generate_icon.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT_DIR = Path(__file__).parent
APP_RESOURCES = OUT_DIR.parent.parent / "src" / "simple_elginfc" / "gui" / "resources"
SIZE = 1024

# Elgin City's black and white: a striped shield on a black tile, with a
# football over its lower half. (Not the club's crest, which is theirs.)
TILE_TOP = (40, 40, 44, 255)
TILE_BOTTOM = (8, 8, 10, 255)
WHITE = (250, 250, 250, 255)
BLACK = (18, 18, 20, 255)
EDGE = (200, 200, 205, 255)


def draw_icon() -> Image.Image:
    tile = Image.new("RGBA", (SIZE, SIZE))
    td = ImageDraw.Draw(tile)
    for y in range(SIZE):
        t = y / SIZE
        td.line([(0, y), (SIZE, y)], fill=tuple(int(TILE_TOP[i] + (TILE_BOTTOM[i] - TILE_TOP[i]) * t) for i in range(3)) + (255,))
    mask = Image.new("L", (SIZE, SIZE), 0)
    margin = SIZE * 0.06
    ImageDraw.Draw(mask).rounded_rectangle([margin, margin, SIZE - margin, SIZE - margin], radius=SIZE * 0.22, fill=255)
    img = tile
    s = SIZE / 100

    # the shield's outline, as a mask, so the stripes stay inside it
    outline = _shield_mask(s)
    shadow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 170), (0, int(1.5 * s)), outline)
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(SIZE * 0.02)))
    rim = Image.new("RGBA", (SIZE, SIZE), EDGE)
    img.paste(rim, (0, 0), outline)
    stripes = Image.new("RGBA", (SIZE, SIZE), WHITE)
    sd = ImageDraw.Draw(stripes)
    for i in range(7):
        if i % 2:
            x0 = 24 * s + i * (52 * s / 7)
            sd.rectangle([x0, 0, x0 + 52 * s / 7, SIZE], fill=BLACK)
    inner = _shield_mask(s, inset=2.2 * s)
    img.paste(stripes, (0, 0), inner)

    # the ball: white with black patches, over the shield's lower half
    d = ImageDraw.Draw(img)
    cx, cy, r = 50 * s, 60 * s, 15 * s
    ball_shadow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(ball_shadow).ellipse([cx - r, cy - r + 2 * s, cx + r, cy + r + 2 * s], fill=(0, 0, 0, 150))
    img.alpha_composite(ball_shadow.filter(ImageFilter.GaussianBlur(SIZE * 0.012)))
    d = ImageDraw.Draw(img)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE, outline=BLACK, width=int(1.4 * s))
    import math

    def pentagon(px, py, pr, rot):
        return [(px + pr * math.cos(rot + k * 2 * math.pi / 5), py + pr * math.sin(rot + k * 2 * math.pi / 5)) for k in range(5)]

    d.polygon(pentagon(cx, cy, 5.2 * s, -math.pi / 2), fill=BLACK)
    for k in range(5):
        a = -math.pi / 2 + k * 2 * math.pi / 5
        px, py = cx + 11.5 * s * math.cos(a), cy + 11.5 * s * math.sin(a)
        d.line([(cx + 5.2 * s * math.cos(a), cy + 5.2 * s * math.sin(a)), (px, py)], fill=BLACK, width=int(1.2 * s))
        ball = Image.new("L", (SIZE, SIZE), 0)
        ImageDraw.Draw(ball).ellipse([cx - r + 1.4 * s, cy - r + 1.4 * s, cx + r - 1.4 * s, cy + r - 1.4 * s], fill=255)
        patch = Image.new("L", (SIZE, SIZE), 0)
        ImageDraw.Draw(patch).polygon(pentagon(px + 2.6 * s * math.cos(a), py + 2.6 * s * math.sin(a), 4.6 * s, a + math.pi), fill=255)
        from PIL import ImageChops

        img.paste(BLACK, (0, 0), ImageChops.multiply(ball, patch))

    out = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def _shield_mask(s: float, inset: float = 0.0) -> Image.Image:
    import math

    left, right, top, shoulder, point = 22 * s + inset, 78 * s - inset, 14 * s + inset, 48 * s, 88 * s - inset * 1.4
    mid = (left + right) / 2
    pts = [(left, top), (right, top), (right, shoulder)]
    steps = 40
    for i in range(1, steps + 1):
        a = i / steps
        pts.append((right - (right - mid) * (1 - math.cos(a * math.pi / 2)), shoulder + (point - shoulder) * math.sin(a * math.pi / 2)))
    for i in range(1, steps + 1):
        a = 1 - i / steps
        pts.append((left + (mid - left) * (1 - math.cos(a * math.pi / 2)), shoulder + (point - shoulder) * math.sin(a * math.pi / 2)))
    m = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    return m


def main() -> None:
    icon = draw_icon()
    master_png = OUT_DIR / "icon.png"
    icon.save(master_png)
    print(f"wrote {master_png}")

    APP_RESOURCES.mkdir(parents=True, exist_ok=True)
    icon.resize((256, 256), Image.LANCZOS).save(APP_RESOURCES / "icon.png")
    print(f"wrote {APP_RESOURCES / 'icon.png'}")

    # Windows .ico (multi-resolution)
    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    ico_path = OUT_DIR / "icon.ico"
    icon.save(ico_path, sizes=[(s, s) for s in ico_sizes])
    print(f"wrote {ico_path}")

    # Linux: a few common hicolor sizes as plain PNGs.
    for s in (16, 32, 48, 64, 128, 256, 512):
        icon.resize((s, s), Image.LANCZOS).save(OUT_DIR / f"icon_{s}.png")
    print("wrote icon_16..512.png")

    # macOS .icns: iconutil on a Mac; elsewhere Pillow's own ICNS writer is
    # good enough to commit, so CI on macOS always has a file to use.
    if sys.platform == "darwin" and shutil.which("iconutil"):
        iconset = OUT_DIR / "icon.iconset"
        iconset.mkdir(exist_ok=True)
        for s in (16, 32, 128, 256, 512):
            icon.resize((s, s), Image.LANCZOS).save(iconset / f"icon_{s}x{s}.png")
            icon.resize((s * 2, s * 2), Image.LANCZOS).save(iconset / f"icon_{s}x{s}@2x.png")
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(OUT_DIR / "icon.icns")],
            check=True,
        )
        for f in iconset.iterdir():
            f.unlink()
        iconset.rmdir()
    else:
        icon.save(OUT_DIR / "icon.icns")
    print(f"wrote {OUT_DIR / 'icon.icns'}")


if __name__ == "__main__":
    main()
