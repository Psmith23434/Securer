"""
Stage 1a — String Encryption
============================
Transforms every string literal in a Python AST into an encrypted byte blob
decrypted at runtime via a shared XOR lambda.

Design goals:
  - Each string gets a unique random key (0x01–0xFE) so identical strings
    produce different ciphertext across the file.
  - Each decryptor lambda has a unique generated name so no single grep
    pattern finds all of them.
  - ALL helper assignments (_dec_, _key_, _dat_) are hoisted to MODULE LEVEL
    as a preamble block.  This avoids injecting closures inside function
    bodies, which caused Nuitka's zig C backend to segfault when compiling
    functions with many nested lambdas.
  - The transformation is purely AST-based — no regex, no text munging.
  - F-strings (JoinedStr nodes) are skipped entirely.
  - Docstrings on modules, classes, and functions are preserved as-is.
    Pass preserve_docstrings=False to encrypt those too.
  - The output is valid Python that can be parsed, imported, and compiled
    by Nuitka without modification.

Usage:
    from securer.string_encryptor import StringEncryptor

    enc = StringEncryptor(seed=42)
    transformed_ast = enc.transform(source_code)
    output_source = enc.unparse(transformed_ast)

The seed controls key generation. Use a different seed per build for
maximum variation between releases.
"""

import ast
import random
from typing import Optional


