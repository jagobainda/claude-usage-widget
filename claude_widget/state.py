"""Shared application state and background refresh worker."""

from __future__ import annotations

import threading
import time
import traceback
from typing import Optional, TYPE_CHECKING

from .api import Usage, fetch_usage
from .auth import OAuthToken, RefreshTokenError, load_token
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

# How long the scheduler waits for a freshly dispatched fetch to publish its
# result before choosing the next interval. A fast outcome (HTTP error, refused
# connection) resolves in well under a second and the wait returns immediately;
# only a hung socket consumes the full grace, and that case is already bounded
# by the in-flight deadline above. Without this the interval was chosen from the
# *previous* cycle's result, so the first failure after a success always waited
# the full refresh interval instead of the short error backoff.
_RESULT_GRACE_SECONDS = 8.0


class AppState:
    def __init__(self) -> None:
        self.token: Optional[OAuthToken] = None
        self.usage: Optional[Usage] = None
        self.last_error: Optional[str] = None
        self.icon: Optional["pystray.Icon"] = None
        self._refresh_event = threading.Event()
        self._stop_event = threading.Event()
        # Set by a fetch when it publishes a result, so the scheduler can pick
        # the next interval from the actual outcome instead of the prior cycle.
        self._result_ready = threading.Event()
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
            summary = "  ·  ".join(
                f"{lim.short_label}: {int(round(lim.utilization * 100))}%"
                for lim in usage.limits
            )
            primary = usage.primary
            lines = ["Claude Code"]
            if summary:
                lines.append(summary)
            if primary is not None:
                lines.append(f"{primary.short_label} reset: {format_until(primary.resets_at)}")
            self.icon.title = "\n".join(lines)
        self._result_ready.set()
        self._notify()

    def _publish_error(self, msg: str) -> None:
        self.last_error = msg
        if self.icon is not None:
            self.icon.icon = error_icon()
            self.icon.title = f"Claude Code – error\n{msg}"
        self._result_ready.set()
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

        def finish_in_flight() -> bool:
            """Clear the in-flight flag iff this fetch is still the newest one.

            A superseded (zombie) fetch returns False so it neither touches the
            flag nor publishes its stale result.
            """
            with self._fetch_lock:
                is_latest = (my_seq == self._fetch_seq)
                if is_latest:
                    self._fetch_in_flight = False
                return is_latest

        def run() -> None:
            try:
                tok = self.token if self.token is not None else load_token()
                try:
                    usage, tok = fetch_usage(tok)
                except RefreshTokenError:
                    # The in-memory refresh token is stale — another client
                    # (the Claude Code CLI) likely rotated it on disk. Reload
                    # the credentials and try once more before giving up; this
                    # is what lets the widget self-heal from a 400 the same way
                    # it recovers from a dropped connection.
                    tok = load_token()
                    self.token = tok
                    usage, tok = fetch_usage(tok)
            except RefreshTokenError:
                # Reload didn't help: the stored refresh token is genuinely
                # dead, so retrying can't recover it — the user must re-auth.
                if finish_in_flight():
                    self._publish_error(
                        "Session expired. Sign in to Claude Code again."
                    )
                return
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                if finish_in_flight():
                    self._publish_error(f"{type(exc).__name__}: {exc}")
                return
            if finish_in_flight():
                self._publish_success(usage, tok)

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
            self._result_ready.clear()
            self._dispatch_fetch(force=force)

            # Wait briefly for this dispatch to publish, so the interval below
            # reflects its actual outcome rather than the previous cycle's. The
            # wait returns the instant a result lands (the common case); a hung
            # fetch is capped here and handled by the in-flight deadline.
            self._result_ready.wait(timeout=_RESULT_GRACE_SECONDS)

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
