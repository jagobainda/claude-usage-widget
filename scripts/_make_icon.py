"""Generate a multi-size .ico for the packaged executable.

Called by build-release.ps1. Mirrors the visual style of the runtime tray
icon (green filled circle with white "CC" text) but at higher resolution
and saved as a proper .ico with the standard size set.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
BG = (40, 167, 69, 255)  # same green as the "ok" runtime icon
FG = (255, 255, 255, 255)
TEXT = "CC"


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("segoeuib.ttf", "arialbd.ttf", "seguisb.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _render(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = max(1, size // 32)
    d.ellipse((pad, pad, size - pad - 1, size - pad - 1), fill=BG)
    font = _font(int(size * 0.5))
    bbox = d.textbbox((0, 0), TEXT, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]),
           TEXT, fill=FG, font=font)
    return img


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: _make_icon.py <out.ico>", file=sys.stderr)
        return 2
    out = Path(sys.argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    base = _render(256)
    base.save(out, format="ICO", sizes=SIZES)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
