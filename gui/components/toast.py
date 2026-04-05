"""
ToastManager — non-blocking toast notification overlay.

Shows a small pill-shaped message at the bottom-right of the window
for 3 seconds, then fades out.  Multiple toasts stack vertically.

Usage::

    toast = ToastManager(root_window)
    toast.show("Pipeline complete!", kind="success")
    toast.show("File not found",     kind="error")
    toast.show("Processing...",      kind="info")
"""
from __future__ import annotations

from typing import Literal

import customtkinter as ctk

Kind = Literal["info", "success", "warning", "error"]

KIND_COLORS: dict[Kind, str] = {
    "info":    "#1f6aa5",
    "success": "#437a22",
    "warning": "#b07a00",
    "error":   "#a13544",
}

KIND_ICONS: dict[Kind, str] = {
    "info":    "\u2139",
    "success": "\u2714",
    "warning": "\u26a0",
    "error":   "\u2718",
}

DURATION_MS  = 3000
FADE_STEPS   = 20
FADE_DELAY   = 15   # ms per fade step
TOAST_H      = 40
TOAST_W      = 320
MARGIN_R     = 16
MARGIN_B     = 16
GAP          = 8


class _Toast(ctk.CTkFrame):
    """A single toast notification frame."""

    def __init__(self, parent: ctk.CTk, message: str, kind: Kind, index: int) -> None:
        color = KIND_COLORS[kind]
        super().__init__(
            parent,
            width=TOAST_W,
            height=TOAST_H,
            corner_radius=TOAST_H // 2,
            fg_color=color,
        )
        self._index = index
        self._kind = kind          # store kind so fade never needs a reverse lookup
        self._alpha = 1.0
        self._base_color = self._hex_to_rgb(color)   # cache original RGB once

        icon = KIND_ICONS[kind]
        ctk.CTkLabel(
            self,
            text=f"{icon}  {message}",
            font=("Segoe UI", 12),
            text_color="#ffffff",
            anchor="w",
        ).pack(side="left", padx=14, pady=0, fill="both", expand=True)

        self._place(index)
        self.after(DURATION_MS, self._start_fade)

    def _place(self, index: int) -> None:
        parent = self.master
        pw = parent.winfo_width()  or 1080
        ph = parent.winfo_height() or 700
        x = pw - TOAST_W - MARGIN_R
        y = ph - MARGIN_B - TOAST_H - index * (TOAST_H + GAP)
        self.place(x=x, y=y, width=TOAST_W, height=TOAST_H)

    def reposition(self, index: int) -> None:
        self._index = index
        self._place(index)

    def _start_fade(self) -> None:
        self._fade_step(FADE_STEPS)

    def _fade_step(self, remaining: int) -> None:
        if remaining <= 0:
            self.destroy()
            return
        # Darken by ratio using the cached base RGB — no reverse lookup needed
        ratio = remaining / FADE_STEPS
        r, g, b = self._base_color
        fade_color = self._rgb_to_hex(
            int(r * ratio), int(g * ratio), int(b * ratio)
        )
        try:
            self.configure(fg_color=fade_color)
        except Exception:
            self.destroy()
            return
        self.after(FADE_DELAY, lambda: self._fade_step(remaining - 1))

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
        h = hex_color.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    @staticmethod
    def _rgb_to_hex(r: int, g: int, b: int) -> str:
        return f"#{r:02x}{g:02x}{b:02x}"


class ToastManager:
    """Manages a stack of active toasts anchored to the parent window."""

    def __init__(self, parent: ctk.CTk) -> None:
        self._parent = parent
        self._active: list[_Toast] = []

    def show(self, message: str, kind: Kind = "info") -> None:
        """Display a new toast and auto-dismiss it after DURATION_MS."""
        # Reposition existing toasts to make room
        for i, t in enumerate(self._active):
            t.reposition(len(self._active) - i)

        toast = _Toast(self._parent, message, kind, index=0)
        self._active.append(toast)
        toast.bind("<Destroy>", lambda e, t=toast: self._on_destroy(t))

    def _on_destroy(self, toast: _Toast) -> None:
        if toast in self._active:
            self._active.remove(toast)
        # Re-stack remaining
        for i, t in enumerate(reversed(self._active)):
            t.reposition(i)
