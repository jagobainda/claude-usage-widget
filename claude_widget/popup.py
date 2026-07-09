"""Modern dark popup window with a custom title bar."""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING, Optional

from PIL import ImageTk

from .config import Theme, status_color_hex
from .icons import claude_logo
from .utils import format_until

if TYPE_CHECKING:
    from .api import LimitUsage, Usage
    from .state import AppState


# ---------------------------------------------------------------------------
# Reusable widgets
# ---------------------------------------------------------------------------

class HoverButton(tk.Label):
    """Flat label-based button with hover/press feedback (dark friendly)."""

    def __init__(
        self,
        master: tk.Misc,
        text: str,
        command,
        *,
        bg: str = Theme.BTN_BG,
        bg_hover: str = Theme.BTN_BG_HOV,
        fg: str = Theme.BTN_FG,
        font=Theme.FONT_BODY,
        padx: int = 14,
        pady: int = 6,
    ) -> None:
        super().__init__(
            master,
            text=text,
            bg=bg,
            fg=fg,
            font=font,
            padx=padx,
            pady=pady,
            cursor="hand2",
            borderwidth=0,
            highlightthickness=0,
        )
        self._bg = bg
        self._bg_hover = bg_hover
        self._command = command
        self.bind("<Enter>", lambda _e: self.configure(bg=self._bg_hover))
        self.bind("<Leave>", lambda _e: self.configure(bg=self._bg))
        self.bind("<Button-1>", self._on_click)

    def _on_click(self, _event) -> None:
        if callable(self._command):
            self._command()


