"""
SecurerApp — root CustomTkinter window.

Responsibilities:
  - Initialise CTk theme and font scale
  - Build the two-column layout: sidebar (fixed) + content area (flex)
  - Own the in-memory app state dict shared across views
  - Route sidebar nav events to view switches

Drag-and-drop:
  tkinterdnd2 cannot safely use multiple inheritance with ctk.CTk because
  both subclass tk.Tk and the MRO breaks CTk’s scaling init.
  Instead we call TkinterDnD’s internal _require() on the already-constructed
  CTk instance — this is the same thing TkinterDnD.Tk.__init__ does, but
  without touching the class hierarchy.
  Falls back silently to plain ctk.CTk when tkinterdnd2 is absent.
"""
from __future__ import annotations

from pathlib import Path

import customtkinter as ctk

from gui.components.sidebar import Sidebar
from gui.components.toast import ToastManager
from gui.views.pipeline_view import PipelineView
from gui.views.settings_view import SettingsView
from gui.views.about_view import AboutView

# ---------------------------------------------------------------------------
# Default app state — shared across all views via reference
# ---------------------------------------------------------------------------
DEFAULT_STATE: dict = {
    "seed": 42,
    "output_dir": "",
    "stages": {
        "1a_strings":    True,
        "1b_names":      True,
        "1c_flow":       True,
        "1d_predicates": True,
        "1e_deadcode":   True,
        "3_shield":      False,   # opt-in: needs hash embedding
    },
    "theme": "dark",
    "last_input": "",
    "last_output": "",
}


class SecurerApp(ctk.CTk):
    """Main application window."""

    WIDTH  = 1080
    HEIGHT = 700
    MIN_W  = 860
    MIN_H  = 560

    def __init__(self) -> None:
        # Theme must be set before super().__init__ touches Tk internals
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        super().__init__()

        # ----------------------------------------------------------------
        # Patch tkinterdnd2 onto the live Tk instance.
        # TkinterDnD.Tk.__init__ does exactly one thing beyond tk.Tk.__init__:
        # it calls self.tk.call("package", "require", "tkdnd") via _require().
        # We replicate that here, after CTk has finished its own __init__,
        # so there is zero MRO conflict.
        # ----------------------------------------------------------------
        try:
            import tkinterdnd2 as _dnd  # type: ignore
            _dnd.TkinterDnD._require(self)  # registers DnD on this Tk root
            self._dnd_enabled = True
        except Exception:
            self._dnd_enabled = False

        self.title("Securer")
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}")
        self.minsize(self.MIN_W, self.MIN_H)
        self._set_window_icon()

        # Shared mutable state (passed by reference to every view).
        # NOTE: named app_state (not state) to avoid shadowing tk.Tk.state()
        self.app_state: dict = dict(DEFAULT_STATE)
        self.app_state["stages"] = dict(DEFAULT_STATE["stages"])

        # Toast manager (overlay layer)
        self.toast = ToastManager(self)

        # Build layout
        self._build_layout()

        # Start on the pipeline view
        self._active_view: str = ""
        self.show_view("pipeline")

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        self.sidebar = Sidebar(self, nav_callback=self.show_view)
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        # Content frame — views are stacked inside
        self.content = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        # Instantiate all views (hidden until shown)
        self._views: dict[str, ctk.CTkFrame] = {
            "pipeline": PipelineView(
                self.content,
                state=self.app_state,
                toast=self.toast,
            ),
            "settings": SettingsView(
                self.content,
                state=self.app_state,
                on_theme_change=self._apply_theme,
            ),
            "about": AboutView(self.content),
        }
        for view in self._views.values():
            view.grid(row=0, column=0, sticky="nsew")

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def show_view(self, name: str) -> None:
        if name == self._active_view:
            return
        self._active_view = name
        view = self._views.get(name)
        if view:
            view.tkraise()
        self.sidebar.set_active(name)

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _apply_theme(self, theme: str) -> None:
        self.app_state["theme"] = theme
        ctk.set_appearance_mode(theme)

    # ------------------------------------------------------------------
    # Window icon (silently ignored if file missing)
    # ------------------------------------------------------------------

    def _set_window_icon(self) -> None:
        try:
            ico = Path(__file__).parent.parent / "assets" / "icon.ico"
            if ico.exists():
                self.iconbitmap(str(ico))
        except Exception:
            pass
