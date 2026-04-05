"""
NuitkaRunner — Stage 2 wrapper.

Runs Nuitka in a subprocess and streams stdout/stderr line-by-line
to a caller-supplied log callback.  Designed to be called from a
background thread so the GUI stays responsive.

Usage::

    from securer.nuitka_runner import NuitkaRunner, NuitkaError

    def log(line: str) -> None:
        print(line)

    runner = NuitkaRunner(log_callback=log)
    runner.check_available()          # raises NuitkaError if not installed
    exe_path = runner.compile(
        source_path="app_obf.py",
        output_dir="dist/",
        onefile=True,
        windows_disable_console=False,
    )
    print(f"Built: {exe_path}")
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional


class NuitkaError(RuntimeError):
    """Raised when Nuitka is unavailable or compilation fails."""


class NuitkaRunner:
    """
    Thin wrapper around ``python -m nuitka``.

    Parameters
    ----------
    log_callback:
        Called with each output line (str).  Must be thread-safe.
    """

    INSTALL_HINT = (
        "Nuitka is not installed.\n"
        "Install it with:\n"
        "  pip install nuitka\n"
        "You also need MSVC Build Tools on Windows:\n"
        "  https://visualstudio.microsoft.com/visual-cpp-build-tools/"
    )

    def __init__(self, log_callback: Callable[[str], None]) -> None:
        self._log = log_callback

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_available(self) -> None:
        """
        Verify Nuitka is importable via the current Python interpreter.

        Raises
        ------
        NuitkaError
            If ``python -m nuitka --version`` fails.
        """
        try:
            result = subprocess.run(
                [sys.executable, "-m", "nuitka", "--version"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode != 0:
                raise NuitkaError(self.INSTALL_HINT)
            version_line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else "unknown"
            self._log(f"Nuitka found: {version_line}")
        except FileNotFoundError:
            raise NuitkaError(self.INSTALL_HINT)
        except subprocess.TimeoutExpired:
            raise NuitkaError("Nuitka version check timed out.")

    def compile(
        self,
        source_path: str | Path,
        output_dir: str | Path,
        onefile: bool = True,
        windows_disable_console: bool = False,
        tk_inter: bool = True,
        extra_args: Optional[list[str]] = None,
    ) -> Path:
        """
        Compile *source_path* with Nuitka, streaming output to the log callback.

        Parameters
        ----------
        source_path:
            Path to the (obfuscated) `.py` file to compile.
        output_dir:
            Directory where Nuitka places the `.exe` / dist output.
        onefile:
            Pass ``--onefile`` to produce a single portable executable.
        windows_disable_console:
            Pass ``--windows-disable-console`` to suppress the console window.
        tk_inter:
            Pass ``--enable-plugin=tk-inter`` so Nuitka bundles TCL/TK DLLs.
            Required for any app that imports tkinter / customtkinter.
            Defaults to True — safe to leave on for non-Tkinter apps (no-op).
        extra_args:
            Any additional Nuitka CLI flags.

        Returns
        -------
        Path
            Path to the produced `.exe` (Windows) or binary (Linux/macOS).

        Raises
        ------
        NuitkaError
            If Nuitka exits with a non-zero return code.
        """
        source_path = Path(source_path)
        output_dir  = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable, "-m", "nuitka",
            str(source_path),
            f"--output-dir={output_dir}",
            "--assume-yes-for-downloads",
        ]
        if onefile:
            cmd.append("--onefile")
        if windows_disable_console:
            cmd.append("--windows-disable-console")
        if tk_inter:
            cmd.append("--enable-plugin=tk-inter")
        if extra_args:
            cmd.extend(extra_args)

        self._log(f"Running: {' '.join(cmd)}")
        self._log("-" * 60)

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                self._log(line.rstrip())
            proc.wait()
        except FileNotFoundError:
            raise NuitkaError(self.INSTALL_HINT)

        if proc.returncode != 0:
            raise NuitkaError(
                f"Nuitka exited with code {proc.returncode}. "
                "Check the log for details."
            )

        self._log("-" * 60)
        self._log("Nuitka compilation finished successfully.")

        exe = self._find_output(source_path.stem, output_dir)
        self._log(f"Output binary: {exe}")
        return exe

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_output(self, stem: str, output_dir: Path) -> Path:
        """Return the path of the compiled binary inside *output_dir*."""
        candidates = [
            output_dir / f"{stem}.exe",
            output_dir / stem,
        ]
        for c in candidates:
            if c.exists():
                return c

        for child in output_dir.rglob(f"{stem}*.exe"):
            return child
        for child in output_dir.rglob(stem):
            if child.is_file():
                return child

        suffix = ".exe" if sys.platform == "win32" else ""
        return output_dir / f"{stem}{suffix}"