class RoundedProgress(tk.Canvas):
    """Canvas-based rounded progress bar."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        width: int = 360,
        height: int = 10,
        track: str = Theme.TRACK,
        fill: str = Theme.OK,
    ) -> None:
        super().__init__(
            master,
            width=width,
            height=height,
            bg=master["bg"],
            highlightthickness=0,
            borderwidth=0,
        )
        self._bar_w = width
        self._bar_h = height
        self._track = track
        self._fill = fill
        self._value = 0.0
        # Draw after the Tcl widget command is registered (safe with Toplevel).
        self.after_idle(self._draw)

    def _round_rect(self, x1, y1, x2, y2, r, **kwargs):
        if x2 - x1 < 2 * r:
            r = max(0, (x2 - x1) // 2)
        if y2 - y1 < 2 * r:
            r = max(0, (y2 - y1) // 2)
        if r <= 0:
            return self.create_rectangle(x1, y1, x2, y2, **kwargs)
        points = [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)

    def set(self, value: float, fill: Optional[str] = None) -> None:
        self._value = max(0.0, min(1.0, value))
        if fill is not None:
            self._fill = fill
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        r = self._bar_h // 2
        self._round_rect(0, 0, self._bar_w, self._bar_h, r, fill=self._track, outline="")
        if self._value > 0:
            w = max(self._bar_h, int(self._bar_w * self._value))
            self._round_rect(0, 0, w, self._bar_h, r, fill=self._fill, outline="")


# ---------------------------------------------------------------------------
# Popup window
# ---------------------------------------------------------------------------

class PopupWindow:
    WIDTH = 380
    PAD = 16

    def __init__(self, state: "AppState", master: tk.Tk, on_close=None) -> None:
        self.state = state
        self._on_close = on_close
        # Use Toplevel so this window shares the hidden root's event loop
        # (which runs on the main thread). Using tk.Tk() from a non-main
        # thread causes silent failures on Windows.
        self.root = tk.Toplevel(master)
        self.root.geometry("+9999+9999")  # off-screen until _show() moves it
        self.root.title("Claude Code – Usage")
        self.root.configure(bg=Theme.BG)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)

        # Outer 1-px border container.
        self.outer = tk.Frame(self.root, bg=Theme.BORDER)
        self.outer.pack(fill="both", expand=True)
        self.body = tk.Frame(self.outer, bg=Theme.BG)
        self.body.pack(fill="both", expand=True, padx=1, pady=1)

        self._icon_imgref: Optional[ImageTk.PhotoImage] = None
        self._title_icon_label: Optional[tk.Label] = None

        self._build_titlebar()
        self.content = tk.Frame(self.body, bg=Theme.BG)
        self.content.pack(fill="both", expand=True, padx=self.PAD, pady=(8, self.PAD))

        # Cards / labels (created lazily in _render, one card per usage limit).
        self._content_widgets: list[tk.Widget] = []
        # Per-card (pct_lbl, bar, reset_lbl), aligned with usage.limits order.
        self._cards: list[tuple[tk.Label, RoundedProgress, tk.Label]] = []
        # Limit kinds currently rendered, so we only rebuild when the set of
        # limits changes rather than on every value refresh.
        self._rendered_keys: tuple[str, ...] = ()
        self._fetched_label: Optional[tk.Label] = None
        self._error_label: Optional[tk.Label] = None

        self._render()

        # Live updates from state.
        self._listener = self._on_state_change
        self.state.add_listener(self._listener)

        # Reset countdown ticker.
        self._tick_job: Optional[str] = None
        self._schedule_tick()

        # Bindings.
        self.root.bind("<Escape>", lambda _e: self.close())
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        # Do the final placement after mainloop starts (1 ms delay) so that
        # root.update() is NOT called inside __init__. Calling update() here
        # causes Windows to process pending events including a spurious
        # WM_CLOSE that overrideredirect windows receive on Windows, which
        # immediately destroys the window before it is ever shown.
        self.root.after(1, self._show)

    # ------------------------------------------------------------------ build

    def _build_titlebar(self) -> None:
        bar = tk.Frame(self.body, bg=Theme.TITLEBAR, height=36)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        # Icon (the numeric tray icon, scaled).
        self._title_icon_label = tk.Label(bar, bg=Theme.TITLEBAR, bd=0)
        self._title_icon_label.pack(side="left", padx=(10, 8), pady=4)
        self._update_title_icon()

        title = tk.Label(
            bar,
            text="Claude Code · Usage",
            bg=Theme.TITLEBAR,
            fg=Theme.TEXT,
            font=Theme.FONT_TITLE,
        )
        title.pack(side="left")

        # Window controls.
        close_btn = HoverButton(
            bar,
            text="✕",
            command=self.close,
            bg=Theme.TITLEBAR,
            bg_hover=Theme.ACCENT_HOV,
            fg=Theme.ACCENT,
            font=(Theme.FONT_FAMILY, 11, "bold"),
            padx=12,
            pady=8,
        )
        close_btn.pack(side="right")

        refresh_btn = HoverButton(
            bar,
            text="⟳",
            command=self._on_refresh,
            bg=Theme.TITLEBAR,
            bg_hover=Theme.BTN_BG_HOV,
            fg=Theme.TEXT_MUTED,
            font=(Theme.FONT_FAMILY, 11, "bold"),
            padx=10,
            pady=8,
        )
        refresh_btn.pack(side="right")

        # Drag-to-move on title bar (icon + title area).
        for w in (bar, title, self._title_icon_label):
            w.bind("<ButtonPress-1>", self._start_move)
            w.bind("<B1-Motion>", self._do_move)

    def _build_card(self, title_text: str) -> tuple[tk.Frame, tk.Label, tk.Label, RoundedProgress, tk.Label]:
        card = tk.Frame(self.content, bg=Theme.CARD)
        card.pack(fill="x", pady=(0, 10))
        inner = tk.Frame(card, bg=Theme.CARD)
        inner.pack(fill="x", padx=14, pady=12)

        head = tk.Frame(inner, bg=Theme.CARD)
        head.pack(fill="x")
        title_lbl = tk.Label(
            head,
            text=title_text,
            bg=Theme.CARD,
            fg=Theme.ACCENT,
            font=Theme.FONT_HEAD,
        )
        title_lbl.pack(side="left")
        pct_lbl = tk.Label(
            head,
            text="—",
            bg=Theme.CARD,
            fg=Theme.TEXT,
            font=Theme.FONT_PCT,
        )
        pct_lbl.pack(side="right")

        bar = RoundedProgress(inner, width=self.WIDTH - 2 * self.PAD - 28, height=10)
        bar.pack(fill="x", pady=(10, 8))

        reset_lbl = tk.Label(
            inner,
            text="Resets in —",
            bg=Theme.CARD,
            fg=Theme.TEXT_MUTED,
            font=Theme.FONT_BODY,
            anchor="w",
        )
        reset_lbl.pack(fill="x")

        return card, title_lbl, pct_lbl, bar, reset_lbl

    # ---------------------------------------------------------------- render

    def _clear_content(self) -> None:
        for w in self._content_widgets:
            w.destroy()
        self._content_widgets.clear()
        self._cards.clear()
        self._rendered_keys = ()
        self._fetched_label = None
        self._error_label = None

    def _render(self) -> None:
        self._clear_content()
        usage = self.state.usage
        err = self.state.last_error

        if usage is None:
            placeholder = tk.Label(
                self.content,
                text="Loading usage data…" if not err else "Could not fetch usage data.",
                bg=Theme.BG,
                fg=Theme.TEXT,
                font=Theme.FONT_HEAD,
                anchor="w",
            )
            placeholder.pack(fill="x", pady=(4, 6))
            self._content_widgets.append(placeholder)
            if err:
                self._error_label = tk.Label(
                    self.content,
                    text=str(err),
                    bg=Theme.BG,
                    fg=Theme.DANGER,
                    font=Theme.FONT_BODY,
                    wraplength=self.WIDTH - 2 * self.PAD,
                    justify="left",
                    anchor="w",
                )
                self._error_label.pack(fill="x", pady=(0, 6))
                self._content_widgets.append(self._error_label)
        else:
            for lim in usage.limits:
                card, _title, pct_lbl, bar, reset_lbl = self._build_card(lim.label)
                self._content_widgets.append(card)
                self._cards.append((pct_lbl, bar, reset_lbl))
            self._rendered_keys = tuple(lim.kind for lim in usage.limits)

            self._fetched_label = tk.Label(
                self.content,
                text="",
                bg=Theme.BG,
                fg=Theme.TEXT_DIM,
                font=Theme.FONT_SMALL,
                anchor="w",
            )
            self._fetched_label.pack(fill="x", pady=(2, 0))
            self._content_widgets.append(self._fetched_label)

            self._update_values(usage)

        # Make sure window resizes to fit content.
        self.root.update_idletasks()

    def _update_values(self, usage: "Usage") -> None:
        for (pct_lbl, bar, reset_lbl), lim in zip(self._cards, usage.limits):
            self._set_window_values(lim, pct_lbl, bar, reset_lbl)
        if self._fetched_label is not None:
            ts = usage.fetched_at.astimezone().strftime("%H:%M:%S")
            self._fetched_label.configure(text=f"Updated · {ts}")

    def _set_window_values(
        self,
        win: "LimitUsage",
        pct_lbl: Optional[tk.Label],
        bar: Optional[RoundedProgress],
        reset_lbl: Optional[tk.Label],
    ) -> None:
        if pct_lbl is None or bar is None or reset_lbl is None:
            return
        pct = win.utilization
        color = status_color_hex(pct)
        pct_lbl.configure(text=f"{int(round(pct * 100))}%", fg=color)
        bar.set(min(1.0, pct), fill=color)
        reset_lbl.configure(text=f"Resets in {format_until(win.resets_at)}")

    def _update_title_icon(self) -> None:
        # Always show the Claude brand mark in the title bar.
        img = claude_logo(size=20)
        self._icon_imgref = ImageTk.PhotoImage(img)
        if self._title_icon_label is not None:
            self._title_icon_label.configure(image=self._icon_imgref)

    # --------------------------------------------------------------- events

    def _on_state_change(self) -> None:
        # Called from worker thread → marshal to Tk thread.
        try:
            self.root.after(0, self._refresh_ui)
        except Exception:
            pass

    def _refresh_ui(self) -> None:
        try:
            self._update_title_icon()
        except Exception:
            pass
        # Rebuild when the set of limits changes (first data, or a limit
        # appearing/disappearing — e.g. a scoped model window activating);
        # otherwise just refresh the values in place.
        usage = self.state.usage
        keys = tuple(lim.kind for lim in usage.limits) if usage is not None else ()
        if keys != self._rendered_keys:
            self._render()
        elif usage is not None:
            self._update_values(usage)

    def _schedule_tick(self) -> None:
        # Refresh "resets in …" countdown every 30s.
        if self.state.usage is not None:
            self._update_values(self.state.usage)
        self._tick_job = self.root.after(30_000, self._schedule_tick)

    def _on_refresh(self) -> None:
        self.state.trigger_refresh()

    # ----- dragging -----
    def _start_move(self, event) -> None:
        self._drag_x = event.x_root - self.root.winfo_x()
        self._drag_y = event.y_root - self.root.winfo_y()

    def _do_move(self, event) -> None:
        x = event.x_root - getattr(self, "_drag_x", 0)
        y = event.y_root - getattr(self, "_drag_y", 0)
        self.root.geometry(f"+{x}+{y}")

    # ----- placement / lifecycle -----
    def _show(self) -> None:
        """Called via after(1) – runs inside the event loop, safe to call update_idletasks."""
        self._place_window()
        self.root.lift()
        self.root.focus_force()

    def _place_window(self) -> None:
        self.root.update_idletasks()
        w = max(self.WIDTH, self.root.winfo_reqwidth())
        h = max(1, self.root.winfo_reqheight())
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = max(0, sw - w - 20)
        y = max(0, sh - h - 60)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def close(self) -> None:
        try:
            self.state.remove_listener(self._listener)
        except Exception:
            pass
        if self._tick_job is not None:
            try:
                self.root.after_cancel(self._tick_job)
            except Exception:
                pass
        if self._on_close is not None:
            try:
                self._on_close()
            except Exception:
                pass
        try:
            self.root.destroy()
        except Exception:
            pass


def open_popup(state: "AppState", master: tk.Tk) -> None:
    """Create the popup Toplevel on the calling thread (must be the Tk main thread)."""
    PopupWindow(state, master)
