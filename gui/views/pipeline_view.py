"""
PipelineView — main obfuscation UI.

Layout (top-to-bottom):
  - Page header: title + subtitle
  - Input row: file path entry + Browse button
  - Stage toggles: 6 toggle switches (1a-1e + Shield)
  - Options row: seed entry + output dir
  - Run button (full width)
  - LogPanel (fills remaining space)
"""
from __future__ import annotations

import threading
from pathlib import Path
from tkinter import filedialog
from typing import Optional

import customtkinter as ctk

from gui.components.log_panel import LogPanel, LogLevel
from gui.components.toast import ToastManager


STAGE_META = [
    ("1a_strings",    "1a", "String Encryption",    "XOR-encrypt every string literal"),
    ("1b_names",      "1b", "Name Mangling",         "Rename all identifiers to _X{hash}"),
    ("1c_flow",       "1c", "Flow Flattening",       "Rewrite functions as state machines"),
    ("1d_predicates", "1d", "Opaque Predicates",     "Insert always-true/false guard branches"),
    ("1e_deadcode",   "1e", "Dead Code Injection",   "Inject realistic but unreachable code"),
    ("3_shield",      " 3", "Runtime Shield",        "Anti-debug + binary integrity check"),
]


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
        self._build()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)   # log panel expands

        # --- Header ---
        self._build_header(row=0)

        # --- File input ---
        self._build_file_row(row=1)

        # --- Stage toggles ---
        self._build_stage_toggles(row=2)

        # --- Options (seed + output dir) ---
        self._build_options_row(row=3)

        # --- Run button ---
        self._run_btn = ctk.CTkButton(
            self,
            text="\u25b6  Run Pipeline",
            height=44,
            font=("Segoe UI", 14, "bold"),
            command=self._on_run,
        )
        self._run_btn.grid(row=4, column=0, sticky="ew", padx=20, pady=(8, 6))

        # --- Log panel ---
        self._log = LogPanel(self)
        self._log.grid(row=5, column=0, sticky="nsew", padx=20, pady=(0, 16))

    def _build_header(self, row: int) -> None:
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=row, column=0, sticky="ew", padx=20, pady=(20, 4))
        hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            hdr,
            text="Obfuscation Pipeline",
            font=("Segoe UI", 20, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            hdr,
            text="Select a .py file, configure stages, then run.",
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

        self._file_entry = ctk.CTkEntry(
            frame,
            placeholder_text="Path to your .py source file...",
            height=36,
            font=("Segoe UI", 12),
        )
        self._file_entry.grid(row=1, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(
            frame,
            text="Browse",
            width=80,
            height=36,
            font=("Segoe UI", 12),
            command=self._browse_file,
        ).grid(row=1, column=1)

    def _build_stage_toggles(self, row: int) -> None:
        outer = ctk.CTkFrame(
            self,
            fg_color=("#f0f0f0", "#1e1e1e"),
            corner_radius=10,
        )
        outer.grid(row=row, column=0, sticky="ew", padx=20, pady=6)

        ctk.CTkLabel(
            outer,
            text="Stages",
            font=("Segoe UI", 12, "bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=6, sticky="w", padx=14, pady=(10, 6))

        # 6 toggle cards in a single row
        for col, (key, badge, name, tip) in enumerate(STAGE_META):
            outer.grid_columnconfigure(col, weight=1)
            card = ctk.CTkFrame(
                outer,
                fg_color=("#ffffff", "#2a2a2a"),
                corner_radius=8,
            )
            card.grid(row=1, column=col, sticky="ew", padx=6, pady=(0, 10))

            # Badge
            ctk.CTkLabel(
                card,
                text=badge,
                font=("Consolas", 10, "bold"),
                text_color=("#888888", "#666666"),
                anchor="w",
            ).grid(row=0, column=0, sticky="w", padx=(10, 0), pady=(8, 0))

            # Name
            ctk.CTkLabel(
                card,
                text=name,
                font=("Segoe UI", 11, "bold"),
                anchor="w",
                wraplength=120,
            ).grid(row=1, column=0, sticky="w", padx=10)

            # Tip
            ctk.CTkLabel(
                card,
                text=tip,
                font=("Segoe UI", 10),
                text_color=("#888888", "#666666"),
                anchor="w",
                wraplength=120,
            ).grid(row=2, column=0, sticky="w", padx=10, pady=(2, 8))

            # Toggle
            var = ctk.BooleanVar(value=self._state["stages"][key])
            self._toggle_vars[key] = var
            switch = ctk.CTkSwitch(
                card,
                text="",
                variable=var,
                width=46,
                command=lambda k=key, v=var: self._on_toggle(k, v),
            )
            switch.grid(row=3, column=0, sticky="w", padx=8, pady=(0, 8))

    def _build_options_row(self, row: int) -> None:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=20, pady=(4, 4))
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_columnconfigure(3, weight=2)

        # Seed
        ctk.CTkLabel(frame, text="Seed", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        self._seed_entry = ctk.CTkEntry(frame, width=80, height=34, font=("Consolas", 12))
        self._seed_entry.insert(0, str(self._state.get("seed", 42)))
        self._seed_entry.grid(row=0, column=1, sticky="w", padx=(0, 20))

        # Output dir
        ctk.CTkLabel(frame, text="Output dir", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=2, sticky="w", padx=(0, 8)
        )
        self._outdir_entry = ctk.CTkEntry(
            frame,
            placeholder_text="Same as input (default)",
            height=34,
            font=("Segoe UI", 12),
        )
        if self._state.get("output_dir"):
            self._outdir_entry.insert(0, self._state["output_dir"])
        self._outdir_entry.grid(row=0, column=3, sticky="ew", padx=(0, 8))

        ctk.CTkButton(
            frame,
            text="\u2026",
            width=34,
            height=34,
            font=("Segoe UI", 14),
            command=self._browse_outdir,
        ).grid(row=0, column=4)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _browse_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Python source file",
            filetypes=[("Python files", "*.py"), ("All files", "*.*")],
        )
        if path:
            self._file_entry.delete(0, "end")
            self._file_entry.insert(0, path)
            self._state["last_input"] = path

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
        thread = threading.Thread(
            target=self._run_pipeline,
            args=(input_path,),
            daemon=True,
        )
        thread.start()

    # ------------------------------------------------------------------
    # Pipeline execution (runs in background thread)
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

            # Stage 1a
            if stages["1a_strings"]:
                log.log("Stage 1a — String Encryption...", LogLevel.INFO)
                from securer.string_encryptor import StringEncryptor
                enc = StringEncryptor(seed=seed)
                tree = enc.transform(src)
                log.log(f"  Encrypted {getattr(enc, 'count', '?')} string(s)", LogLevel.SUCCESS)
                last_module = enc
            else:
                log.log("Stage 1a — skipped", LogLevel.INFO)

            # Stage 1b
            if stages["1b_names"]:
                log.log("Stage 1b — Name Mangling...", LogLevel.INFO)
                from securer.name_mangler import NameMangler
                mg = NameMangler(seed=seed)
                if tree is None:
                    import ast
                    tree = ast.parse(src)
                tree = mg.transform_tree(tree)
                log.log(f"  Mangled {len(mg.mapping)} identifier(s)", LogLevel.SUCCESS)
                last_module = mg
            else:
                log.log("Stage 1b — skipped", LogLevel.INFO)

            # Stage 1c
            if stages["1c_flow"]:
                log.log("Stage 1c — Flow Flattening...", LogLevel.INFO)
                from securer.flow_flattener import FlowFlattener
                ff = FlowFlattener(seed=seed)
                if tree is None:
                    import ast
                    tree = ast.parse(src)
                tree = ff.transform_tree(tree)
                log.log(f"  Flattened {getattr(ff, 'functions_transformed', '?')} function(s)", LogLevel.SUCCESS)
                last_module = ff
            else:
                log.log("Stage 1c — skipped", LogLevel.INFO)

            # Stage 1d
            if stages["1d_predicates"]:
                log.log("Stage 1d — Opaque Predicates...", LogLevel.INFO)
                from securer.opaque_predicates import OpaquePredicates
                op = OpaquePredicates(seed=seed)
                if tree is None:
                    import ast
                    tree = ast.parse(src)
                tree = op.transform_tree(tree)
                log.log(f"  Injected predicates", LogLevel.SUCCESS)
                last_module = op
            else:
                log.log("Stage 1d — skipped", LogLevel.INFO)

            # Stage 1e
            if stages["1e_deadcode"]:
                log.log("Stage 1e — Dead Code Injection...", LogLevel.INFO)
                from securer.dead_code_injector import DeadCodeInjector
                di = DeadCodeInjector(seed=seed)
                if tree is None:
                    import ast
                    tree = ast.parse(src)
                tree = di.transform_tree(tree)
                stats = getattr(di, 'stats', {})
                injected = stats.get('injected', '?') if isinstance(stats, dict) else '?'
                log.log(f"  Injected {injected} dead block(s)", LogLevel.SUCCESS)
                last_module = di
            else:
                log.log("Stage 1e — skipped", LogLevel.INFO)

            # Unparse
            if tree is not None:
                if last_module and hasattr(last_module, "unparse"):
                    output_src = last_module.unparse(tree)
                else:
                    import ast
                    output_src = ast.unparse(tree)
            else:
                log.log("No stages active — writing original source.", LogLevel.WARNING)
                output_src = src

            # Stage 3 shield header
            if stages["3_shield"]:
                log.log("Stage 3 — prepending RuntimeShield.guard() call...", LogLevel.INFO)
                shield_header = (
                    "from securer.runtime_shield import RuntimeShield\n"
                    "RuntimeShield.guard()  # anti-debug + integrity check\n\n"
                )
                output_src = shield_header + output_src
                log.log("  Shield header prepended", LogLevel.SUCCESS)

            # Write output
            in_path = Path(input_path)
            out_dir = state.get("output_dir", "").strip()
            if out_dir:
                out_path = Path(out_dir) / (in_path.stem + "_obf.py")
            else:
                out_path = in_path.parent / (in_path.stem + "_obf.py")

            out_path.write_text(output_src, encoding="utf-8")
            state["last_output"] = str(out_path)

            out_lines = len(output_src.splitlines())
            ratio = out_lines / max(len(src.splitlines()), 1)
            log.log(f"Written to {out_path}", LogLevel.SUCCESS)
            log.log(
                f"Output: {out_lines} lines ({ratio:.1f}x expansion)",
                LogLevel.SUCCESS,
            )
            self.after(0, lambda: self._toast.show("Pipeline complete!", kind="success"))

        except Exception as exc:  # noqa: BLE001
            log.log(f"ERROR: {exc}", LogLevel.ERROR)
            self.after(0, lambda: self._toast.show(f"Error: {exc}", kind="error"))

        finally:
            self.after(
                0,
                lambda: self._run_btn.configure(
                    state="normal", text="\u25b6  Run Pipeline"
                ),
            )
            self._running = False
