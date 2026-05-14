"""Small shared helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def format_until(dt: Optional[datetime]) -> str:
    if dt is None:
        return "—"
    now = datetime.now(timezone.utc)
    delta = dt - now
    total = int(delta.total_seconds())
    if total <= 0:
        return "now"
    h, rem = divmod(total, 3600)
    m, _ = divmod(rem, 60)
    if h >= 24:
        d, h = divmod(h, 24)
        return f"{d}d {h}h {m}m"
    return f"{h}h {m:02d}m"
