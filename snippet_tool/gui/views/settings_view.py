"""
Settings view — license activation, theme toggle, app info.
"""
import customtkinter as ctk
from snippet_tool.gui.theme import (
    COLORS, FONT_BODY,
    SIZE_XS, SIZE_SM, SIZE_BASE, SIZE_LG, SIZE_XL,
    SP2, SP3, SP4, SP5, SP6, SP8, SP10,
    RADIUS_MD, RADIUS_LG,
)
from shared.license_check import get_activation_info, validate_license


class SettingsView(ctk.CTkFrame):
    def __init__(self, master, toast_fn, version: str, toggle_theme_fn, **kwargs):
        mode = ctk.get_appearance_mode().lower()
        c = COLORS[mode]
        super().__init__(master, fg_color=c["bg"], corner_radius=0, **kwargs)
        self._toast = toast_fn
        self._mode = mode
        self._version = version
        self._toggle_theme = toggle_theme_fn
        self._build()

    def _build(self):
        c = COLORS[self._mode]
        self.columnconfigure(0, weight=1)

        # ---- Page title ----
        ctk.CTkLabel(
            self,
            text="Settings",
            font=(FONT_BODY, SIZE_XL, "bold"),
            text_color=c["text"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=SP8, pady=(SP8, SP6))

        # ---- Appearance card ----
        self._card(row=1, title="Appearance", builder=self._build_appearance)

        # ---- License card ----
        self._card(row=2, title="License Activation", builder=self._build_license)

        # ---- About card ----
        self._card(row=3, title="About", builder=self._build_about)

    def _card(self, row: int, title: str, builder):
        c = COLORS[self._mode]
        card = ctk.CTkFrame(
            self,
            fg_color=c["surface"],
            corner_radius=RADIUS_LG,
        )
        card.grid(row=row, column=0, sticky="ew", padx=SP8, pady=(0, SP5))
        card.columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text=title,
            font=(FONT_BODY, SIZE_BASE, "bold"),
            text_color=c["text"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=SP6, pady=(SP5, SP3))

        ctk.CTkFrame(card, height=1, fg_color=c["divider"]).grid(
            row=1, column=0, sticky="ew", padx=SP6
        )

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.grid(row=2, column=0, sticky="ew", padx=SP6, pady=SP5)
        inner.columnconfigure(0, weight=1)
        builder(inner)

    def _build_appearance(self, parent):
        c = COLORS[self._mode]
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x")

        ctk.CTkLabel(
            row,
            text="Theme",
            font=(FONT_BODY, SIZE_SM),
            text_color=c["text_muted"],
        ).pack(side="left")

        self._theme_btn = ctk.CTkButton(
            row,
            text="\u263c  Light mode" if self._mode == "dark" else "\u263e  Dark mode",
            font=(FONT_BODY, SIZE_SM),
            height=32, corner_radius=RADIUS_MD,
            fg_color=c["surface_offset"],
            hover_color=c["surface_2"],
            text_color=c["text"],
            command=self._toggle_theme,
        )
        self._theme_btn.pack(side="right")

    def _build_license(self, parent):
        c = COLORS[self._mode]

        info = get_activation_info(self._read_saved_key())

        status_color = c["success"] if info["valid"] else c["text_muted"]
        status_text  = "\u2713 Activated" if info["valid"] else "\u25cb Not activated"

        status_row = ctk.CTkFrame(parent, fg_color="transparent")
        status_row.pack(fill="x", pady=(0, SP4))

        ctk.CTkLabel(
            status_row,
            text="Status:",
            font=(FONT_BODY, SIZE_SM),
            text_color=c["text_muted"],
        ).pack(side="left")
        ctk.CTkLabel(
            status_row,
            text=status_text,
            font=(FONT_BODY, SIZE_SM, "bold"),
            text_color=status_color,
        ).pack(side="left", padx=SP3)

        ctk.CTkLabel(
            parent,
            text="License Key",
            font=(FONT_BODY, SIZE_SM),
            text_color=c["text_muted"],
            anchor="w",
        ).pack(fill="x", pady=(0, SP2))

        key_row = ctk.CTkFrame(parent, fg_color="transparent")
        key_row.pack(fill="x")
        key_row.columnconfigure(0, weight=1)

        self._key_var = ctk.StringVar(value=self._read_saved_key())
        key_entry = ctk.CTkEntry(
            key_row,
            textvariable=self._key_var,
            placeholder_text="XXXX-XXXX-XXXX-XXXX",
            font=(FONT_BODY, SIZE_SM),
            height=34,
            corner_radius=RADIUS_MD,
        )
        key_entry.grid(row=0, column=0, sticky="ew", padx=(0, SP3))

        ctk.CTkButton(
            key_row,
            text="Activate",
            font=(FONT_BODY, SIZE_SM),
            height=34, corner_radius=RADIUS_MD,
            fg_color=c["primary"],
            hover_color=c["primary_hover"],
            text_color=c["text_inverse"],
            command=self._activate,
        ).grid(row=0, column=1)

        ctk.CTkLabel(
            parent,
            text=f"Machine ID: {info['machine_id']}",
            font=(FONT_BODY, SIZE_XS),
            text_color=c["text_faint"],
            anchor="w",
        ).pack(fill="x", pady=(SP4, 0))

    def _build_about(self, parent):
        c = COLORS[self._mode]
        lines = [
            ("Version",   self._version),
            ("Build tool", "Nuitka + Cython"),
            ("Python",     "3.11+"),
            ("License",    "Commercial — see EULA"),
        ]
        for label, value in lines:
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", pady=SP2)
            ctk.CTkLabel(
                row, text=label,
                font=(FONT_BODY, SIZE_SM),
                text_color=c["text_muted"],
                width=120, anchor="w",
            ).pack(side="left")
            ctk.CTkLabel(
                row, text=value,
                font=(FONT_BODY, SIZE_SM),
                text_color=c["text"],
                anchor="w",
            ).pack(side="left")

    # ------------------------------------------------------------------
    # License helpers
    # ------------------------------------------------------------------

    def _read_saved_key(self) -> str:
        import os
        key_file = os.path.join(os.path.expanduser("~"), ".snippet_tool", "license.key")
        try:
            with open(key_file) as f:
                return f.read().strip()
        except FileNotFoundError:
            return ""

    def _save_key(self, key: str):
        import os
        folder = os.path.join(os.path.expanduser("~"), ".snippet_tool")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "license.key"), "w") as f:
            f.write(key.strip())

    def _activate(self):
        key = self._key_var.get().strip()
        if validate_license(key):
            self._save_key(key)
            self._toast("\u2713 License activated successfully!", "success")
        else:
            self._toast("Invalid license key for this machine.", "error")

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def update_theme(self, mode: str):
        self._mode = mode
        # Rebuild the whole view with new colors
        for w in self.winfo_children():
            w.destroy()
        self._build()
