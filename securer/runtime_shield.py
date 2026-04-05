"""
Stage 3 — Runtime Shield
========================
Two independent defences that wrap the *compiled* executable output,
not the Python source.

1. Anti-debug guard
   Windows:  IsDebuggerPresent()  + NtQueryInformationProcess (remote debugger)
   Fallback: timing-delta heuristic (≥50 ms gap between two perf_counter calls
             indicates single-stepping under a debugger)

2. Binary self-integrity check
   SHA-256 of the running executable is compared against a known-good hash
   embedded at build time.  Any byte-patch or loader injection causes an
   immediate exit.

Usage — embed this call at the very first line of your entry point:

    from securer.runtime_shield import RuntimeShield
    RuntimeShield.guard()   # raises RuntimeError or calls os._exit(1) on failure

The public API is intentionally tiny so that every compiled app can call
it identically regardless of what stage-1 mangling has renamed.
"""

from __future__ import annotations

import hashlib
import os
import platform
import sys
import time
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _windows_debugger_present() -> bool:
    """Return True if a debugger is attached (Windows only)."""
    try:
        import ctypes
        import ctypes.wintypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

        # --- Check 1: IsDebuggerPresent ---
        if kernel32.IsDebuggerPresent():
            return True

        # --- Check 2: NtQueryInformationProcess (catches remote debuggers) ---
        ntdll = ctypes.windll.ntdll  # type: ignore[attr-defined]
        ProcessDebugPort = 7
        debug_port = ctypes.c_ulong(0)
        status = ntdll.NtQueryInformationProcess(
            kernel32.GetCurrentProcess(),
            ProcessDebugPort,
            ctypes.byref(debug_port),
            ctypes.sizeof(debug_port),
            None,
        )
        if status == 0 and debug_port.value != 0:
            return True

    except Exception:  # noqa: BLE001
        pass
    return False


def _timing_debugger_heuristic(threshold_ms: float = 50.0) -> bool:
    """
    A debugger stepping through code slows execution measurably.
    Two back-to-back perf_counter samples should be < 1 µs apart in
    normal execution.  If they are > *threshold_ms* ms apart we assume
    a breakpoint was hit between them.
    """
    t0 = time.perf_counter()
    # trivial work that a real optimiser will not strip
    _ = sum(i * i for i in range(8))
    t1 = time.perf_counter()
    return (t1 - t0) * 1000 > threshold_ms


def _compute_exe_sha256(exe_path: Path) -> str:
    """SHA-256 hex digest of the executable file, read in 1 MiB chunks."""
    h = hashlib.sha256()
    with exe_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_exe_path() -> Optional[Path]:
    """Return the path to the running executable (Nuitka .exe or python.exe)."""
    # sys.executable is reliable both under Nuitka and CPython
    exe = Path(sys.executable).resolve()
    if exe.exists():
        return exe
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class RuntimeShield:
    """
    Static helper class.  Call ``RuntimeShield.guard()`` once at process
    startup to activate all runtime defences.

    Parameters
    ----------
    expected_hash : str | None
        The SHA-256 hex digest that the running executable *should* have.
        Embed this value at build time (see ``build/build_securer.py``).
        Pass ``None`` (default) to skip the integrity check — useful during
        development / testing.
    strict_timing : bool
        If *True*, the timing heuristic is also used as a kill signal on
        non-Windows platforms (where ctypes checks are unavailable).
    exit_code : int
        ``os._exit`` code used on failure.  Defaults to 1.
    """

    # Set at build time by build/build_securer.py
    # e.g. RuntimeShield.EXPECTED_HASH = "a3f1...de09"
    EXPECTED_HASH: Optional[str] = None

    @classmethod
    def guard(
        cls,
        expected_hash: Optional[str] = None,
        strict_timing: bool = False,
        exit_code: int = 1,
    ) -> None:
        """
        Run all enabled checks.  Terminates the process immediately
        (``os._exit``) on any failure — no exception is catchable by
        the attacker's harness.

        Raises
        ------
        RuntimeError
            In test / non-fatal mode when ``os._exit`` is monkeypatched.
        """
        cls._check_debugger(strict_timing=strict_timing, exit_code=exit_code)
        cls._check_integrity(
            expected_hash=expected_hash or cls.EXPECTED_HASH,
            exit_code=exit_code,
        )

    # ------------------------------------------------------------------
    # Sub-checks (exposed for unit testing)
    # ------------------------------------------------------------------

    @classmethod
    def _check_debugger(
        cls,
        strict_timing: bool = False,
        exit_code: int = 1,
    ) -> None:
        """Kill process if a debugger is detected."""
        detected = False

        if platform.system() == "Windows":
            detected = _windows_debugger_present()

        if not detected and strict_timing:
            detected = _timing_debugger_heuristic()

        if detected:
            os._exit(exit_code)  # noqa: SLF001

    @classmethod
    def _check_integrity(
        cls,
        expected_hash: Optional[str],
        exit_code: int = 1,
    ) -> None:
        """
        If *expected_hash* is provided, verify the running executable
        matches it.  Skip silently when *expected_hash* is None (dev mode).
        """
        if expected_hash is None:
            return

        exe_path = _resolve_exe_path()
        if exe_path is None:
            # Cannot determine exe path — fail safe
            os._exit(exit_code)  # noqa: SLF001

        actual = _compute_exe_sha256(exe_path)
        if not _safe_compare(actual, expected_hash):
            os._exit(exit_code)  # noqa: SLF001

    @classmethod
    def compute_current_hash(cls) -> str:
        """
        Convenience method: return the SHA-256 of the running executable.
        Call this *once* after a clean build to obtain the value you should
        embed as ``RuntimeShield.EXPECTED_HASH`` in the next build.

        Example (in build/build_securer.py)::

            from securer.runtime_shield import RuntimeShield
            print("Embed this hash:", RuntimeShield.compute_current_hash())
        """
        exe_path = _resolve_exe_path()
        if exe_path is None:
            raise RuntimeError("Cannot resolve running executable path.")
        return _compute_exe_sha256(exe_path)


# ---------------------------------------------------------------------------
# Constant-time comparison (prevents timing side-channel on hash compare)
# ---------------------------------------------------------------------------

def _safe_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to defeat timing attacks."""
    import hmac as _hmac
    return _hmac.compare_digest(
        a.encode("ascii", errors="replace"),
        b.encode("ascii", errors="replace"),
    )