class StringEncryptor(ast.NodeTransformer):
    """
    AST NodeTransformer that encrypts string literals.

    All helper statements (_dec_XXXX, _key_XXXX, _dat_XXXX) are collected
    during the tree walk and injected as a single preamble at the top of
    the module body — never inside function or class bodies.  This means
    Nuitka sees only simple module-level assignments and no nested closures
    inside functions, which eliminates the zig-backend segfault.
    """

    def __init__(
        self,
        seed: Optional[int] = None,
        preserve_docstrings: bool = True,
        min_length: int = 3,
    ):
        """
        Args:
            seed: RNG seed for reproducible builds. None = random each run.
            preserve_docstrings: If True, module/class/function docstrings
                are left as plain strings.
            min_length: Strings shorter than this are left unencrypted.
        """
        self._rng = random.Random(seed)
        self._preserve_docstrings = preserve_docstrings
        self._min_length = min_length

        self._used_names: set[str] = set()
        self._docstring_ids: set[int] = set()

        # All helper stmts accumulated here during the full tree walk.
        # Injected at module level by visit_Module after visiting children.
        self._module_helpers: list[ast.stmt] = []

        self.count: int = 0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def transform(self, source: str) -> ast.Module:
        """Parse *source*, encrypt strings, return the modified AST."""
        tree = ast.parse(source)
        if self._preserve_docstrings:
            self._collect_docstrings(tree)
        new_tree = self.visit(tree)
        ast.fix_missing_locations(new_tree)
        return new_tree

    @staticmethod
    def unparse(tree: ast.AST) -> str:
        """Convert the modified AST back to source code (Python 3.9+)."""
        return ast.unparse(tree)

    def transform_file(self, input_path: str, output_path: str) -> None:
        """Convenience: read file, encrypt, write result."""
        with open(input_path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = self.transform(source)
        result = self.unparse(tree)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result)

    # ------------------------------------------------------------------
    # Docstring detection
    # ------------------------------------------------------------------

    def _collect_docstrings(self, tree: ast.Module) -> None:
        """Mark Constant nodes that are docstrings so we skip them."""
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if (
                    node.body
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)
                ):
                    self._docstring_ids.add(id(node.body[0].value))

    # ------------------------------------------------------------------
    # Name generation
    # ------------------------------------------------------------------

    def _unique_tag(self) -> str:
        """Generate a short unique hex tag like 'a3f1'."""
        while True:
            tag = format(self._rng.randint(0x1000, 0xFFFF), 'x')
            if tag not in self._used_names:
                self._used_names.add(tag)
                return tag

    def _make_names(self, tag: str) -> tuple[str, str, str]:
        """Return (decryptor_name, key_name, data_name) for a given tag."""
        return f"_dec_{tag}", f"_key_{tag}", f"_dat_{tag}"

    # ------------------------------------------------------------------
    # Encryption
    # ------------------------------------------------------------------

    @staticmethod
    def _encrypt(plaintext: str, key: int) -> bytes:
        """XOR-encrypt *plaintext* (UTF-8) with single-byte *key* (1-254)."""
        raw = plaintext.encode("utf-8")
        return bytes(b ^ key for b in raw)

    # ------------------------------------------------------------------
    # AST node builders
    # ------------------------------------------------------------------

    def _build_decryptor_assign(self, dec_name: str) -> ast.Assign:
        """
        Build module-level:
            _dec_XXXX = lambda k, d: bytes(a ^ b for a, b in zip(d, bytes([k]) * len(d))).decode('utf-8', errors='replace')
        """
        source = (
            f"{dec_name} = "
            "lambda k, d: "
            "bytes(a ^ b for a, b in zip(d, bytes([k]) * len(d)))"
            ".decode('utf-8', errors='replace')"
        )
        return ast.parse(source, mode="exec").body[0]  # type: ignore[return-value]

    def _build_key_assign(self, key_name: str, key: int) -> ast.Assign:
        """Build module-level: _key_XXXX = 0xKK"""
        return ast.Assign(
            targets=[ast.Name(id=key_name, ctx=ast.Store())],
            value=ast.Constant(value=key),
            lineno=0,
            col_offset=0,
        )

    def _build_data_assign(self, dat_name: str, ciphertext: bytes) -> ast.Assign:
        """Build module-level: _dat_XXXX = b'...'"""
        return ast.Assign(
            targets=[ast.Name(id=dat_name, ctx=ast.Store())],
            value=ast.Constant(value=ciphertext),
            lineno=0,
            col_offset=0,
        )

    def _build_call(self, dec_name: str, key_name: str, dat_name: str) -> ast.Call:
        """Build: _dec_XXXX(_key_XXXX, _dat_XXXX) — replaces the original string."""
        return ast.Call(
            func=ast.Name(id=dec_name, ctx=ast.Load()),
            args=[
                ast.Name(id=key_name, ctx=ast.Load()),
                ast.Name(id=dat_name, ctx=ast.Load()),
            ],
            keywords=[],
        )

    # ------------------------------------------------------------------
    # NodeTransformer overrides
    # ------------------------------------------------------------------

    def visit_Module(self, node: ast.Module) -> ast.Module:
        """
        Visit all children first (populates self._module_helpers),
        then prepend the entire helper preamble to the module body.
        """
        self.generic_visit(node)
        if self._module_helpers:
            node.body = self._module_helpers + node.body
        return node

    def visit_JoinedStr(self, node: ast.JoinedStr) -> ast.JoinedStr:
        """
        Skip f-strings entirely — their Constant sub-nodes are literal
        fragments mixed with expressions; replacing them with Call nodes
        produces invalid AST.
        """
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        """
        Replace string constants with a decryptor call.
        Helper assignments are appended to self._module_helpers (hoisted
        to module level) — NOT injected into the local statement list.
        """
        if not isinstance(node.value, str):
            return node
        if id(node) in self._docstring_ids:
            return node
        if len(node.value) < self._min_length:
            return node

        tag = self._unique_tag()
        dec_name, key_name, dat_name = self._make_names(tag)

        key = self._rng.randint(1, 254)
        ciphertext = self._encrypt(node.value, key)

        # Hoist helpers to module level — avoids nested closures in functions
        self._module_helpers.append(self._build_decryptor_assign(dec_name))
        self._module_helpers.append(self._build_key_assign(key_name, key))
        self._module_helpers.append(self._build_data_assign(dat_name, ciphertext))
        self.count += 1

        return self._build_call(dec_name, key_name, dat_name)


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------

def encrypt_strings(
    source: str,
    seed: Optional[int] = None,
    preserve_docstrings: bool = True,
    min_length: int = 3,
) -> str:
    """
    One-liner: encrypt all strings in *source* and return the new source.

    Example::

        obfuscated = encrypt_strings(open('app.py').read(), seed=1337)
        open('app_obf.py', 'w').write(obfuscated)
    """
    enc = StringEncryptor(
        seed=seed,
        preserve_docstrings=preserve_docstrings,
        min_length=min_length,
    )
    tree = enc.transform(source)
    return enc.unparse(tree)
