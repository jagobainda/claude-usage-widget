"""Generate a multi-size .ico for the packaged executable.

Called by build-release.ps1. Rasterises the in-repo Claude brand mark
(claude_widget/claude_icon.svg) with resvg-py natively at each target
size — giving the crispest result per resolution — and bundles all
frames into a single Windows .ico.

If resvg-py is not importable, falls back to the programmatic sparkle
drawn by claude_widget.icons.claude_logo() so the build never blocks
on a missing build-time dep.
"""
from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

from PIL import Image


SIZES = [16, 32, 48, 64, 128, 256]

REPO_ROOT = Path(__file__).resolve().parent.parent
SVG_PATH = REPO_ROOT / "claude_widget" / "claude_icon.svg"


def _render_with_resvg(size: int) -> Image.Image | None:
    try:
        import resvg_py  # type: ignore
    except ImportError:
        return None
    png_bytes = resvg_py.svg_to_bytes(
        svg_path=str(SVG_PATH),
        width=size,
        height=size,
    )
    return Image.open(BytesIO(bytes(png_bytes))).convert("RGBA")


def _render_fallback(size: int) -> Image.Image:
    sys.path.insert(0, str(REPO_ROOT))
    from claude_widget.icons import claude_logo  # noqa: WPS433

    return claude_logo(size=size).convert("RGBA")


def _render(size: int, source: list[str]) -> Image.Image:
    img = _render_with_resvg(size)
    if img is not None:
        if not source:
            source.append("resvg-py (claude_icon.svg)")
        return img
    if not source:
        source.append("fallback: claude_widget.icons.claude_logo")
    return _render_fallback(size)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: _make_icon.py <out.ico>", file=sys.stderr)
        return 2

    out = Path(sys.argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)

    source: list[str] = []
    frames = [_render(s, source) for s in SIZES]

    # Largest frame is the base; smaller frames are passed via append_images
    # so each size in the .ico is the natively-rendered raster (not a
    # downsample of the 256px one).
    frames.sort(key=lambda im: im.size[0], reverse=True)
    base, *extras = frames
    base.save(out, format="ICO", append_images=extras)
    print(f"wrote {out}  [{source[0]}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
