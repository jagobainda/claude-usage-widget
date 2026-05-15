"""Shared application state and background refresh worker."""

from __future__ import annotations

import threading
import time
import traceback
from typing import Optional, TYPE_CHECKING

from .api import Usage, fetch_usage
from .auth import OAuthToken, load_token
from .config import REFRESH_INTERVAL_SECONDS
from .icons import error_icon, usage_icon
from .utils import format_until

if TYPE_CHECKING:
    import pystray


# If a fetch thread is still running after this many seconds we consider it
# hung (typically because the OS is blocked on DNS / WinHTTP after losing
# connectivity) and allow the scheduler to dispatch a fresh attempt while
# leaving the zombie thread to die on its own. It's a daemon thread so it
# will not keep the process alive.
_FETCH_DEADLINE_SECONDS = 30.0


class AppState:
    def __init__(self) -> None:
        self.token: Optional[OAuthToken] = None
        self.usage: Optional[Usage] = None
        self.last_error: Optional[str] = None
        self.icon: Optional["pystray.Icon"] = None
        self._refresh_event = threading.Event()
        self._stop_event = threading.Event()
        self._listeners: list = []
        # Fetch dispatch bookkeeping. A monotonically increasing sequence id
        # lets a late-arriving zombie fetch detect that it has been superseded
        # and skip publishing its (probably stale) result.
        self._fetch_lock = threading.Lock()
        self._fetch_in_flight = False
        self._fetch_started_at = 0.0
        self._fetch_seq = 0
        self._force_dispatch = False  # set by manual refresh

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
        # Manual refresh: bypass the in-flight guard so the user always gets
        # a new attempt even if a previous fetch is hung on a dead socket.
        self._force_dispatch = True
        self._refresh_event.set()

    def stop(self) -> None:
        self._stop_event.set()
        self._refresh_event.set()
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass

    # ----- fetch dispatch -----
    def _publish_success(self, usage: Usage, tok: OAuthToken) -> None:
        self.token = tok
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
        self._notify()

    def _publish_error(self, msg: str) -> None:
        self.last_error = msg
        if self.icon is not None:
            self.icon.icon = error_icon()
            self.icon.title = f"Claude Code – error\n{msg}"
        self._notify()

    def _dispatch_fetch(self, force: bool = False) -> None:
        """Start a fetch on a background thread. Returns immediately.

        If a previous fetch is still in-flight and within the deadline we
        skip (to avoid stacking duplicate requests). ``force=True`` (used by
        the manual refresh button) bypasses that guard.
        """
        with self._fetch_lock:
            now = time.monotonic()
            in_flight = self._fetch_in_flight and (now - self._fetch_started_at) < _FETCH_DEADLINE_SECONDS
            if in_flight and not force:
                return
            self._fetch_seq += 1
            my_seq = self._fetch_seq
            self._fetch_in_flight = True
            self._fetch_started_at = now

        def run() -> None:
            try:
                tok = self.token if self.token is not None else load_token()
                usage, tok = fetch_usage(tok)
                with self._fetch_lock:
                    is_latest = (my_seq == self._fetch_seq)
                    if is_latest:
                        self._fetch_in_flight = False
                if is_latest:
                    self._publish_success(usage, tok)
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                with self._fetch_lock:
                    is_latest = (my_seq == self._fetch_seq)
                    if is_latest:
                        self._fetch_in_flight = False
                if is_latest:
                    self._publish_error(f"{type(exc).__name__}: {exc}")

        threading.Thread(target=run, daemon=True, name=f"claude-fetch-{my_seq}").start()

    # ----- worker -----
    def worker_loop(self) -> None:
        """Scheduler. Never performs network I/O itself, so it stays
        responsive to the stop / manual-refresh events even if a previous
        fetch attempt is hung waiting on a dead socket."""
        error_backoff = 5
        while not self._stop_event.is_set():
            force = self._force_dispatch
            self._force_dispatch = False
            self._dispatch_fetch(force=force)

            # Pick wait interval based on the most recently published result.
            # When in error state we retry sooner (5 s, doubling up to the
            # normal interval) so we recover quickly once the network is back.
            if self.last_error is None:
                wait_s: float = REFRESH_INTERVAL_SECONDS
                error_backoff = 5
            else:
                wait_s = min(error_backoff, REFRESH_INTERVAL_SECONDS)
                error_backoff = min(error_backoff * 2, REFRESH_INTERVAL_SECONDS)

            self._refresh_event.wait(timeout=wait_s)
            self._refresh_event.clear()
