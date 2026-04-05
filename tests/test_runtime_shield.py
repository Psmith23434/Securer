"""
Tests for Stage 3 — RuntimeShield

These tests monkeypatch os._exit so the process is NOT killed during
testing.  They verify:
  - No-op when no debugger is present and no hash is configured
  - Anti-debug path triggers when the Windows check returns True
  - Integrity check passes when hash matches
  - Integrity check kills when hash does NOT match
  - compute_current_hash() returns a 64-char hex string
  - _safe_compare() is constant-time safe
"""

from __future__ import annotations

import hashlib
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from securer.runtime_shield import (
    RuntimeShield,
    _compute_exe_sha256,
    _safe_compare,
    _timing_debugger_heuristic,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _ExitCalled(Exception):
    """Raised by the monkeypatched os._exit to prevent process termination."""
    def __init__(self, code: int) -> None:
        self.code = code
        super().__init__(f"os._exit({code}) called")


@pytest.fixture(autouse=True)
def _patch_exit(monkeypatch):
    """Replace os._exit with a raising stub for all tests."""
    monkeypatch.setattr(os, "_exit", lambda code: (_ for _ in ()).throw(_ExitCalled(code)))


# ---------------------------------------------------------------------------
# _safe_compare
# ---------------------------------------------------------------------------

class TestSafeCompare:
    def test_equal_strings(self):
        assert _safe_compare("abc", "abc") is True

    def test_unequal_strings(self):
        assert _safe_compare("abc", "xyz") is False

    def test_different_lengths(self):
        # hmac.compare_digest returns False for different lengths
        assert _safe_compare("a", "aa") is False

    def test_empty_strings(self):
        assert _safe_compare("", "") is True

    def test_case_sensitive(self):
        assert _safe_compare("ABC", "abc") is False


# ---------------------------------------------------------------------------
# _timing_debugger_heuristic
# ---------------------------------------------------------------------------

class TestTimingHeuristic:
    def test_returns_bool(self):
        result = _timing_debugger_heuristic(threshold_ms=50.0)
        assert isinstance(result, bool)

    def test_very_high_threshold_always_false(self):
        # 1 000 000 ms threshold — will never trigger in real execution
        assert _timing_debugger_heuristic(threshold_ms=1_000_000) is False


# ---------------------------------------------------------------------------
# _compute_exe_sha256
# ---------------------------------------------------------------------------

class TestComputeExeSha256:
    def test_known_file(self, tmp_path):
        f = tmp_path / "dummy.exe"
        f.write_bytes(b"hello world")
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert _compute_exe_sha256(f) == expected

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.exe"
        f.write_bytes(b"")
        expected = hashlib.sha256(b"").hexdigest()
        assert _compute_exe_sha256(f) == expected

    def test_large_file_chunked(self, tmp_path):
        """File > 1 MiB chunk size to exercise the iteration loop."""
        data = b"A" * (2 << 20)  # 2 MiB
        f = tmp_path / "big.exe"
        f.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert _compute_exe_sha256(f) == expected


# ---------------------------------------------------------------------------
# RuntimeShield._check_debugger
# ---------------------------------------------------------------------------

class TestCheckDebugger:
    def test_no_debugger_no_exit(self):
        """Normal run — should NOT call os._exit."""
        with patch("securer.runtime_shield._windows_debugger_present", return_value=False), \
             patch("securer.runtime_shield._timing_debugger_heuristic", return_value=False):
            # Must not raise _ExitCalled
            RuntimeShield._check_debugger(strict_timing=True)

    def test_windows_debugger_detected_exits(self):
        with patch("securer.runtime_shield._windows_debugger_present", return_value=True), \
             patch("securer.runtime_shield.platform.system", return_value="Windows"):
            with pytest.raises(_ExitCalled) as exc_info:
                RuntimeShield._check_debugger(exit_code=1)
            assert exc_info.value.code == 1

    def test_timing_heuristic_exits_when_strict(self):
        with patch("securer.runtime_shield._windows_debugger_present", return_value=False), \
             patch("securer.runtime_shield._timing_debugger_heuristic", return_value=True):
            with pytest.raises(_ExitCalled) as exc_info:
                RuntimeShield._check_debugger(strict_timing=True, exit_code=2)
            assert exc_info.value.code == 2

    def test_timing_heuristic_ignored_when_not_strict(self):
        with patch("securer.runtime_shield._windows_debugger_present", return_value=False), \
             patch("securer.runtime_shield._timing_debugger_heuristic", return_value=True):
            # strict_timing=False — timing result ignored, no exit
            RuntimeShield._check_debugger(strict_timing=False)


# ---------------------------------------------------------------------------
# RuntimeShield._check_integrity
# ---------------------------------------------------------------------------

class TestCheckIntegrity:
    def test_no_hash_skips_check(self):
        """expected_hash=None → skip, no exit."""
        RuntimeShield._check_integrity(expected_hash=None)

    def test_matching_hash_no_exit(self, tmp_path):
        exe = tmp_path / "app.exe"
        exe.write_bytes(b"real binary content")
        good_hash = hashlib.sha256(b"real binary content").hexdigest()

        with patch("securer.runtime_shield._resolve_exe_path", return_value=exe):
            RuntimeShield._check_integrity(expected_hash=good_hash)

    def test_mismatched_hash_exits(self, tmp_path):
        exe = tmp_path / "app.exe"
        exe.write_bytes(b"patched binary")
        wrong_hash = hashlib.sha256(b"original binary").hexdigest()

        with patch("securer.runtime_shield._resolve_exe_path", return_value=exe):
            with pytest.raises(_ExitCalled) as exc_info:
                RuntimeShield._check_integrity(expected_hash=wrong_hash, exit_code=1)
            assert exc_info.value.code == 1

    def test_unresolvable_exe_exits(self):
        with patch("securer.runtime_shield._resolve_exe_path", return_value=None):
            with pytest.raises(_ExitCalled):
                RuntimeShield._check_integrity(expected_hash="somehash", exit_code=1)


# ---------------------------------------------------------------------------
# RuntimeShield.guard() — integration
# ---------------------------------------------------------------------------

class TestGuard:
    def test_guard_clean_run(self):
        """No debugger, no hash → guard() returns normally."""
        with patch("securer.runtime_shield._windows_debugger_present", return_value=False):
            RuntimeShield.guard(expected_hash=None, strict_timing=False)

    def test_guard_uses_class_hash(self, tmp_path):
        exe = tmp_path / "app.exe"
        exe.write_bytes(b"content")
        h = hashlib.sha256(b"content").hexdigest()
        RuntimeShield.EXPECTED_HASH = h
        try:
            with patch("securer.runtime_shield._windows_debugger_present", return_value=False), \
                 patch("securer.runtime_shield._resolve_exe_path", return_value=exe):
                RuntimeShield.guard(strict_timing=False)
        finally:
            RuntimeShield.EXPECTED_HASH = None


# ---------------------------------------------------------------------------
# RuntimeShield.compute_current_hash()
# ---------------------------------------------------------------------------

class TestComputeCurrentHash:
    def test_returns_64_char_hex(self, tmp_path):
        exe = tmp_path / "app.exe"
        exe.write_bytes(b"some exe bytes")
        with patch("securer.runtime_shield._resolve_exe_path", return_value=exe):
            h = RuntimeShield.compute_current_hash()
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_raises_when_path_unresolvable(self):
        with patch("securer.runtime_shield._resolve_exe_path", return_value=None):
            with pytest.raises(RuntimeError, match="Cannot resolve"):
                RuntimeShield.compute_current_hash()
