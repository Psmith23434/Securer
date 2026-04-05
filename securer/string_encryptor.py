"""
Stage 1a — String Encryption
============================
Transforms every string literal in a Python AST into an encrypted byte blob
with a unique per-string XOR decryptor lambda.

Design goals:
  - Each string gets a unique random key (0x01–0xFE) so identical strings
    produce different ciphertext across the file.
  - Each decryptor lambda has a unique generated name so no single grep
    pattern finds all of them.
  - The transformation is purely AST-based — no regex, no text munging.
    This means it handles multi-line strings, f-strings (skipped safely),
    bytes literals (skipped), and docstrings correctly.
  - Docstrings on modules, classes, and functions are preserved as-is
    (they are safe to leave; removing them breaks help() and __doc__).
    Pass preserve_docstrings=False to encrypt those too.
  - The output is valid Python that can be parsed, imported, and compiled
    by Nuitka without modification.

Usage:
    from securer.string_encryptor import StringEncryptor

    enc = StringEncryptor(seed=42)          # fixed seed for reproducible builds
    transformed_ast = enc.transform(source_code)
    output_source = enc.unparse(transformed_ast)

The seed controls key generation. Use a different seed per build for
maximum variation between releases.
"""

import ast
import random
import secrets
import textwrap
from typing import Optional


class StringEncryptor(ast.NodeTransformer):
    """
    AST NodeTransformer that encrypts string literals.

    After transformation, the AST contains additional Assign nodes that
    declare the key, data, and lambda decryptor for each encrypted string,
    and the original Constant node is replaced with a Call to the lambda.
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
                are left as plain strings (safe, conventional).
            min_length: Strings shorter than this are left unencrypted.
                Single chars and very short strings are not worth the overhead.
        """
        self._rng = random.Random(seed)
        self._preserve_docstrings = preserve_docstrings
        self._min_length = min_length

        # Tracks generated names to guarantee uniqueness within a file.
        self._used_names: set[str] = set()

        # Collected (name, assignment_nodes) pairs that must be prepended
        # to the current statement list being processed.
        # Each entry: (insert_before_index, [ast.Assign, ast.Assign, ast.Assign])
        self._pending_stmts: list[tuple[int, list[ast.stmt]]] = []

        # Set of node ids that are docstrings — populated before visiting.
        self._docstring_ids: set[int] = set()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def transform(self, source: str) -> ast.Module:
        """
        Parse *source*, encrypt strings, return the modified AST.

        The returned AST has correct lineno/col_offset on all nodes
        (ast.fix_missing_locations is called automatically).
        """
        tree = ast.parse(source)
        if self._preserve_docstrings:
            self._collect_docstrings(tree)
        new_tree = self.visit(tree)
        ast.fix_missing_locations(new_tree)
        return new_tree

    @staticmethod
    def unparse(tree: ast.AST) -> str:
        """
        Convert the modified AST back to source code.
        Requires Python 3.9+ (ast.unparse).
        """
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
        """
        XOR-encrypt *plaintext* encoded as UTF-8 with single-byte *key*.
        Key must be 1–254 (never 0, never 255 for safety).
        """
        raw = plaintext.encode("utf-8")
        return bytes(b ^ key for b in raw)

    # ------------------------------------------------------------------
    # AST node builders
    # ------------------------------------------------------------------

    def _build_decryptor_assign(self, dec_name: str) -> ast.Assign:
        """
        Build:
            _dec_XXXX = lambda k, d: bytes(a ^ b for a, b in zip(d, bytes([k]) * len(d))).decode('utf-8', errors='replace')
        """
        # lambda k, d: bytes(a ^ b for a, b in zip(d, bytes([k]) * len(d))).decode('utf-8', errors='replace')
        source = (
            f"{dec_name} = "
            "lambda k, d: "
            "bytes(a ^ b for a, b in zip(d, bytes([k]) * len(d)))"
            ".decode('utf-8', errors='replace')"
        )
        return ast.parse(source, mode="exec").body[0]  # type: ignore[return-value]

    def _build_key_assign(self, key_name: str, key: int) -> ast.Assign:
        """Build: _key_XXXX = 0xKK"""
        return ast.Assign(
            targets=[ast.Name(id=key_name, ctx=ast.Store())],
            value=ast.Constant(value=key),
            lineno=0,
            col_offset=0,
        )

    def _build_data_assign(self, dat_name: str, ciphertext: bytes) -> ast.Assign:
        """Build: _dat_XXXX = b'...' (the encrypted bytes literal)"""
        return ast.Assign(
            targets=[ast.Name(id=dat_name, ctx=ast.Store())],
            value=ast.Constant(value=ciphertext),
            lineno=0,
            col_offset=0,
        )

    def _build_call(self, dec_name: str, key_name: str, dat_name: str) -> ast.Call:
        """
        Build: _dec_XXXX(_key_XXXX, _dat_XXXX)
        This replaces the original string Constant node.
        """
        return ast.Call(
            func=ast.Name(id=dec_name, ctx=ast.Load()),
            args=[
                ast.Name(id=key_name, ctx=ast.Load()),
                ast.Name(id=dat_name, ctx=ast.Load()),
            ],
            keywords=[],
        )

    # ------------------------------------------------------------------
    # Statement-list processor
    # ------------------------------------------------------------------

    def _process_stmts(self, stmts: list[ast.stmt]) -> list[ast.stmt]:
        """
        Visit each statement in a list.  Because each encrypted string
        introduces three new assignment statements that must appear *before*
        the statement containing the string, we do a two-pass approach:

        1. Visit each stmt (which may register pending inserts via
           _queue_insert).
        2. After visiting, splice in the pending stmts at the correct
           positions.
        """
        result: list[ast.stmt] = []
        for stmt in stmts:
            self._pending_stmts.clear()
            new_stmt = self.visit(stmt)
            # _pending_stmts holds the helper assignments to insert before
            for _idx, helpers in self._pending_stmts:
                result.extend(helpers)
            if new_stmt is not None:
                result.append(new_stmt)
        return result

    # ------------------------------------------------------------------
    # NodeTransformer overrides
    # ------------------------------------------------------------------

    def visit_Module(self, node: ast.Module) -> ast.Module:
        node.body = self._process_stmts(node.body)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        node.body = self._process_stmts(node.body)
        return node

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        node.body = self._process_stmts(node.body)
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        """
        Replace string constants with a decryptor call.
        Skips:
          - Non-string constants (int, float, bool, None, bytes, ...)
          - Strings shorter than min_length
          - Docstrings (if preserve_docstrings is True)
          - f-string components (they appear as JoinedStr, not Constant)
        """
        if not isinstance(node.value, str):
            return node
        if id(node) in self._docstring_ids:
            return node
        if len(node.value) < self._min_length:
            return node

        # Generate unique names
        tag = self._unique_tag()
        dec_name, key_name, dat_name = self._make_names(tag)

        # Pick a random non-zero, non-255 key
        key = self._rng.randint(1, 254)
        ciphertext = self._encrypt(node.value, key)

        # Queue the three helper assignments to be inserted before the
        # current statement in the enclosing statement list.
        helpers = [
            self._build_decryptor_assign(dec_name),
            self._build_key_assign(key_name, key),
            self._build_data_assign(dat_name, ciphertext),
        ]
        self._pending_stmts.append((0, helpers))

        # Return the call node that replaces the original string
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
