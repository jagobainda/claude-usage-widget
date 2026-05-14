"""Constants, paths and theme palette."""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# API / OAuth
# ---------------------------------------------------------------------------

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
# Public OAuth client id used by Claude Code CLI.
OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"

API_HEADERS_BASE = {
    "anthropic-beta": "oauth-2025-04-20",
    "User-Agent": "claude-code/2.0.31",
}

REFRESH_INTERVAL_SECONDS = 60  # 1 minute

TOKEN_PATH_CANDIDATES = [
    Path.home() / ".claude" / ".credentials.json",
    Path(os.environ.get("APPDATA", "")) / "Claude" / ".credentials.json",
    Path(os.environ.get("APPDATA", "")) / "Claude Code" / ".credentials.json",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Claude" / ".credentials.json",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Claude Code" / ".credentials.json",
]


# ---------------------------------------------------------------------------
# Tray icon rendering
# ---------------------------------------------------------------------------

ICON_SIZE = 64


# ---------------------------------------------------------------------------
# Popup theme (dark)
# ---------------------------------------------------------------------------

class Theme:
    # Surfaces
    BG          = "#1b1c20"  # window body
    TITLEBAR    = "#131418"  # custom title bar
    CARD        = "#24262c"  # subtle elevated surface
    BORDER      = "#34363d"

    # Text
    TEXT        = "#e9eaee"
    TEXT_MUTED  = "#9aa0a8"
    TEXT_DIM    = "#6c7079"

    # Buttons
    BTN_BG      = "#2c2f36"
    BTN_BG_HOV  = "#3a3e47"
    BTN_FG      = "#e9eaee"
    BTN_PRIMARY = "#4f8cff"
    BTN_PRIMARY_HOV = "#3d78e6"

    # Progress bar track
    TRACK       = "#2c2f36"

    # Status accent palette (matches tray icon colour scheme).
    OK          = "#3ecf63"
    WARN_LOW    = "#f0c419"
    WARN_HIGH   = "#ff9933"
    DANGER      = "#e64960"
    NEUTRAL     = "#7a818c"

    # Claude brand accent.
    ACCENT      = "#D97757"
    ACCENT_HOV  = "#c0613f"

    FONT_FAMILY = "Segoe UI"
    FONT_TITLE  = (FONT_FAMILY, 10, "bold")
    FONT_BODY   = (FONT_FAMILY, 10)
    FONT_HEAD   = (FONT_FAMILY, 11, "bold")
    FONT_PCT    = (FONT_FAMILY, 14, "bold")
    FONT_SMALL  = (FONT_FAMILY, 8)


def status_color_hex(pct: float) -> str:
    if pct >= 0.90:
        return Theme.DANGER
    if pct >= 0.75:
        return Theme.WARN_HIGH
    if pct >= 0.50:
        return Theme.WARN_LOW
    return Theme.OK


def status_color_rgb(pct: float) -> tuple[int, int, int]:
    if pct >= 0.90:
        return (230, 73, 96)
    if pct >= 0.75:
        return (255, 153, 51)
    if pct >= 0.50:
        return (240, 196, 25)
    return (62, 207, 99)
