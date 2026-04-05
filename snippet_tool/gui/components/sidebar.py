"""
Animated collapsible sidebar component.
Uses a smooth width animation driven by CTk's after() loop.
"""
import customtkinter as ctk
from typing import Callable
from snippet_tool.gui.theme import (
    COLORS, FONT_BODY, SIZE_SM, SIZE_BASE, SIZE_LG,
    SP2, SP3, SP4, SP6,
    SIDEBAR_WIDTH_EXPANDED, SIDEBAR_WIDTH_COLLAPSED,
    SIDEBAR_ANIM_STEPS, SIDEBAR_ANIM_MS,
    RADIUS_MD,
)


class NavItem:
    def __init__(self, key: str, label: str, icon: str):
        self.key = key
        self.label = label
        self.icon = icon  # Unicode symbol used as icon


NAV_ITEMS = [
    NavItem("snippets",  "Snippets",  "\u2630"),  # ☰
    NavItem("ocr",       "OCR",        "\u2315"),  # ⌕
    NavItem("settings",  "Settings",   "\u2699"),  # ⚙
]


class Sidebar(ctk.CTkFrame):
    """
    Vertical sidebar with icon + label nav items and a collapse toggle.
    """

    def __init__(self, master, on_navigate: Callable[[str], None], **kwargs):
        self._mode = ctk.get_appearance_mode().lower()
        c = COLORS[self._mode]

        super().__init__(
            master,
            width=SIDEBAR_WIDTH_EXPANDED,
            corner_radius=0,
            fg_color=c["sidebar_bg"],
            **kwargs,
        )
        self.pack_propagate(False)

        self._on_navigate = on_navigate
        self._active_key = "snippets"
        self._expanded = True
        self._target_width = SIDEBAR_WIDTH_EXPANDED
        self._current_width = SIDEBAR_WIDTH_EXPANDED
        self._anim_id = None
        self._buttons: dict[str, ctk.CTkButton] = {}

        self._build()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self):
        c = COLORS[self._mode]

        # Top: logo area
        self._logo_frame = ctk.CTkFrame(self, fg_color="transparent", height=56)
        self._logo_frame.pack(fill="x")
        self._logo_frame.pack_propagate(False)

        self._logo_label = ctk.CTkLabel(
            self._logo_frame,
            text="  \u229e  Securer",
            font=(FONT_BODY, SIZE_LG, "bold"),
            text_color=c["text"],
            anchor="w",
        )
        self._logo_label.pack(side="left", padx=SP4, pady=SP4)

        # Divider
        ctk.CTkFrame(self, height=1, fg_color=c["divider"]).pack(fill="x")

        # Nav items
        self._nav_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._nav_frame.pack(fill="both", expand=True, pady=SP3)

        for item in NAV_ITEMS:
            btn = ctk.CTkButton(
                self._nav_frame,
                text=f"  {item.icon}   {item.label}",
                font=(FONT_BODY, SIZE_BASE),
                anchor="w",
                fg_color="transparent",
                text_color=c["text_muted"],
                hover_color=c["sidebar_hover"],
                height=40,
                corner_radius=RADIUS_MD,
                command=lambda k=item.key: self._navigate(k),
            )
            btn.pack(fill="x", padx=SP3, pady=2)
            self._buttons[item.key] = btn

        # Spacer
        ctk.CTkFrame(self._nav_frame, fg_color="transparent").pack(fill="both", expand=True)

        # Divider above toggle
        ctk.CTkFrame(self, height=1, fg_color=c["divider"]).pack(fill="x")

        # Collapse toggle
        self._toggle_btn = ctk.CTkButton(
            self,
            text="\u25c4  Collapse",
            font=(FONT_BODY, SIZE_SM),
            anchor="w",
            fg_color="transparent",
            text_color=c["text_faint"],
            hover_color=c["sidebar_hover"],
            height=36,
            corner_radius=0,
            command=self._toggle_collapse,
        )
        self._toggle_btn.pack(fill="x", pady=(SP2, SP3), padx=SP3)

        # Set initial active state
        self._set_active(self._active_key)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _navigate(self, key: str):
        self._set_active(key)
        self._on_navigate(key)

    def _set_active(self, key: str):
        c = COLORS[self._mode]
        self._active_key = key
        for k, btn in self._buttons.items():
            if k == key:
                btn.configure(
                    fg_color=c["sidebar_active"],
                    text_color=c["text"],
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=c["text_muted"],
                )

    # ------------------------------------------------------------------
    # Collapse / Expand animation
    # ------------------------------------------------------------------

    def _toggle_collapse(self):
        if self._anim_id:
            self.after_cancel(self._anim_id)
        self._expanded = not self._expanded
        self._target_width = SIDEBAR_WIDTH_EXPANDED if self._expanded else SIDEBAR_WIDTH_COLLAPSED
        self._animate()

    def _animate(self):
        diff = self._target_width - self._current_width
        step = diff / SIDEBAR_ANIM_STEPS
        self._current_width += step
        self.configure(width=int(self._current_width))

        # Update text visibility
        if self._current_width < SIDEBAR_WIDTH_COLLAPSED + 20:
            self._logo_label.configure(text="  \u229e")
            self._toggle_btn.configure(text="\u25ba")
            for item in NAV_ITEMS:
                self._buttons[item.key].configure(text=f"  {item.icon}")
        else:
            self._logo_label.configure(text="  \u229e  Securer")
            self._toggle_btn.configure(text="\u25c4  Collapse")
            for item in NAV_ITEMS:
                self._buttons[item.key].configure(text=f"  {item.icon}   {item.label}")

        if abs(diff) > 1:
            self._anim_id = self.after(SIDEBAR_ANIM_MS, self._animate)
        else:
            self._current_width = self._target_width
            self.configure(width=int(self._current_width))

    # ------------------------------------------------------------------
    # Theme update
    # ------------------------------------------------------------------

    def update_theme(self, mode: str):
        self._mode = mode
        c = COLORS[mode]
        self.configure(fg_color=c["sidebar_bg"])
        for k, btn in self._buttons.items():
            is_active = (k == self._active_key)
            btn.configure(
                fg_color=c["sidebar_active"] if is_active else "transparent",
                text_color=c["text"] if is_active else c["text_muted"],
                hover_color=c["sidebar_hover"],
            )
        self._toggle_btn.configure(
            text_color=c["text_faint"],
            hover_color=c["sidebar_hover"],
        )
        self._logo_label.configure(text_color=c["text"])
