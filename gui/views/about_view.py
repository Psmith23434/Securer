"""
AboutView — version info, pipeline summary, and links.
"""
from __future__ import annotations

import customtkinter as ctk

from securer import __version__

STAGE_ROWS = [
    ("Stage 1a", "String Encryption",    "XOR-encrypts every string literal into bytes + lambda decryptor"),
    ("Stage 1b", "Name Mangling",         "Renames all user identifiers to _X{sha256} hashes"),
    ("Stage 1c", "Flow Flattening",       "Rewrites functions as while-True state machines"),
    ("Stage 1d", "Opaque Predicates",     "Injects always-true/false guards to defeat static analysis"),
    ("Stage 1e", "Dead Code Injection",   "Inserts realistic but unreachable code at 3 injection sites"),
    ("Stage 3",  "Runtime Shield",        "Anti-debug (Windows API + timing) + SHA-256 binary integrity"),
]


class AboutView(ctk.CTkFrame):
    """About and documentation view."""

    def __init__(self, parent: ctk.CTkFrame) -> None:
        super().__init__(parent, fg_color="transparent")
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        # Header
        ctk.CTkLabel(
            self,
            text="About Securer",
            font=("Segoe UI", 20, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=24, pady=(24, 2))

        ctk.CTkLabel(
            self,
            text=f"Version {__version__}  \u2014  Python source obfuscation pipeline",
            font=("Segoe UI", 12),
            text_color=("#666666", "#888888"),
            anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=24, pady=(0, 20))

        # Architecture diagram (monospace label)
        diag_text = (
            "  Your .py source\n"
            "       \u2502\n"
            "  \u250c\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2510\n"
            "  \u2502  Stage 1: Obfuscate \u2502\n"
            "  \u2502  1a \u2192 1b \u2192 1c \u2192 1d \u2192 1e \u2502\n"
            "  \u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2518\n"
            "       \u2502  mangled .py\n"
            "  \u250c\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2510\n"
            "  \u2502  Stage 2: Nuitka   \u2502 (external)\n"
            "  \u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2518\n"
            "       \u2502  .exe\n"
            "  \u250c\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2510\n"
            "  \u2502  Stage 3: Shield   \u2502\n"
            "  \u2502  anti-debug + hash \u2502\n"
            "  \u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2518\n"
        )
        diag_frame = ctk.CTkFrame(
            self,
            fg_color=("#f0f0f0", "#1a1a1a"),
            corner_radius=10,
        )
        diag_frame.grid(row=2, column=0, sticky="w", padx=24, pady=(0, 16))
        ctk.CTkLabel(
            diag_frame,
            text=diag_text,
            font=("Consolas", 11),
            justify="left",
            anchor="w",
        ).pack(padx=16, pady=12)

        # Stage table
        ctk.CTkLabel(
            self,
            text="Pipeline Stages",
            font=("Segoe UI", 14, "bold"),
            anchor="w",
        ).grid(row=3, column=0, sticky="w", padx=24, pady=(0, 8))

        table = ctk.CTkFrame(
            self,
            fg_color=("#f5f5f5", "#1e1e1e"),
            corner_radius=10,
        )
        table.grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 16))
        table.grid_columnconfigure(2, weight=1)

        for i, (stage, name, desc) in enumerate(STAGE_ROWS):
            bg = ("#ffffff", "#252525") if i % 2 == 0 else ("#f5f5f5", "#1e1e1e")
            row_frame = ctk.CTkFrame(table, fg_color=bg, corner_radius=0)
            row_frame.grid(row=i, column=0, columnspan=3, sticky="ew")
            row_frame.grid_columnconfigure(2, weight=1)

            ctk.CTkLabel(
                row_frame,
                text=stage,
                font=("Consolas", 11, "bold"),
                text_color=("#1f6aa5", "#4f98a3"),
                width=72,
                anchor="w",
            ).grid(row=0, column=0, sticky="w", padx=(14, 0), pady=8)

            ctk.CTkLabel(
                row_frame,
                text=name,
                font=("Segoe UI", 11, "bold"),
                width=150,
                anchor="w",
            ).grid(row=0, column=1, sticky="w", padx=(8, 0))

            ctk.CTkLabel(
                row_frame,
                text=desc,
                font=("Segoe UI", 11),
                text_color=("#666666", "#999999"),
                anchor="w",
            ).grid(row=0, column=2, sticky="w", padx=(8, 14))

        # Footer
        ctk.CTkLabel(
            self,
            text="Private — do not distribute.  Built with CustomTkinter + Nuitka.",
            font=("Segoe UI", 11),
            text_color=("#999999", "#555555"),
            anchor="w",
        ).grid(row=5, column=0, sticky="w", padx=24, pady=(8, 24))
