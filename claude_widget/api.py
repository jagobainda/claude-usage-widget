"""Anthropic usage API client."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import requests

from .auth import OAuthToken, refresh_token
from .config import API_HEADERS_BASE, USAGE_URL
from .utils import parse_dt


@dataclass
class WindowUsage:
    utilization: float  # 0..1
    resets_at: Optional[datetime]


@dataclass
class Usage:
    five_hour: WindowUsage
    seven_day: WindowUsage
    fetched_at: datetime


def fetch_usage(tok: OAuthToken) -> tuple[Usage, OAuthToken]:
    if tok.is_expired:
        tok = refresh_token(tok)
    headers = dict(API_HEADERS_BASE)
    headers["Authorization"] = f"Bearer {tok.access_token}"
    # (connect, read) timeouts: fail fast on network outages so the worker's
    # watchdog can dispatch a fresh attempt as soon as connectivity returns.
    r = requests.get(USAGE_URL, headers=headers, timeout=(5, 15))
    if r.status_code == 401:
        tok = refresh_token(tok)
        headers["Authorization"] = f"Bearer {tok.access_token}"
        r = requests.get(USAGE_URL, headers=headers, timeout=(5, 15))
    r.raise_for_status()
    j = r.json()

    def win(key: str) -> WindowUsage:
        block = j.get(key) or {}
        raw = float(block.get("utilization", 0.0) or 0.0)
        # API returns 0..100; normalise to 0..1.
        return WindowUsage(
            utilization=raw / 100.0,
            resets_at=parse_dt(block.get("resets_at")),
        )

    return Usage(
        five_hour=win("five_hour"),
        seven_day=win("seven_day"),
        fetched_at=datetime.now(timezone.utc),
    ), tok
