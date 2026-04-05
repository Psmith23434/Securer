"""
Centralised design tokens for the Snippet Tool GUI.
All colors, fonts, spacing, and radius values live here.
Adapts automatically to light/dark mode via CustomTkinter.
"""

# ---------------------------------------------------------------------------
# Color palette — Nexus Design System (warm neutrals + teal accent)
# ---------------------------------------------------------------------------

COLORS = {
    "light": {
        "bg":              "#f7f6f2",
        "surface":         "#f9f8f5",
        "surface_2":       "#fbfbf9",
        "surface_offset":  "#f0ede8",
        "border":          "#d4d1ca",
        "divider":         "#dcd9d5",

        "text":            "#28251d",
        "text_muted":      "#7a7974",
        "text_faint":      "#bab9b4",
        "text_inverse":    "#f9f8f4",

        "primary":         "#01696f",
        "primary_hover":   "#0c4e54",
        "primary_active":  "#0f3638",
        "primary_subtle":  "#cedcd8",

        "success":         "#437a22",
        "success_subtle":  "#d4dfcc",
        "error":           "#c0392b",
        "error_subtle":    "#fce8e6",
        "warning":         "#964219",
        "warning_subtle":  "#ddcfc6",

        "sidebar_bg":      "#efede8",
        "sidebar_active":  "#dcd9d5",
        "sidebar_hover":   "#e5e2dc",
    },
    "dark": {
        "bg":              "#171614",
        "surface":         "#1c1b19",
        "surface_2":       "#201f1d",
        "surface_offset":  "#252422",
        "border":          "#393836",
        "divider":         "#262523",

        "text":            "#cdccca",
        "text_muted":      "#797876",
        "text_faint":      "#5a5957",
        "text_inverse":    "#2b2a28",

        "primary":         "#4f98a3",
        "primary_hover":   "#227f8b",
        "primary_active":  "#1a626b",
        "primary_subtle":  "#313b3b",

        "success":         "#6daa45",
        "success_subtle":  "#3a4435",
        "error":           "#e07070",
        "error_subtle":    "#3d2929",
        "warning":         "#bb653b",
        "warning_subtle":  "#564942",

        "sidebar_bg":      "#141312",
        "sidebar_active":  "#2a2927",
        "sidebar_hover":   "#1f1e1c",
    },
}

# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------

FONT_BODY    = "Segoe UI"       # Windows system font with excellent legibility
FONT_MONO    = "Cascadia Code"  # Fallback: Consolas

SIZE_XS   = 11
SIZE_SM   = 12
SIZE_BASE = 13
SIZE_LG   = 15
SIZE_XL   = 18
SIZE_2XL  = 22

# ---------------------------------------------------------------------------
# Spacing (4px base unit)
# ---------------------------------------------------------------------------

SP1  = 4
SP2  = 8
SP3  = 12
SP4  = 16
SP5  = 20
SP6  = 24
SP8  = 32
SP10 = 40
SP12 = 48

# ---------------------------------------------------------------------------
# Radius
# ---------------------------------------------------------------------------

RADIUS_SM = 4
RADIUS_MD = 6
RADIUS_LG = 10
RADIUS_XL = 14

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

SIDEBAR_WIDTH_EXPANDED  = 210
SIDEBAR_WIDTH_COLLAPSED = 56
SIDEBAR_ANIM_STEPS      = 12
SIDEBAR_ANIM_MS         = 12


def get(key: str, mode: str = "dark") -> str:
    """Convenience: get a color by key for a given mode."""
    return COLORS.get(mode, COLORS["dark"]).get(key, "#ff00ff")
