"""
PipelineView — main obfuscation UI.

Layout (top-to-bottom):
  - Page header: title + subtitle
  - Input row: drag-and-drop zone + Browse button
  - Stage toggles: 7 toggle switches (1a-1e + 3a Anti-Debug + 3b Integrity Hash)
  - Options row: seed entry + output dir
  - Run button (full width)
  - LogPanel (fills remaining space)

Stage 3 is split into two independent cards:
  3a — Anti-Debug  : IsDebuggerPresent + timing heuristic.
                     Safe on every PC — enable by default.
  3b — Integrity Hash : SHA-256 self-check baked into the binary.
                     Disabled by default. Requires a two-pass build and
                     is incompatible with --onefile (use --standalone).
                     A ⚠️ tooltip explains this when hovered.

Nuitka compilation now defaults to --standalone (not --onefile) so the
produced app never self-extracts to a temp folder at runtime, which
reduces antivirus false-positives on user machines.

Drag-and-drop:
  Uses tkinterdnd2 when available.  The drop zone is a dashed-border
  CTkFrame that accepts .py files dragged from Explorer / Finder.
  Falls back silently to Browse-only mode if tkinterdnd2 is not installed.

Post-run:
  After a successful obfuscation run a CTkToplevel dialog asks the user
  whether to compile the _obf.py with Nuitka.  If accepted, NuitkaRunner
  streams the build log into the same LogPanel.
"""
from __future__ import annotations

import threading
from pathlib import Path
from tkinter import filedialog
import os
import subprocess
import sys

import customtkinter as ctk

from gui.components.log_panel import LogPanel, LogLevel
from gui.components.toast import ToastManager
from securer.nuitka_runner import NuitkaRunner, NuitkaError

# ---------------------------------------------------------------------------
# Optional drag-and-drop support
# ---------------------------------------------------------------------------
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore
    _DND_AVAILABLE = True
except ImportError:
    _DND_AVAILABLE = False
    DND_FILES = None  # type: ignore


# ---------------------------------------------------------------------------
# Stage metadata
# Each tuple: (state_key, badge_label, display_name, short_tip, warn_tip|None)
# warn_tip is shown in a hoverable ⚠️ popover; None = no warning badge
# ---------------------------------------------------------------------------
STAGE_META = [
    (
        "1a_strings",
        "1a",
        "String Encryption",
        "XOR-encrypt every string literal",
        None,
    ),
    (
        "1b_names",
        "1b",
        "Name Mangling",
        "Rename all identifiers to _X{hash}",
        None,
    ),
    (
        "1c_flow",
        "1c",
        "Flow Flattening",
        "Rewrite functions as state machines",
        None,
    ),
    (
        "1d_predicates",
        "1d",
        "Opaque Predicates",
        "Insert always-true/false guard branches",
        None,
    ),
    (
        "1e_deadcode",
        "1e",
        "Dead Code Injection",
        "Inject realistic but unreachable code",
        None,
    ),
    (
        "3a_antidebug",
        "3a",
        "Anti-Debug",
        "Kills process if debugger attached",
        None,  # safe on all PCs — no warning needed
    ),
    (
        "3b_integrity",
        "3b",
        "Integrity Hash",
        "SHA-256 self-check at startup",
        # Warning shown in popover when user hovers the ⚠️ badge:
        (
            "⚠️  Advanced — read before enabling\n\n"
            "This bakes a SHA-256 fingerprint of your .exe into the\n"
            "binary itself. Any modification to the file causes an\n"
            "immediate silent exit.\n\n"
            "Requires a two-pass build:\n"
            "  1. Build once to produce the .exe\n"
            "  2. Run compute_current_hash() to get the fingerprint\n"
            "  3. Set RuntimeShield.EXPECTED_HASH = \"<hash>\"\n"
            "  4. Build again — now the check is active\n\n"
            "⚠️  Incompatible with --onefile.\n"
            "Use --standalone (default in Securer) so sys.executable\n"
            "points to a stable path, not a temp extraction folder.\n\n"
            "⚠️  Antivirus / Windows Defender may modify the .exe\n"
            "after build (scan, quarantine, SmartScreen tag).\n"
            "If that happens the fingerprint changes and your app\n"
            "will silently refuse to launch on ANY machine.\n\n"
            "Leave OFF unless you fully control distribution."
        ),
    ),
]

