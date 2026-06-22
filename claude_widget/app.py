"""Application entry point: wires the tray icon to AppState + popup."""

from __future__ import annotations

import sys
import threading
import tkinter as tk

import pystray

from .icons import loading_icon
from .popup import open_popup, PopupWindow
from .state import AppState


def _enable_system_trust_store() -> None:
    """Validate TLS against the OS certificate store instead of certifi's
    bundle. On corporate networks an SSL-inspection proxy re-signs HTTPS with
    a private root CA that IT installs into the Windows cert store but that
    certifi never sees, causing CERTIFICATE_VERIFY_FAILED. truststore patches
    ssl to use the platform store, where that CA is already trusted. Best
    effort: if truststore is unavailable we fall back to certifi silently.
    """
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:
        pass


def main() -> int:
    _enable_system_trust_store()
    state = AppState()

    # Hidden Tk root that lives on the main thread and owns the event loop.
    # All Toplevel popup windows will be children of this root so they share
    # the same Tk interpreter and event loop without threading issues.
    tk_root = tk.Tk()
    tk_root.withdraw()

    # Guard: only one popup at a time.
    _popup_open = threading.Event()

    def _do_open_popup() -> None:
        """Runs on the Tk main thread via after()."""
        if _popup_open.is_set():
            return
        _popup_open.set()
        PopupWindow(state, tk_root, on_close=_popup_open.clear)

    def on_open(icon, _item) -> None:
        tk_root.after(0, _do_open_popup)

    def on_refresh(icon, _item) -> None:
        state.trigger_refresh()

    def on_quit(icon, _item) -> None:
        state.stop()
        tk_root.after(0, tk_root.quit)

    menu = pystray.Menu(
        pystray.MenuItem("View details…", on_open, default=True),
        pystray.MenuItem("Refresh now", on_refresh),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit),
    )

    icon = pystray.Icon(
        "claude-usage",
        icon=loading_icon(),
        title="Claude Code – loading…",
        menu=menu,
    )
    state.icon = icon

    # pystray and worker both run in daemon threads; Tk mainloop owns main thread.
    threading.Thread(target=icon.run, daemon=True).start()
    threading.Thread(target=state.worker_loop, daemon=True).start()

    tk_root.mainloop()  # blocks until tk_root.quit() is called (on_quit)

    state.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
