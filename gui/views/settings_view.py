"""
SettingsView — seed, output directory, and theme preferences.
"""
from __future__ import annotations

from tkinter import filedialog
from typing import Callable

import customtkinter as ctk


class SettingsView(ctk.CTkFrame):
    """Application settings panel."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        state: dict,
        on_theme_change: Callable[[str], None],
    ) -> None:
        super().__init__(parent, fg_color="transparent")
        self._state = state
        self._on_theme_change = on_theme_change
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        # Header
        ctk.CTkLabel(
            self,
            text="Settings",
            font=("Segoe UI", 20, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=24, pady=(24, 4))

        ctk.CTkLabel(
            self,
            text="Configure pipeline defaults and application preferences.",
            font=("Segoe UI", 12),
            text_color=("#666666", "#888888"),
            anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=24, pady=(0, 20))

        # Settings card
        card = ctk.CTkFrame(
            self,
            fg_color=("#f5f5f5", "#1e1e1e"),
            corner_radius=12,
        )
        card.grid(row=2, column=0, sticky="ew", padx=24, pady=0)
        card.grid_columnconfigure(1, weight=1)

        row = 0

        # --- Default seed ---
        self._add_label(card, "Default seed", row)
        self._seed_entry = ctk.CTkEntry(
            card, width=100, height=34, font=("Consolas", 12)
        )
        self._seed_entry.insert(0, str(self._state.get("seed", 42)))
        self._seed_entry.grid(row=row, column=1, sticky="w", padx=12, pady=10)
        row += 1

        self._add_divider(card, row); row += 1

        # --- Output directory ---
        self._add_label(card, "Default output dir", row)
        out_frame = ctk.CTkFrame(card, fg_color="transparent")
        out_frame.grid(row=row, column=1, sticky="ew", padx=12, pady=10)
        out_frame.grid_columnconfigure(0, weight=1)

        self._outdir_entry = ctk.CTkEntry(
            out_frame,
            placeholder_text="Same as input file (default)",
            height=34,
            font=("Segoe UI", 12),
        )
        if self._state.get("output_dir"):
            self._outdir_entry.insert(0, self._state["output_dir"])
        self._outdir_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(
            out_frame,
            text="Browse",
            width=72,
            height=34,
            font=("Segoe UI", 12),
            command=self._browse_outdir,
        ).grid(row=0, column=1)
        row += 1

        self._add_divider(card, row); row += 1

        # --- Theme ---
        self._add_label(card, "Appearance", row)
        theme_frame = ctk.CTkFrame(card, fg_color="transparent")
        theme_frame.grid(row=row, column=1, sticky="w", padx=12, pady=10)

        self._theme_var = ctk.StringVar(
            value=self._state.get("theme", "dark")
        )
        for theme_val, theme_lbl in [("dark", "Dark"), ("light", "Light"), ("system", "System")]:
            ctk.CTkRadioButton(
                theme_frame,
                text=theme_lbl,
                variable=self._theme_var,
                value=theme_val,
                command=lambda: self._on_theme_change(self._theme_var.get()),
            ).pack(side="left", padx=(0, 16))
        row += 1

        # --- Save button ---
        ctk.CTkButton(
            self,
            text="Save Settings",
            height=40,
            width=160,
            font=("Segoe UI", 13, "bold"),
            command=self._save,
        ).grid(row=3, column=0, sticky="w", padx=24, pady=16)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _add_label(self, parent: ctk.CTkFrame, text: str, row: int) -> None:
        ctk.CTkLabel(
            parent,
            text=text,
            font=("Segoe UI", 12, "bold"),
            anchor="w",
            width=160,
        ).grid(row=row, column=0, sticky="w", padx=(16, 0), pady=10)

    def _add_divider(self, parent: ctk.CTkFrame, row: int) -> None:
        ctk.CTkFrame(
            parent,
            height=1,
            fg_color=("#e0e0e0", "#2d2d2d"),
        ).grid(row=row, column=0, columnspan=2, sticky="ew", padx=12)

    def _browse_outdir(self) -> None:
        path = filedialog.askdirectory(title="Select default output directory")
        if path:
            self._outdir_entry.delete(0, "end")
            self._outdir_entry.insert(0, path)

    def _save(self) -> None:
        try:
            self._state["seed"] = int(self._seed_entry.get().strip())
        except ValueError:
            pass
        self._state["output_dir"] = self._outdir_entry.get().strip()
        self._state["theme"] = self._theme_var.get()
        self._on_theme_change(self._state["theme"])
