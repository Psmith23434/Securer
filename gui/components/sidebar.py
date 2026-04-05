"""
Sidebar component.

A fixed-width left navigation panel with:
  - App logo + name at the top
  - Navigation buttons (icon + label)
  - Collapse/expand toggle at the bottom
  - Smooth width animation via CTk
"""
from __future__ import annotations

from typing import Callable

import customtkinter as ctk

# Nav item definitions: (view_key, icon_unicode, label)
NAV_ITEMS = [
    ("pipeline", "\u26a1",  "Pipeline"),
    ("settings", "\u2699",  "Settings"),
    ("about",    "\u24d8",  "About"),
]

COLOR_ACTIVE   = ("#1f538d", "#1f6aa5")   # CTk blue tones
COLOR_INACTIVE = "transparent"             # must be a plain string, not a tuple
TEXT_ACTIVE    = ("#ffffff", "#ffffff")
TEXT_INACTIVE  = ("#555555", "#aaaaaa")

SIDEBAR_W_EXPANDED  = 200
SIDEBAR_W_COLLAPSED = 56
ANIM_STEPS = 8
ANIM_DELAY = 12   # ms per step


class Sidebar(ctk.CTkFrame):
    """Left navigation sidebar with collapse animation."""

    def __init__(
        self,
        parent: ctk.CTk,
        nav_callback: Callable[[str], None],
    ) -> None:
        super().__init__(
            parent,
            width=SIDEBAR_W_EXPANDED,
            corner_radius=0,
            fg_color=("#e8e8e8", "#1a1a1a"),
        )
        self.grid_propagate(False)
        self._nav_cb  = nav_callback
        self._active  = ""
        self._expanded = True
        self._anim_id  = None

        self._build()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # --- Logo row ---
        self._logo_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._logo_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=(16, 8))
        self._logo_frame.grid_columnconfigure(1, weight=1)

        self._logo_icon = ctk.CTkLabel(
            self._logo_frame,
            text="\U0001f512",
            font=("Segoe UI Emoji", 22),
            width=36,
        )
        self._logo_icon.grid(row=0, column=0, padx=(4, 0))

        self._logo_label = ctk.CTkLabel(
            self._logo_frame,
            text="Securer",
            font=("Segoe UI", 16, "bold"),
            anchor="w",
        )
        self._logo_label.grid(row=0, column=1, sticky="w", padx=(8, 0))

        # Divider
        ctk.CTkFrame(self, height=1, fg_color=("#cccccc", "#2d2d2d")).grid(
            row=0, column=0, sticky="sew", padx=12, pady=(56, 0)
        )

        # --- Nav buttons ---
        self._nav_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._nav_frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=8)
        self._nav_frame.grid_columnconfigure(0, weight=1)

        self._buttons: dict[str, ctk.CTkButton] = {}
        for i, (key, icon, label) in enumerate(NAV_ITEMS):
            btn = ctk.CTkButton(
                self._nav_frame,
                text=f"  {icon}   {label}",
                anchor="w",
                height=40,
                corner_radius=8,
                fg_color=COLOR_INACTIVE,
                text_color=TEXT_INACTIVE,
                hover_color=("#d0d0d0", "#2a2a2a"),
                font=("Segoe UI", 13),
                command=lambda k=key: self._nav_cb(k),
            )
            btn.grid(row=i, column=0, sticky="ew", pady=2)
            self._buttons[key] = btn

        # --- Collapse toggle ---
        self._toggle_btn = ctk.CTkButton(
            self,
            text="\u25c4",
            width=36,
            height=36,
            corner_radius=8,
            fg_color="transparent",
            hover_color=("#d0d0d0", "#2a2a2a"),
            font=("Segoe UI", 14),
            command=self._toggle_collapse,
        )
        self._toggle_btn.grid(row=2, column=0, sticky="e", padx=10, pady=12)

    # ------------------------------------------------------------------
    # Active state
    # ------------------------------------------------------------------

    def set_active(self, key: str) -> None:
        self._active = key
        for k, btn in self._buttons.items():
            if k == key:
                btn.configure(fg_color=COLOR_ACTIVE, text_color=TEXT_ACTIVE)
            else:
                btn.configure(fg_color=COLOR_INACTIVE, text_color=TEXT_INACTIVE)

    # ------------------------------------------------------------------
    # Collapse animation
    # ------------------------------------------------------------------

    def _toggle_collapse(self) -> None:
        if self._anim_id is not None:
            return  # animation in progress
        self._expanded = not self._expanded
        target = SIDEBAR_W_EXPANDED if self._expanded else SIDEBAR_W_COLLAPSED
        current = self.winfo_width()
        step = (target - current) / ANIM_STEPS
        self._toggle_btn.configure(
            text="\u25c4" if self._expanded else "\u25ba"
        )
        self._animate(current, target, step, ANIM_STEPS)

    def _animate(self, current: float, target: int, step: float, remaining: int) -> None:
        if remaining <= 0:
            self.configure(width=target)
            self._anim_id = None
            self._update_label_visibility()
            return
        new_w = int(current + step)
        self.configure(width=new_w)
        self._anim_id = self.after(
            ANIM_DELAY,
            lambda: self._animate(new_w, target, step, remaining - 1),
        )

    def _update_label_visibility(self) -> None:
        """Show/hide text labels based on expanded state."""
        for key, btn in self._buttons.items():
            icon = next(i for k, i, _ in NAV_ITEMS if k == key)
            label = next(l for k, _, l in NAV_ITEMS if k == key)
            if self._expanded:
                btn.configure(text=f"  {icon}   {label}")
            else:
                btn.configure(text=f" {icon}")
        if self._expanded:
            self._logo_label.grid()
        else:
            self._logo_label.grid_remove()
