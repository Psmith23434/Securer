"""
LogPanel — scrollable real-time log output widget.

Features:
  - Color-coded log levels: INFO (default), SUCCESS (green), WARNING (amber), ERROR (red)
  - Auto-scroll to bottom on new entries
  - Clear button
  - Line limit (default 500) to prevent unbounded memory growth
  - thread-safe append via .after() scheduling
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Optional

import customtkinter as ctk


class LogLevel(Enum):
    INFO    = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR   = "error"


# Color map: (light_mode_color, dark_mode_color)
LEVEL_COLORS: dict[LogLevel, str] = {
    LogLevel.INFO:    "#cccccc",
    LogLevel.SUCCESS: "#6daa45",
    LogLevel.WARNING: "#e8af34",
    LogLevel.ERROR:   "#dd6974",
}

LEVEL_PREFIXES: dict[LogLevel, str] = {
    LogLevel.INFO:    "  ",
    LogLevel.SUCCESS: "\u2714 ",
    LogLevel.WARNING: "\u26a0 ",
    LogLevel.ERROR:   "\u2718 ",
}

MAX_LINES = 500


class LogPanel(ctk.CTkFrame):
    """Scrollable log output panel with color-coded levels."""

    def __init__(self, parent: ctk.CTkBaseClass, **kwargs) -> None:
        kwargs.setdefault("fg_color", ("#f0f0f0", "#111111"))
        kwargs.setdefault("corner_radius", 8)
        super().__init__(parent, **kwargs)

        self._lines: list[str] = []
        self._build()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Header row
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 0))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Build Log",
            font=("Segoe UI", 12, "bold"),
            text_color=("#444444", "#888888"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        self._clear_btn = ctk.CTkButton(
            header,
            text="Clear",
            width=52,
            height=24,
            font=("Segoe UI", 11),
            fg_color="transparent",
            border_width=1,
            border_color=("#cccccc", "#444444"),
            text_color=("#666666", "#999999"),
            hover_color=("#e0e0e0", "#2a2a2a"),
            command=self.clear,
        )
        self._clear_btn.grid(row=0, column=1, sticky="e")

        # Text widget (read-only)
        self._text = ctk.CTkTextbox(
            self,
            font=("Consolas", 12),
            wrap="word",
            state="disabled",
            fg_color=("#f8f8f8", "#0d0d0d"),
            text_color=("#333333", "#cccccc"),
            border_width=0,
            corner_radius=0,
        )
        self._text.grid(row=1, column=0, sticky="nsew", padx=0, pady=(4, 0))
        self.grid_rowconfigure(1, weight=1)

        # Configure text tags for colors
        for level, color in LEVEL_COLORS.items():
            self._text._textbox.tag_configure(level.value, foreground=color)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log(self, message: str, level: LogLevel = LogLevel.INFO) -> None:
        """Append a log line (thread-safe via .after)."""
        self.after(0, self._append, message, level)

    def clear(self) -> None:
        """Remove all log entries."""
        self._lines.clear()
        self._text.configure(state="normal")
        self._text._textbox.delete("1.0", "end")
        self._text.configure(state="disabled")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _append(self, message: str, level: LogLevel) -> None:
        timestamp = time.strftime("%H:%M:%S")
        prefix = LEVEL_PREFIXES[level]
        line = f"{timestamp}  {prefix}{message}\n"
        self._lines.append(line)

        # Enforce line limit
        if len(self._lines) > MAX_LINES:
            self._lines = self._lines[-MAX_LINES:]
            self._text.configure(state="normal")
            self._text._textbox.delete("1.0", "end")
            for stored in self._lines:
                self._text._textbox.insert("end", stored)
            self._text.configure(state="disabled")
        else:
            self._text.configure(state="normal")
            self._text._textbox.insert("end", line, level.value)
            self._text.configure(state="disabled")

        # Auto-scroll
        self._text._textbox.see("end")