# Drop-zone appearance constants
_DZ_IDLE_LIGHT  = "#e8e8e8"
_DZ_IDLE_DARK   = "#2a2a2a"
_DZ_HOVER_LIGHT = "#d0e8ff"
_DZ_HOVER_DARK  = "#1a3a5c"
_DZ_HEIGHT      = 72


class _TooltipPopover(ctk.CTkToplevel):
    """
    A small borderless popover window shown while the user hovers a widget.
    Destroyed automatically when the pointer leaves the trigger widget.
    """

    def __init__(self, trigger: ctk.CTkBaseClass, text: str) -> None:
        super().__init__(trigger)
        self.overrideredirect(True)   # no title bar / borders
        self.attributes("-topmost", True)
        self.resizable(False, False)

        frame = ctk.CTkFrame(self, corner_radius=8, border_width=1,
                             border_color=("#e0a020", "#c08010"),
                             fg_color=("#fffbe6", "#2a2510"))
        frame.pack(fill="both", expand=True, padx=0, pady=0)

        ctk.CTkLabel(
            frame,
            text=text,
            font=("Segoe UI", 11),
            text_color=("#5a3e00", "#e8c46a"),
            justify="left",
            anchor="w",
            wraplength=340,
        ).pack(padx=14, pady=12)

        # Position just below the trigger widget
        self.update_idletasks()
        tx = trigger.winfo_rootx()
        ty = trigger.winfo_rooty() + trigger.winfo_height() + 4
        self.geometry(f"+{tx}+{ty}")


class _CompileDialog(ctk.CTkToplevel):
    """
    Modal dialog shown after a successful obfuscation run.

    Asks: "Compile <name>_obf.py to a native binary with Nuitka?"
    Returns via ``result`` attribute: True = compile, False = skip.

    Defaults to --standalone (not --onefile) so the compiled app never
    self-extracts to a temp folder on the user's machine, which avoids
    antivirus false-positives and temp-file clutter.
    """

    def __init__(self, parent: ctk.CTk, obf_path: Path) -> None:
        super().__init__(parent)
        self.title("Compile with Nuitka?")
        self.resizable(False, False)
        self.grab_set()
        self.result: bool = False
        self._obf_path = obf_path

        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text="\u26a1  Compile to native binary?",
            font=("Segoe UI", 16, "bold"),
        ).grid(row=0, column=0, columnspan=2, padx=24, pady=(22, 6), sticky="w")

        ctk.CTkLabel(
            self,
            text=(
                f"Obfuscated file written:\n"
                f"  {obf_path.name}\n\n"
                "Compile it to a standalone native binary\n"
                "using Nuitka? This may take a few minutes."
            ),
            font=("Segoe UI", 12),
            justify="left",
            anchor="w",
        ).grid(row=1, column=0, columnspan=2, padx=24, pady=(0, 6), sticky="w")

        # --standalone is the new default (was --onefile)
        # Reason: --onefile self-extracts to %TEMP% at runtime which triggers
        # antivirus heuristics and leaves temp files on user machines.
        # --standalone produces a folder; nothing is extracted at runtime.
        self._standalone_var = ctk.BooleanVar(value=True)
        standalone_cb = ctk.CTkCheckBox(
            self,
            text="Standalone folder (--standalone, recommended)",
            variable=self._standalone_var,
            font=("Segoe UI", 12),
        )
        standalone_cb.grid(row=2, column=0, columnspan=2, padx=24, pady=(0, 2), sticky="w")

        ctk.CTkLabel(
            self,
            text="  No temp extraction on user PCs — safer against antivirus",
            font=("Segoe UI", 10),
            text_color=("#666666", "#888888"),
            anchor="w",
        ).grid(row=3, column=0, columnspan=2, padx=24, pady=(0, 8), sticky="w")

        self._noconsole_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            self,
            text="Hide console window (--windows-disable-console)",
            variable=self._noconsole_var,
            font=("Segoe UI", 12),
        ).grid(row=4, column=0, columnspan=2, padx=24, pady=(0, 16), sticky="w")

        out_frame = ctk.CTkFrame(self, fg_color="transparent")
        out_frame.grid(row=5, column=0, columnspan=2, sticky="ew", padx=24, pady=(0, 16))
        out_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            out_frame, text="Output dir", font=("Segoe UI", 12, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))

        self._out_entry = ctk.CTkEntry(
            out_frame,
            placeholder_text="Same as .py file (default)",
            height=34,
            font=("Segoe UI", 12),
        )
        self._out_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))

        ctk.CTkButton(
            out_frame, text="\u2026", width=34, height=34,
            font=("Segoe UI", 14), command=self._browse_out,
        ).grid(row=0, column=2)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=6, column=0, columnspan=2, sticky="ew", padx=24, pady=(0, 20))
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            btn_frame, text="Skip",
            fg_color="transparent", border_width=1,
            text_color=("#333333", "#cccccc"),
            font=("Segoe UI", 13), command=self._skip,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            btn_frame, text="\u26a1  Compile",
            font=("Segoe UI", 13, "bold"), command=self._compile,
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width()  - self.winfo_width())  // 2
        py = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")

    def _browse_out(self) -> None:
        path = filedialog.askdirectory(title="Select Nuitka output directory")
        if path:
            self._out_entry.delete(0, "end")
            self._out_entry.insert(0, path)

    def _skip(self) -> None:
        self.result = False
        self.destroy()

    def _compile(self) -> None:
        self.result = True
        self._chosen_out        = self._out_entry.get().strip()
        self._chosen_standalone = self._standalone_var.get()
        self._chosen_noconsole  = self._noconsole_var.get()
        self.destroy()


