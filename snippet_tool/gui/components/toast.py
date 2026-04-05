"""
Non-blocking toast notification component.
Shows a brief message that fades out automatically.

Usage:
    toast = ToastManager(root_window)
    toast.show("Copied to clipboard!", kind="success")
"""
import customtkinter as ctk
from snippet_tool.gui.theme import (
    COLORS, FONT_BODY, SIZE_SM,
    SP3, SP4, SP6,
    RADIUS_LG,
)

KIND_COLORS = {
    "success": ("success",       "text_inverse"),
    "error":   ("error",          "text_inverse"),
    "warning": ("warning",        "text_inverse"),
    "info":    ("primary",        "text_inverse"),
}


class ToastManager:
    """
    Manages a stack of toast notifications anchored to the bottom-right
    of the parent window.
    """

    def __init__(self, root: ctk.CTk):
        self._root = root
        self._active: list["_Toast"] = []

    def show(self, message: str, kind: str = "info", duration_ms: int = 2800):
        mode = ctk.get_appearance_mode().lower()
        c = COLORS[mode]
        bg_key, fg_key = KIND_COLORS.get(kind, KIND_COLORS["info"])
        t = _Toast(
            self._root,
            message=message,
            bg_color=c[bg_key],
            text_color=c[fg_key],
            on_done=self._remove,
            duration_ms=duration_ms,
            offset_index=len(self._active),
        )
        self._active.append(t)
        t.show()

    def _remove(self, toast):
        if toast in self._active:
            self._active.remove(toast)
        # Re-position remaining toasts
        for i, t in enumerate(self._active):
            t.reposition(i)


class _Toast(ctk.CTkToplevel):
    _MARGIN_RIGHT  = 24
    _MARGIN_BOTTOM = 24
    _HEIGHT        = 44
    _GAP           = 10
    _FADE_STEPS    = 20
    _FADE_MS       = 30

    def __init__(self, root, message, bg_color, text_color,
                 on_done, duration_ms, offset_index):
        super().__init__(root)
        self._root       = root
        self._on_done    = on_done
        self._duration   = duration_ms
        self._offset     = offset_index
        self._alpha      = 1.0

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.0)
        self.configure(fg_color=bg_color)

        label = ctk.CTkLabel(
            self,
            text=message,
            font=(FONT_BODY, SIZE_SM),
            text_color=text_color,
            fg_color="transparent",
        )
        label.pack(padx=SP6, pady=SP3)

        self.update_idletasks()
        self._w = max(self.winfo_reqwidth(), 220)
        self._position()

    def _position(self):
        rw = self._root.winfo_width()
        rh = self._root.winfo_height()
        rx = self._root.winfo_rootx()
        ry = self._root.winfo_rooty()
        x = rx + rw - self._w - self._MARGIN_RIGHT
        y = ry + rh - self._HEIGHT - self._MARGIN_BOTTOM - self._offset * (self._HEIGHT + self._GAP)
        self.geometry(f"{self._w}x{self._HEIGHT}+{x}+{y}")

    def show(self):
        self._fade_in()

    def reposition(self, new_index: int):
        self._offset = new_index
        self._position()

    def _fade_in(self, step=0):
        alpha = step / self._FADE_STEPS
        self.attributes("-alpha", alpha)
        if step < self._FADE_STEPS:
            self.after(self._FADE_MS, lambda: self._fade_in(step + 1))
        else:
            self.after(self._duration, self._fade_out)

    def _fade_out(self, step=0):
        alpha = 1.0 - step / self._FADE_STEPS
        self.attributes("-alpha", max(0.0, alpha))
        if step < self._FADE_STEPS:
            self.after(self._FADE_MS, lambda: self._fade_out(step + 1))
        else:
            self._on_done(self)
            self.destroy()
