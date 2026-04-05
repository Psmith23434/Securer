"""
Main application shell.

Architecture:
  CTk root
  ├── Sidebar (fixed left, collapsible)
  └── Content area (fills rest of window)
      ├── SnippetsView   (active when nav key == 'snippets')
      ├── OCRView        (active when nav key == 'ocr')
      └── SettingsView   (active when nav key == 'settings')

Only the active view is visible; others are hidden via pack_forget / pack.
"""
import customtkinter as ctk
from pathlib import Path

from snippet_tool.gui.theme import COLORS, FONT_BODY, SIZE_XS, SP4
from snippet_tool.gui.components.sidebar import Sidebar
from snippet_tool.gui.components.toast import ToastManager
from snippet_tool.gui.views.snippets_view import SnippetsView
from snippet_tool.gui.views.ocr_view import OCRView
from snippet_tool.gui.views.settings_view import SettingsView


class SnippetApp(ctk.CTk):
    _MIN_W = 900
    _MIN_H = 600
    _DEFAULT_W = 1100
    _DEFAULT_H = 700

    def __init__(self, version: str = "1.0.0"):
        # Initialise CustomTkinter
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")  # We override all colors ourselves

        super().__init__()

        self._version = version
        self._mode = "dark"
        self._active_view_key = "snippets"

        self.title(f"Snippet Tool  v{version}")
        self.geometry(f"{self._DEFAULT_W}x{self._DEFAULT_H}")
        self.minsize(self._MIN_W, self._MIN_H)
        self._set_icon()

        self._toast = ToastManager(self)
        self._build()
        self._navigate("snippets")

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self):
        c = COLORS[self._mode]
        self.configure(fg_color=c["bg"])

        # Root layout: sidebar | content
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # Sidebar
        self._sidebar = Sidebar(
            self,
            on_navigate=self._navigate,
        )
        self._sidebar.grid(row=0, column=0, sticky="nsew")

        # Content area
        self._content = ctk.CTkFrame(self, fg_color=c["bg"], corner_radius=0)
        self._content.grid(row=0, column=1, sticky="nsew")
        self._content.columnconfigure(0, weight=1)
        self._content.rowconfigure(0, weight=1)

        # Instantiate all views
        self._views: dict[str, ctk.CTkFrame] = {}

        self._views["snippets"] = SnippetsView(
            self._content,
            toast_fn=lambda msg, kind="info": self._toast.show(msg, kind),
        )
        self._views["ocr"] = OCRView(
            self._content,
            toast_fn=lambda msg, kind="info": self._toast.show(msg, kind),
        )
        self._views["settings"] = SettingsView(
            self._content,
            toast_fn=lambda msg, kind="info": self._toast.show(msg, kind),
            version=self._version,
            toggle_theme_fn=self._toggle_theme,
        )

        for view in self._views.values():
            view.grid(row=0, column=0, sticky="nsew")
            view.grid_remove()  # hide all initially

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _navigate(self, key: str):
        # Hide current
        if self._active_view_key in self._views:
            self._views[self._active_view_key].grid_remove()

        self._active_view_key = key
        if key in self._views:
            self._views[key].grid()

    # ------------------------------------------------------------------
    # Theme toggle
    # ------------------------------------------------------------------

    def _toggle_theme(self):
        self._mode = "light" if self._mode == "dark" else "dark"
        ctk.set_appearance_mode(self._mode)
        c = COLORS[self._mode]
        self.configure(fg_color=c["bg"])
        self._content.configure(fg_color=c["bg"])
        self._sidebar.update_theme(self._mode)
        for view in self._views.values():
            view.update_theme(self._mode)

    # ------------------------------------------------------------------
    # Update banner
    # ------------------------------------------------------------------

    def show_update_banner(self, update_info: dict):
        """Called from background thread via after() when update is available."""
        self._toast.show(
            f"Update available: v{update_info['latest']}  —  {update_info.get('download_url', '')}",
            kind="info",
            duration_ms=6000,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_icon(self):
        icon_path = Path(__file__).parent.parent / "assets" / "icon.ico"
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
            except Exception:
                pass
