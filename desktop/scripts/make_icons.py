#!/usr/bin/env python3
"""Generate the desktop app icon set (original artwork, drawn with Pillow).

Mark: a rounded teal tile with a white pulse/heartbeat line — health monitoring.
Run:  python desktop/scripts/make_icons.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "src-tauri" / "icons"

TOP = (15, 118, 110)     # #0f766e
BOTTOM = (17, 94, 89)    # #115e59
WHITE = (255, 255, 255, 255)


def _rounded_mask(size: int, radius_ratio: float = 0.22) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    r = int(size * radius_ratio)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=255)
    return mask


def _gradient(size: int) -> Image.Image:
    grad = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / max(size - 1, 1)
        grad.putpixel(
            (0, y),
            (
                int(TOP[0] + (BOTTOM[0] - TOP[0]) * t),
                int(TOP[1] + (BOTTOM[1] - TOP[1]) * t),
                int(TOP[2] + (BOTTOM[2] - TOP[2]) * t),
            ),
        )
    return grad.resize((size, size))


def render(size: int) -> Image.Image:
    base = _gradient(size).convert("RGBA")

    line = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(line)
    w = max(2, int(size * 0.075))
    x0, x1 = size * 0.14, size * 0.86
    mid = size * 0.5
    amp = size * 0.20
    pts = [
        (x0, mid),
        (size * 0.34, mid),
        (size * 0.40, mid - amp),
        (size * 0.48, mid + amp),
        (size * 0.56, mid - amp * 0.6),
        (size * 0.62, mid),
        (x1, mid),
    ]
    d.line(pts, fill=WHITE, width=w, joint="curve")
    for p in (pts[0], pts[-1]):
        r = w * 0.6
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=WHITE)

    base = Image.alpha_composite(base, line)
    base.putalpha(_rounded_mask(size))
    return base


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sizes = {
        "32x32.png": 32,
        "128x128.png": 128,
        "128x128@2x.png": 256,
        "icon.png": 512,
    }
    for name, s in sizes.items():
        render(s).save(OUT / name)
        print("wrote", OUT / name)

    ico = render(256)
    ico.save(OUT / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", OUT / "icon.ico")


if __name__ == "__main__":
    main()
