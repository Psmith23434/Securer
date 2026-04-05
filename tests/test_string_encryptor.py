"""
Tests for securer.string_encryptor
====================================
Every test follows the same pattern:
  1. Start with a snippet of real Python source.
  2. Run it through StringEncryptor.
  3. exec() the output in a fresh namespace.
  4. Assert the runtime behaviour is identical to the original.

This proves the encrypted output is semantically correct Python.
"""

import ast
import pytest
from securer.string_encryptor import StringEncryptor, encrypt_strings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(source: str) -> dict:
    """Execute *source* and return its global namespace."""
    ns: dict = {}
    exec(compile(source, "<test>", "exec"), ns)  # noqa: S102
    return ns


def obf_run(source: str, seed: int = 42) -> dict:
    """Obfuscate *source* then execute it; return namespace."""
    obfuscated = encrypt_strings(source, seed=seed)
    return run(obfuscated)


# ---------------------------------------------------------------------------
# Round-trip correctness
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_simple_assignment(self):
        src = 'msg = "hello world"'
        ns = obf_run(src)
        assert ns["msg"] == "hello world"

    def test_multiple_strings(self):
        src = textwrap = '''
name = "Alice"
greeting = "Hello, Alice!"
url = "https://example.com"
'''
        ns = obf_run(src)
        assert ns["name"] == "Alice"
        assert ns["greeting"] == "Hello, Alice!"
        assert ns["url"] == "https://example.com"

    def test_string_in_function(self):
        src = '''
def get_token():
    return "secret-token-abc123"
'''
        ns = obf_run(src)
        assert ns["get_token"]() == "secret-token-abc123"

    def test_string_in_class(self):
        src = '''
class Config:
    BASE_URL = "https://api.example.com"
    VERSION = "v2"
'''
        ns = obf_run(src)
        assert ns["Config"].BASE_URL == "https://api.example.com"
        assert ns["Config"].VERSION == "v2"

    def test_unicode_strings(self):
        src = 'msg = "Ünïcödé strïng: \u4e2d\u6587"'
        ns = obf_run(src)
        assert ns["msg"] == "Ünïcödé strïng: \u4e2d\u6587"

    def test_string_with_newlines(self):
        src = 'block = "line one\\nline two\\nline three"'
        ns = obf_run(src)
        assert "line one" in ns["block"]
        assert "line three" in ns["block"]

    def test_string_in_list(self):
        src = 'items = ["alpha", "beta", "gamma"]'
        ns = obf_run(src)
        assert ns["items"] == ["alpha", "beta", "gamma"]

    def test_string_in_dict(self):
        src = 'cfg = {"host": "localhost", "port": "5432"}'
        ns = obf_run(src)
        assert ns["cfg"]["host"] == "localhost"

    def test_string_comparison(self):
        src = '''
password = "correct-horse-battery"
result = (password == "correct-horse-battery")
'''
        ns = obf_run(src)
        assert ns["result"] is True

    def test_f_string_left_alone(self):
        """f-strings must not be broken — they are JoinedStr nodes, not Constant."""
        src = '''
name = "World"
msg = f"Hello, {name}!"
'''
        ns = obf_run(src)
        assert ns["msg"] == "Hello, World!"


# ---------------------------------------------------------------------------
# Preservation of non-string literals
# ---------------------------------------------------------------------------

class TestNonStringPreservation:
    def test_integers_untouched(self):
        src = "x = 42"
        ns = obf_run(src)
        assert ns["x"] == 42

    def test_float_untouched(self):
        src = "pi = 3.14159"
        ns = obf_run(src)
        assert abs(ns["pi"] - 3.14159) < 1e-9

    def test_none_untouched(self):
        src = "val = None"
        ns = obf_run(src)
        assert ns["val"] is None

    def test_bool_untouched(self):
        src = "flag = True"
        ns = obf_run(src)
        assert ns["flag"] is True

    def test_bytes_untouched(self):
        src = "data = b'hello'"
        ns = obf_run(src)
        assert ns["data"] == b"hello"


# ---------------------------------------------------------------------------
# Docstring preservation
# ---------------------------------------------------------------------------

class TestDocstrings:
    def test_module_docstring_preserved(self):
        src = '"""This is the module docstring."""\nx = 1'
        enc = StringEncryptor(seed=0, preserve_docstrings=True)
        tree = enc.transform(src)
        out = enc.unparse(tree)
        # The docstring should still appear as a plain string literal
        assert '"""This is the module docstring."""' in out or "'This is the module docstring.'" in out

    def test_function_docstring_preserved(self):
        src = '''
def foo():
    """Does foo things."""
    return "result-value"
'''
        enc = StringEncryptor(seed=0, preserve_docstrings=True)
        tree = enc.transform(src)
        out = enc.unparse(tree)
        # Docstring intact, body string encrypted
        assert "Does foo things" in out
        # The return value string should be encrypted (not appear verbatim)
        assert "result-value" not in out

    def test_docstrings_encrypted_when_disabled(self):
        src = '"""Secret module."""'
        enc = StringEncryptor(seed=0, preserve_docstrings=False)
        tree = enc.transform(src)
        out = enc.unparse(tree)
        assert "Secret module" not in out


# ---------------------------------------------------------------------------
# Min-length threshold
# ---------------------------------------------------------------------------

class TestMinLength:
    def test_short_strings_skipped(self):
        src = 'x = "hi"'  # length 2, below default min_length=3
        enc = StringEncryptor(seed=0, min_length=3)
        tree = enc.transform(src)
        out = enc.unparse(tree)
        assert "'hi'" in out or '"hi"' in out

    def test_exact_min_length_encrypted(self):
        src = 'x = "abc"'  # length 3, exactly at threshold
        enc = StringEncryptor(seed=0, min_length=3)
        tree = enc.transform(src)
        out = enc.unparse(tree)
        assert "abc" not in out


# ---------------------------------------------------------------------------
# Determinism and uniqueness
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_seed_same_output(self):
        src = 'x = "deterministic"'
        out1 = encrypt_strings(src, seed=100)
        out2 = encrypt_strings(src, seed=100)
        assert out1 == out2

    def test_different_seeds_different_output(self):
        src = 'x = "varies by seed"'
        out1 = encrypt_strings(src, seed=1)
        out2 = encrypt_strings(src, seed=2)
        assert out1 != out2

    def test_identical_strings_get_unique_names(self):
        """Two identical string literals should produce two different decryptor names."""
        src = '''
a = "duplicate"
b = "duplicate"
'''
        enc = StringEncryptor(seed=0)
        tree = enc.transform(src)
        out = enc.unparse(tree)
        # Count occurrences of the decryptor prefix
        dec_count = out.count("_dec_")
        assert dec_count == 2


# ---------------------------------------------------------------------------
# Valid Python output
# ---------------------------------------------------------------------------

class TestValidOutput:
    def test_output_is_parseable(self):
        src = '''
import os

DEBUG = False
BASE_URL = "https://api.example.com/v2"

class AppConfig:
    name = "MyApp"
    version = "1.0.0"

def get_header():
    return {"Authorization": "Bearer secrettoken123"}
'''
        out = encrypt_strings(src, seed=99)
        # Must parse without SyntaxError
        tree = ast.parse(out)
        assert tree is not None

    def test_output_is_executable(self):
        src = '''
result = "execution works"
'''
        ns = obf_run(src)
        assert ns["result"] == "execution works"
