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
class LimitUsage:
    """A single usage limit reported by the API (one card in the popup).

    The endpoint's ``limits`` array is the canonical, human-facing list of
    active quotas: the 5-hour session window, the weekly all-models window and
    any per-model scoped windows (e.g. the weekly cap on the most expensive
    model). Rendering straight from it means new limit kinds appear in the UI
    without code changes.
    """

    kind: str  # "session", "weekly_all", "weekly_scoped", …
    label: str  # full card title, e.g. "7-day · Fable"
    short_label: str  # compact tooltip label, e.g. "Fable"
    utilization: float  # 0..1
    resets_at: Optional[datetime]
    severity: str  # "normal", "warning", …
    is_active: bool


@dataclass
class Usage:
    limits: list[LimitUsage]
    fetched_at: datetime

    @property
    def primary(self) -> Optional[LimitUsage]:
        """The limit that drives the tray icon number and tooltip headline.

        The 5-hour session window is the headline figure; fall back to the
        first reported limit if the API ever omits ``session``.
        """
        for lim in self.limits:
            if lim.kind == "session":
                return lim
        return self.limits[0] if self.limits else None


def _limit_labels(kind: str, scope: Optional[dict]) -> tuple[str, str]:
    """Return (full_label, short_label) for a limit given its kind/scope."""
    if kind == "session":
        return "5-hour window", "5h"
    if kind == "weekly_all":
        return "7-day window", "7d"
    if kind == "weekly_scoped":
        model = (scope or {}).get("model") or {}
        name = model.get("display_name") or "scoped"
        return f"7-day · {name}", name
    # Unknown/future kind: derive something readable rather than dropping it.
    pretty = kind.replace("_", " ").title() if kind else "Limit"
    return pretty, pretty


def _parse_limits(j: dict) -> list[LimitUsage]:
    limits: list[LimitUsage] = []
    for item in j.get("limits") or []:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind") or ""
        # ``percent`` is an integer 0..100; normalise to 0..1.
        pct = float(item.get("percent") or 0.0)
        full, short = _limit_labels(kind, item.get("scope"))
        limits.append(
            LimitUsage(
                kind=kind,
                label=full,
                short_label=short,
                utilization=pct / 100.0,
                resets_at=parse_dt(item.get("resets_at")),
                severity=item.get("severity") or "normal",
                is_active=bool(item.get("is_active")),
            )
        )

    if limits:
        return limits

    # Fallback for responses without a ``limits`` array (older API shape):
    # synthesise it from the legacy ``five_hour`` / ``seven_day`` blocks whose
    # ``utilization`` is on a 0..100 scale.
    for key, (full, short) in (
        ("five_hour", ("5-hour window", "5h")),
        ("seven_day", ("7-day window", "7d")),
    ):
        block = j.get(key) or {}
        limits.append(
            LimitUsage(
                kind=key,
                label=full,
                short_label=short,
                utilization=float(block.get("utilization") or 0.0) / 100.0,
                resets_at=parse_dt(block.get("resets_at")),
                severity="normal",
                is_active=True,
            )
        )
    return limits


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

    return Usage(
        limits=_parse_limits(j),
        fetched_at=datetime.now(timezone.utc),
    ), tok
