"""Shared application state and background refresh worker."""

from __future__ import annotations

import threading
import traceback
from typing import Optional, TYPE_CHECKING

from .api import Usage, fetch_usage
from .auth import OAuthToken, load_token
from .config import REFRESH_INTERVAL_SECONDS
from .icons import error_icon, usage_icon
from .utils import format_until

if TYPE_CHECKING:
    import pystray


class AppState:
    def __init__(self) -> None:
        self.token: Optional[OAuthToken] = None
        self.usage: Optional[Usage] = None
        self.last_error: Optional[str] = None
        self.icon: Optional["pystray.Icon"] = None
        self._refresh_event = threading.Event()
        self._stop_event = threading.Event()
        self._listeners: list = []

    # ----- listeners -----
    def add_listener(self, fn) -> None:
        self._listeners.append(fn)

    def remove_listener(self, fn) -> None:
        try:
            self._listeners.remove(fn)
        except ValueError:
            pass

    def _notify(self) -> None:
        for fn in list(self._listeners):
            try:
                fn()
            except Exception:
                traceback.print_exc()

    # ----- control -----
    def trigger_refresh(self) -> None:
        self._refresh_event.set()

    def stop(self) -> None:
        self._stop_event.set()
        self._refresh_event.set()
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass

    # ----- worker -----
    def _refresh_once(self) -> None:
        try:
            if self.token is None:
                self.token = load_token()
            usage, self.token = fetch_usage(self.token)
            self.usage = usage
            self.last_error = None
            if self.icon is not None:
                self.icon.icon = usage_icon(usage)
                pct = usage.five_hour.utilization * 100
                self.icon.title = (
                    f"Claude Code\n"
                    f"5h: {int(round(pct))}%  ·  7d: {int(round(usage.seven_day.utilization*100))}%\n"
                    f"5h reset: {format_until(usage.five_hour.resets_at)}"
                )
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
            if self.icon is not None:
                self.icon.icon = error_icon()
                self.icon.title = f"Claude Code – error\n{self.last_error}"
        finally:
            self._notify()

    def worker_loop(self) -> None:
        while not self._stop_event.is_set():
            self._refresh_once()
            self._refresh_event.wait(timeout=REFRESH_INTERVAL_SECONDS)
            self._refresh_event.clear()