class PipelineView(ctk.CTkFrame):
    """Main pipeline execution view."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        state: dict,
        toast: ToastManager,
    ) -> None:
        super().__init__(parent, fg_color="transparent")
        self._state = state
        self._toast = toast
        self._running = False
        self._toggle_vars: dict[str, ctk.BooleanVar] = {}
        self._active_tooltip: _TooltipPopover | None = None
        self._build()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)

        self._build_header(row=0)
        self._build_file_row(row=1)
        self._build_stage_toggles(row=2)
        self._build_options_row(row=3)

        self._run_btn = ctk.CTkButton(
            self,
            text="\u25b6  Run Pipeline",
            height=44,
            font=("Segoe UI", 14, "bold"),
            command=self._on_run,
        )
        self._run_btn.grid(row=4, column=0, sticky="ew", padx=20, pady=(8, 6))

        self._log = LogPanel(self)
        self._log.grid(row=5, column=0, sticky="nsew", padx=20, pady=(0, 16))

    def _build_header(self, row: int) -> None:
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=row, column=0, sticky="ew", padx=20, pady=(20, 4))
        hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            hdr, text="Obfuscation Pipeline",
            font=("Segoe UI", 20, "bold"), anchor="w",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            hdr,
            text="Drop a .py file below or browse, configure stages, then run.",
            font=("Segoe UI", 12),
            text_color=("#666666", "#888888"),
            anchor="w",
        ).grid(row=1, column=0, sticky="w")

    def _build_file_row(self, row: int) -> None:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=20, pady=(8, 4))
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame, text="Input file",
            font=("Segoe UI", 12, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))

        is_dark = ctk.get_appearance_mode() == "Dark"
        dz_idle = _DZ_IDLE_DARK if is_dark else _DZ_IDLE_LIGHT

        self._drop_zone = ctk.CTkFrame(
            frame,
            height=_DZ_HEIGHT,
            corner_radius=8,
            fg_color=dz_idle,
            border_width=2,
            border_color=("#bbbbbb", "#444444"),
        )
        self._drop_zone.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self._drop_zone.grid_propagate(False)
        self._drop_zone.grid_columnconfigure(0, weight=1)
        self._drop_zone.grid_rowconfigure(0, weight=1)

        dnd_icon = "\u2B07" if _DND_AVAILABLE else "\U0001F4C2"
        dnd_hint = (
            f"{dnd_icon}  Drop a .py file here"
            if _DND_AVAILABLE
            else "\U0001F4C2  Browse to select a .py file"
        )
        self._dz_label = ctk.CTkLabel(
            self._drop_zone,
            text=dnd_hint,
            font=("Segoe UI", 12),
            text_color=("#888888", "#666666"),
        )
        self._dz_label.grid(row=0, column=0)

        if _DND_AVAILABLE:
            self._drop_zone.drop_target_register(DND_FILES)  # type: ignore[arg-type]
            self._drop_zone.dnd_bind("<<DropEnter>>", self._on_drop_enter)
            self._drop_zone.dnd_bind("<<DropLeave>>", self._on_drop_leave)
            self._drop_zone.dnd_bind("<<Drop>>",      self._on_drop)
            self._dz_label.drop_target_register(DND_FILES)  # type: ignore[arg-type]
            self._dz_label.dnd_bind("<<Drop>>", self._on_drop)

        self._drop_zone.bind("<Button-1>", lambda _e: self._browse_file())
        self._dz_label.bind("<Button-1>",  lambda _e: self._browse_file())

        self._file_entry = ctk.CTkEntry(
            frame,
            placeholder_text="Path to your .py source file...",
            height=36,
            font=("Segoe UI", 12),
        )
        self._file_entry.grid(row=2, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(
            frame,
            text="Browse",
            width=80,
            height=36,
            font=("Segoe UI", 12),
            command=self._browse_file,
        ).grid(row=2, column=1)

    def _build_stage_toggles(self, row: int) -> None:
        outer = ctk.CTkFrame(
            self,
            fg_color=("#f0f0f0", "#1e1e1e"),
            corner_radius=10,
        )
        outer.grid(row=row, column=0, sticky="ew", padx=20, pady=6)

        ctk.CTkLabel(
            outer, text="Stages",
            font=("Segoe UI", 12, "bold"), anchor="w",
        ).grid(row=0, column=0, columnspan=len(STAGE_META), sticky="w", padx=14, pady=(10, 6))

        for col, (key, badge, name, tip, warn_tip) in enumerate(STAGE_META):
            outer.grid_columnconfigure(col, weight=1)
            card = ctk.CTkFrame(
                outer, fg_color=("#ffffff", "#2a2a2a"), corner_radius=8,
            )
            card.grid(row=1, column=col, sticky="ew", padx=6, pady=(0, 10))

            # Badge row: badge label + optional ⚠️ hover button
            badge_row = ctk.CTkFrame(card, fg_color="transparent")
            badge_row.grid(row=0, column=0, sticky="w", padx=(10, 0), pady=(8, 0))

            ctk.CTkLabel(
                badge_row, text=badge,
                font=("Consolas", 10, "bold"),
                text_color=("#888888", "#666666"),
            ).pack(side="left")

            if warn_tip:
                warn_btn = ctk.CTkLabel(
                    badge_row,
                    text=" ⚠️",
                    font=("Segoe UI", 10),
                    text_color=("#c08000", "#e8c46a"),
                    cursor="question_arrow",
                )
                warn_btn.pack(side="left", padx=(4, 0))
                # Show popover on hover
                warn_btn.bind("<Enter>",  lambda e, w=warn_btn, t=warn_tip: self._show_tooltip(w, t))
                warn_btn.bind("<Leave>",  lambda e: self._hide_tooltip())

            ctk.CTkLabel(
                card, text=name,
                font=("Segoe UI", 11, "bold"), anchor="w", wraplength=120,
            ).grid(row=1, column=0, sticky="w", padx=10)

            ctk.CTkLabel(
                card, text=tip,
                font=("Segoe UI", 10),
                text_color=("#888888", "#666666"), anchor="w", wraplength=120,
            ).grid(row=2, column=0, sticky="w", padx=10, pady=(2, 8))

            var = ctk.BooleanVar(value=self._state["stages"].get(key, False))
            self._toggle_vars[key] = var
            switch = ctk.CTkSwitch(
                card, text="", variable=var, width=46,
                command=lambda k=key, v=var: self._on_toggle(k, v),
            )
            switch.grid(row=3, column=0, sticky="w", padx=8, pady=(0, 8))

    def _build_options_row(self, row: int) -> None:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=20, pady=(4, 4))
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_columnconfigure(3, weight=2)

        ctk.CTkLabel(frame, text="Seed", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        self._seed_entry = ctk.CTkEntry(frame, width=80, height=34, font=("Consolas", 12))
        self._seed_entry.insert(0, str(self._state.get("seed", 42)))
        self._seed_entry.grid(row=0, column=1, sticky="w", padx=(0, 20))

        ctk.CTkLabel(frame, text="Output dir", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=2, sticky="w", padx=(0, 8)
        )
        self._outdir_entry = ctk.CTkEntry(
            frame,
            placeholder_text="Same as input (default)",
            height=34, font=("Segoe UI", 12),
        )
        if self._state.get("output_dir"):
            self._outdir_entry.insert(0, self._state["output_dir"])
        self._outdir_entry.grid(row=0, column=3, sticky="ew", padx=(0, 8))

        ctk.CTkButton(
            frame, text="\u2026", width=34, height=34,
            font=("Segoe UI", 14), command=self._browse_outdir,
        ).grid(row=0, column=4)

    # ------------------------------------------------------------------
    # Tooltip helpers
    # ------------------------------------------------------------------

    def _show_tooltip(self, trigger: ctk.CTkBaseClass, text: str) -> None:
        self._hide_tooltip()
        try:
            self._active_tooltip = _TooltipPopover(trigger, text)
        except Exception:
            pass

    def _hide_tooltip(self) -> None:
        if self._active_tooltip is not None:
            try:
                self._active_tooltip.destroy()
            except Exception:
                pass
            self._active_tooltip = None

    # ------------------------------------------------------------------
    # Drag-and-drop handlers
    # ------------------------------------------------------------------

    def _on_drop_enter(self, event) -> None:
        is_dark = ctk.get_appearance_mode() == "Dark"
        self._drop_zone.configure(fg_color=_DZ_HOVER_DARK if is_dark else _DZ_HOVER_LIGHT)
        self._dz_label.configure(text="\u2B07  Release to load file")

    def _on_drop_leave(self, event) -> None:
        self._reset_drop_zone()

    def _on_drop(self, event) -> None:
        self._reset_drop_zone()
        raw: str = event.data.strip()
        if raw.startswith("{") and raw.endswith("}"):
            raw = raw[1:-1]
        paths = raw.split()
        py_path: str | None = None
        for p in paths:
            if p.lower().endswith(".py"):
                py_path = p
                break
        if py_path is None:
            self._toast.show("Only .py files are accepted.", kind="warning")
            return
        if not Path(py_path).exists():
            self._toast.show("Dropped file not found.", kind="error")
            return
        self._set_file(py_path)
        self._toast.show(f"Loaded: {Path(py_path).name}", kind="success")

    def _reset_drop_zone(self) -> None:
        is_dark = ctk.get_appearance_mode() == "Dark"
        self._drop_zone.configure(fg_color=_DZ_IDLE_DARK if is_dark else _DZ_IDLE_LIGHT)
        dnd_hint = (
            "\u2B07  Drop a .py file here"
            if _DND_AVAILABLE
            else "\U0001F4C2  Browse to select a .py file"
        )
        self._dz_label.configure(text=dnd_hint)

    def _set_file(self, path: str) -> None:
        self._file_entry.delete(0, "end")
        self._file_entry.insert(0, path)
        self._state["last_input"] = path
        self._dz_label.configure(
            text=f"\u2714  {Path(path).name}",
            text_color=("#437a22", "#6daa45"),
        )

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _browse_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Python source file",
            filetypes=[("Python files", "*.py"), ("All files", "*.*")],
        )
        if path:
            self._set_file(path)

    def _browse_outdir(self) -> None:
        path = filedialog.askdirectory(title="Select output directory")
        if path:
            self._outdir_entry.delete(0, "end")
            self._outdir_entry.insert(0, path)
            self._state["output_dir"] = path

    def _on_toggle(self, key: str, var: ctk.BooleanVar) -> None:
        self._state["stages"][key] = var.get()

    def _on_run(self) -> None:
        if self._running:
            return
        input_path = self._file_entry.get().strip()
        if not input_path:
            self._toast.show("Please select an input .py file.", kind="warning")
            return
        if not Path(input_path).exists():
            self._toast.show("Input file not found.", kind="error")
            return
        try:
            self._state["seed"] = int(self._seed_entry.get().strip())
        except ValueError:
            self._toast.show("Seed must be an integer.", kind="warning")
            return
        out_dir = self._outdir_entry.get().strip()
        self._state["output_dir"] = out_dir
        self._state["last_input"] = input_path

        self._run_btn.configure(state="disabled", text="\u23f3  Running...")
        self._running = True
        self._log.clear()
        threading.Thread(
            target=self._run_pipeline,
            args=(input_path,),
            daemon=True,
        ).start()

    # ------------------------------------------------------------------
    # Pipeline execution (background thread)
    # ------------------------------------------------------------------

    def _run_pipeline(self, input_path: str) -> None:
        log = self._log
        state = self._state
        stages = state["stages"]
        seed = state["seed"]

        try:
            log.log(f"Reading {input_path}", LogLevel.INFO)
            src = Path(input_path).read_text(encoding="utf-8")
            log.log(f"Source: {len(src.splitlines())} lines, {len(src):,} bytes", LogLevel.INFO)

            tree = None
            last_module = None

            if stages.get("1a_strings"):
                log.log("Stage 1a \u2014 String Encryption...", LogLevel.INFO)
                from securer.string_encryptor import StringEncryptor
                enc = StringEncryptor(seed=seed)
                tree = enc.transform(src)
                log.log(f"  Encrypted {enc.count} string(s)", LogLevel.SUCCESS)
                last_module = enc
            else:
                log.log("Stage 1a \u2014 skipped", LogLevel.INFO)

            if stages.get("1b_names"):
                log.log("Stage 1b \u2014 Name Mangling...", LogLevel.INFO)
                from securer.name_mangler import NameMangler
                mg = NameMangler(seed=seed)
                if tree is None:
                    import ast; tree = ast.parse(src)
                tree = mg.transform_tree(tree)
                log.log(f"  Mangled {len(mg.symbol_table)} identifier(s)", LogLevel.SUCCESS)
                last_module = mg
            else:
                log.log("Stage 1b \u2014 skipped", LogLevel.INFO)

            if stages.get("1c_flow"):
                log.log("Stage 1c \u2014 Flow Flattening...", LogLevel.INFO)
                from securer.flow_flattener import FlowFlattener
                ff = FlowFlattener(seed=seed)
                if tree is None:
                    import ast; tree = ast.parse(src)
                tree = ff.transform_tree(tree)
                log.log(f"  Flattened {getattr(ff, 'functions_transformed', '?')} function(s)", LogLevel.SUCCESS)
                last_module = ff
            else:
                log.log("Stage 1c \u2014 skipped", LogLevel.INFO)

            if stages.get("1d_predicates"):
                log.log("Stage 1d \u2014 Opaque Predicates...", LogLevel.INFO)
                from securer.opaque_predicates import OpaquePredicates
                op = OpaquePredicates(seed=seed)
                if tree is None:
                    import ast; tree = ast.parse(src)
                tree = op.transform_tree(tree)
                log.log("  Injected predicates", LogLevel.SUCCESS)
                last_module = op
            else:
                log.log("Stage 1d \u2014 skipped", LogLevel.INFO)

            if stages.get("1e_deadcode"):
                log.log("Stage 1e \u2014 Dead Code Injection...", LogLevel.INFO)
                from securer.dead_code_injector import DeadCodeInjector
                di = DeadCodeInjector(seed=seed)
                if tree is None:
                    import ast; tree = ast.parse(src)
                tree = di.transform_tree(tree)
                stats = getattr(di, 'stats', {})
                injected = stats.get('injected', '?') if isinstance(stats, dict) else '?'
                log.log(f"  Injected {injected} dead block(s)", LogLevel.SUCCESS)
                last_module = di
            else:
                log.log("Stage 1e \u2014 skipped", LogLevel.INFO)

            if tree is not None:
                output_src = (
                    last_module.unparse(tree)
                    if last_module and hasattr(last_module, "unparse")
                    else __import__("ast").unparse(tree)
                )
            else:
                log.log("No stages active \u2014 writing original source.", LogLevel.WARNING)
                output_src = src

            # ----------------------------------------------------------
            # Stage 3 — Runtime Shield header injection
            # 3a (anti-debug) and 3b (integrity hash) are independent.
            # We only inject the import + guard call when at least one
            # sub-stage is active.  The RuntimeShield.guard() call itself
            # internally skips whichever checks aren't configured.
            # ----------------------------------------------------------
            antidebug = stages.get("3a_antidebug", False)
            integrity = stages.get("3b_integrity",  False)

            if antidebug or integrity:
                log.log("Stage 3 \u2014 prepending RuntimeShield header...", LogLevel.INFO)

                shield_lines = [
                    "from securer.runtime_shield import RuntimeShield",
                ]

                if integrity:
                    # Integrity hash: caller must set EXPECTED_HASH before
                    # the second build.  We emit the placeholder comment so
                    # the developer knows where to put it.
                    shield_lines += [
                        "# TODO: set EXPECTED_HASH after first build:",
                        "# RuntimeShield.EXPECTED_HASH = \"<paste hash here>\"",
                    ]

                if antidebug and not integrity:
                    # Anti-debug only — skip the integrity check explicitly
                    shield_lines.append(
                        "RuntimeShield.guard(expected_hash=None)  # anti-debug only"
                    )
                else:
                    shield_lines.append(
                        "RuntimeShield.guard()  # anti-debug + integrity check"
                    )

                output_src = "\n".join(shield_lines) + "\n\n" + output_src

                active = []
                if antidebug: active.append("anti-debug")
                if integrity:  active.append("integrity hash")
                log.log(f"  Shield active: {', '.join(active)}", LogLevel.SUCCESS)
            else:
                log.log("Stage 3 \u2014 skipped", LogLevel.INFO)

            in_path = Path(input_path)
            out_dir_str = state.get("output_dir", "").strip()
            out_path = (
                Path(out_dir_str) / (in_path.stem + "_obf.py")
                if out_dir_str
                else in_path.parent / (in_path.stem + "_obf.py")
            )
            out_path.write_text(output_src, encoding="utf-8")
            state["last_output"] = str(out_path)

            out_lines = len(output_src.splitlines())
            ratio = out_lines / max(len(src.splitlines()), 1)
            log.log(f"Written to {out_path}", LogLevel.SUCCESS)
            log.log(f"Output: {out_lines} lines ({ratio:.1f}x expansion)", LogLevel.SUCCESS)

            self.after(0, lambda p=out_path: self._prompt_nuitka(p))

        except Exception as exc:  # noqa: BLE001
            import traceback
            tb = traceback.format_exc()
            log.log(tb, LogLevel.ERROR)
            self.after(0, lambda e=exc: self._toast.show(f"Error: {e}", kind="error"))

        finally:
            self.after(
                0,
                lambda: self._run_btn.configure(state="normal", text="\u25b6  Run Pipeline"),
            )
            self._running = False

    # ------------------------------------------------------------------
    # Nuitka compile prompt + execution
    # ------------------------------------------------------------------

    def _prompt_nuitka(self, obf_path: Path) -> None:
        root = self.winfo_toplevel()
        dlg = _CompileDialog(root, obf_path)
        root.wait_window(dlg)

        if not dlg.result:
            self._toast.show("Obfuscation complete. Skipped Nuitka.", kind="success")
            return

        chosen_out  = getattr(dlg, "_chosen_out",        "").strip() or str(obf_path.parent / "dist")
        standalone  = getattr(dlg, "_chosen_standalone",  True)
        noconsole   = getattr(dlg, "_chosen_noconsole",   False)

        self._toast.show("Starting Nuitka compilation...", kind="info")
        self._log.log("", LogLevel.INFO)
        self._log.log("=" * 60, LogLevel.INFO)
        self._log.log("STAGE 2 \u2014 Nuitka Compilation", LogLevel.INFO)
        self._log.log("=" * 60, LogLevel.INFO)

        threading.Thread(
            target=self._run_nuitka,
            args=(obf_path, chosen_out, standalone, noconsole),
            daemon=True,
        ).start()

    def _run_nuitka(
        self,
        obf_path: Path,
        out_dir: str,
        standalone: bool,
        noconsole: bool,
    ) -> None:
        log = self._log
        try:
            runner = NuitkaRunner(log_callback=lambda line: log.log(line, LogLevel.INFO))
            runner.check_available()
            exe_path = runner.compile(
                source_path=obf_path,
                output_dir=out_dir,
                standalone=standalone,
                windows_disable_console=noconsole,
            )
            self.after(0, lambda: self._on_nuitka_success(exe_path))
        except NuitkaError as exc:
            log.log(f"Nuitka error: {exc}", LogLevel.ERROR)
            self.after(0, lambda e=exc: self._toast.show(f"Nuitka failed: {e}", kind="error"))
        except Exception as exc:  # noqa: BLE001
            log.log(f"Unexpected error: {exc}", LogLevel.ERROR)
            self.after(0, lambda e=exc: self._toast.show(f"Error: {e}", kind="error"))

    def _on_nuitka_success(self, exe_path: Path) -> None:
        self._log.log(f"\u2714 Binary ready: {exe_path}", LogLevel.SUCCESS)
        self._toast.show("Compiled successfully!", kind="success")
        self._state["last_exe"] = str(exe_path)

        root = self.winfo_toplevel()
        dlg = ctk.CTkToplevel(root)
        dlg.title("Build Complete")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            dlg, text="\u2714  Build complete!",
            font=("Segoe UI", 16, "bold"),
        ).grid(row=0, column=0, columnspan=2, padx=24, pady=(20, 6), sticky="w")

        ctk.CTkLabel(
            dlg, text=str(exe_path),
            font=("Consolas", 11),
            text_color=("#444444", "#aaaaaa"),
            wraplength=380, anchor="w",
        ).grid(row=1, column=0, columnspan=2, padx=24, pady=(0, 16), sticky="w")

        btn_frame = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=24, pady=(0, 20))
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            btn_frame, text="Open Folder",
            fg_color="transparent", border_width=1,
            text_color=("#333333", "#cccccc"),
            font=("Segoe UI", 13),
            command=lambda: (
                os.startfile(str(exe_path.parent))
                if sys.platform == "win32"
                else subprocess.Popen(
                    ["open" if sys.platform == "darwin" else "xdg-open", str(exe_path.parent)]
                ),
                dlg.destroy(),
            ),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            btn_frame, text="Close",
            font=("Segoe UI", 13, "bold"),
            command=dlg.destroy,
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        dlg.update_idletasks()
        px = root.winfo_x() + (root.winfo_width()  - dlg.winfo_width())  // 2
        py = root.winfo_y() + (root.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{px}+{py}")
