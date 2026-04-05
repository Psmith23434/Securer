"""
Stage 1b — Name Mangling
========================
Renames every user-defined identifier in a Python AST to a meaningless
``_X{hash}`` name, making decompiled output near-unreadable.

What gets renamed
-----------------
- Function and method names (``def foo`` → ``def _Xa3f1``)
- Class names (``class Foo`` → ``class _Xb2e0``)
- Local variables and augmented assignments
- Function arguments (positional, keyword, *args, **kwargs)
- For-loop targets, with-statement aliases, comprehension targets
- Import aliases (``import os as _X...``)

What is preserved
-----------------
- ``__dunder__`` names (``__init__``, ``__main__``, ``__all__``, …)
- Python builtins (``len``, ``range``, ``print``, ``True``, ``False``, …)
- Imported module names used without alias (``import os`` → ``os`` kept)
- Names listed in ``__all__`` (public API, preserved to avoid import breakage)
- The top-level entry-point name passed as ``entry_point`` (default: ``main``)
- Any name explicitly added to ``preserve`` set

Design
------
Two-pass approach:
  Pass 1 — ``_SymbolCollector``: walk the entire AST and build a mapping
           of original_name → mangled_name for every name that should be
           renamed.  This pass also collects preserved names.
  Pass 2 — ``_NameRewriter``: NodeTransformer that replaces Name/arg/alias
           nodes using the symbol table from Pass 1.

This two-pass design ensures forward references work correctly (a name used
before its definition still gets mangled consistently).

Usage
-----
::

    from securer.name_mangler import NameMangler

    mg = NameMangler(seed=42)
    transformed_ast = mg.transform(source_code)
    output_source = mg.unparse(transformed_ast)

Typically used *after* StringEncryptor so the decryptor lambda names
(``_dec_XXXX``) are also mangled in the second pass::

    from securer.string_encryptor import StringEncryptor
    from securer.name_mangler import NameMangler

    src = open('app.py').read()
    enc = StringEncryptor(seed=42)
    mg  = NameMangler(seed=42)

    tree = enc.transform(src)
    tree = mg.transform_tree(tree)          # accepts already-parsed AST
    print(mg.unparse(tree))
"""

import ast
import builtins
import hashlib
import keyword
import random
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BUILTINS: frozenset[str] = frozenset(dir(builtins))
_KEYWORDS: frozenset[str] = frozenset(keyword.kwlist + keyword.softkwlist)

# Names that must never be renamed regardless of context.
_ALWAYS_PRESERVE: frozenset[str] = frozenset({
    # Entry / protocol
    "main", "__main__", "__name__", "__file__", "__doc__",
    "__all__", "__version__", "__author__",
    # Common framework hooks
    "__init__", "__new__", "__del__",
    "__repr__", "__str__", "__bytes__",
    "__format__", "__hash__", "__bool__",
    "__getattr__", "__getattribute__", "__setattr__", "__delattr__",
    "__dir__", "__get__", "__set__", "__delete__",
    "__slots__", "__class__",
    "__len__", "__length_hint__",
    "__getitem__", "__setitem__", "__delitem__", "__missing__",
    "__iter__", "__reversed__", "__next__",
    "__contains__",
    "__add__", "__radd__", "__iadd__",
    "__sub__", "__rsub__", "__isub__",
    "__mul__", "__rmul__", "__imul__",
    "__truediv__", "__floordiv__", "__mod__", "__divmod__",
    "__pow__", "__lshift__", "__rshift__",
    "__and__", "__xor__", "__or__",
    "__neg__", "__pos__", "__abs__", "__invert__",
    "__complex__", "__int__", "__float__", "__index__",
    "__round__", "__trunc__", "__floor__", "__ceil__",
    "__enter__", "__exit__",
    "__await__", "__aiter__", "__anext__",
    "__aenter__", "__aexit__",
    "__call__", "__instancecheck__", "__subclasscheck__",
    "__class_getitem__", "__init_subclass__",
    "__set_name__", "__mro_entries__",
    "__sizeof__", "__reduce__", "__reduce_ex__",
    "__getnewargs__", "__getnewargs_ex__",
    "__getstate__", "__setstate__",
    "__copy__", "__deepcopy__",
    "__lt__", "__le__", "__eq__", "__ne__", "__gt__", "__ge__",
    # Pytest / unittest hooks (preserve so tests still work)
    "setUp", "tearDown", "setUpClass", "tearDownClass",
    # tkinter / CustomTkinter callbacks
    "configure", "pack", "grid", "place", "destroy", "update",
    "mainloop", "bind", "unbind", "after", "quit",
    # Common GUI method names
    "run", "start", "stop", "show", "hide", "close",
    # self / cls
    "self", "cls",
})


# ---------------------------------------------------------------------------
# Pass 1: Symbol collector
# ---------------------------------------------------------------------------

class _SymbolCollector(ast.NodeVisitor):
    """
    Walks the AST and builds a set of names that are *candidates* for
    renaming (i.e. user-defined and not preserved).

    Also collects:
    - ``_preserved``: names that must never be renamed
    - ``_imported_modules``: bare module names from ``import X`` (no alias)
    """

    def __init__(self, extra_preserve: frozenset[str]):
        self._candidates: set[str] = set()
        self._preserved: set[str] = set(_ALWAYS_PRESERVE | _BUILTINS | _KEYWORDS)
        self._preserved |= extra_preserve
        self._imported_modules: set[str] = set()

    # -- helpers ------------------------------------------------------------

    def _add(self, name: str) -> None:
        if name not in self._preserved and not name.startswith("__"):
            self._candidates.add(name)

    # -- visitors -----------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.asname:
                # ``import os as operating_system`` — asname is user-defined
                self._add(alias.asname)
            else:
                # ``import os`` — the bare module name must be preserved
                top = alias.name.split(".")[0]
                self._preserved.add(top)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.asname:
                self._add(alias.asname)
            else:
                # ``from os import path`` — 'path' is a module attribute,
                # preserve it to avoid breaking attribute access chains.
                self._preserved.add(alias.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._add(node.name)
        for arg in (
            node.args.args
            + node.args.posonlyargs
            + node.args.kwonlyargs
            + ([node.args.vararg] if node.args.vararg else [])
            + ([node.args.kwarg] if node.args.kwarg else [])
        ):
            self._add(arg.arg)
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._add(node.name)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self._add(node.id)
        self.generic_visit(node)

    def visit_Global(self, node: ast.Global) -> None:
        # global declarations don't add candidates but the names will be
        # picked up via visit_Name when assigned.
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self._add(node.name)
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        # Target of a comprehension (for x in ...)
        for n in ast.walk(ast.Expression(body=node.target)):
            if isinstance(n, ast.Name):
                self._add(n.id)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # Check if this is ``__all__ = [...]`` and preserve listed names
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__all__":
                if isinstance(node.value, (ast.List, ast.Tuple)):
                    for elt in node.value.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            self._preserved.add(elt.value)
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# Pass 2: Name rewriter
# ---------------------------------------------------------------------------

class _NameRewriter(ast.NodeTransformer):
    """Applies a pre-built symbol table to rename identifiers in the AST."""

    def __init__(self, table: dict[str, str]):
        self._table = table

    def _r(self, name: str) -> str:
        """Look up name in table; return mangled or original."""
        return self._table.get(name, name)

    def visit_Name(self, node: ast.Name) -> ast.Name:
        node.id = self._r(node.id)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        node.name = self._r(node.name)
        # Rename arguments
        for arg in (
            node.args.args
            + node.args.posonlyargs
            + node.args.kwonlyargs
        ):
            arg.arg = self._r(arg.arg)
        if node.args.vararg:
            node.args.vararg.arg = self._r(node.args.vararg.arg)
        if node.args.kwarg:
            node.args.kwarg.arg = self._r(node.args.kwarg.arg)
        self.generic_visit(node)
        return node

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        node.name = self._r(node.name)
        self.generic_visit(node)
        return node

    def visit_Import(self, node: ast.Import) -> ast.Import:
        for alias in node.names:
            if alias.asname:
                alias.asname = self._r(alias.asname)
        return node

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.ImportFrom:
        for alias in node.names:
            if alias.asname:
                alias.asname = self._r(alias.asname)
        return node

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> ast.ExceptHandler:
        if node.name:
            node.name = self._r(node.name)
        self.generic_visit(node)
        return node

    def visit_Global(self, node: ast.Global) -> ast.Global:
        node.names = [self._r(n) for n in node.names]
        return node

    def visit_Nonlocal(self, node: ast.Nonlocal) -> ast.Nonlocal:
        node.names = [self._r(n) for n in node.names]
        return node

    def visit_Attribute(self, node: ast.Attribute) -> ast.Attribute:
        # Only visit the *value* (the object), never the *attr* string.
        # Renaming attribute names would break library calls like
        # ``os.path.join`` or ``self.my_method()`` where my_method is
        # defined externally.
        node.value = self.visit(node.value)
        return node


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class NameMangler:
    """
    AST-based identifier renamer.

    Example usage::

        mg = NameMangler(seed=42)
        out = mg.transform(source_code)
        print(mg.unparse(out))

    After transformation, ``mg.symbol_table`` contains the full
    original → mangled mapping for debugging / audit purposes.
    """

    def __init__(
        self,
        seed: Optional[int] = None,
        preserve: Optional[set[str]] = None,
        entry_point: str = "main",
        prefix: str = "_X",
    ):
        """
        Args:
            seed: RNG seed for reproducible builds.
            preserve: Additional names to never rename.
            entry_point: Top-level function name to preserve (e.g. ``"main"``).
            prefix: Prefix for mangled names. Default ``"_X"``.
                    Use a different prefix per project for extra uniqueness.
        """
        self._rng = random.Random(seed)
        self._preserve = frozenset(preserve or set()) | frozenset({entry_point})
        self._prefix = prefix
        self.symbol_table: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def transform(self, source: str) -> ast.Module:
        """
        Parse *source*, mangle names, return modified AST.
        Also populates ``self.symbol_table``.
        """
        tree = ast.parse(source)
        return self.transform_tree(tree)

    def transform_tree(self, tree: ast.Module) -> ast.Module:
        """
        Mangle names in an already-parsed AST.
        Use this when chaining after StringEncryptor.
        """
        # Pass 1: collect
        collector = _SymbolCollector(extra_preserve=self._preserve)
        collector.visit(tree)

        # Build symbol table: candidate → mangled name
        self.symbol_table = {}
        for name in sorted(collector._candidates):  # sorted for determinism
            self.symbol_table[name] = self._mangle(name)

        # Pass 2: rewrite
        rewriter = _NameRewriter(self.symbol_table)
        new_tree = rewriter.visit(tree)
        ast.fix_missing_locations(new_tree)
        return new_tree

    @staticmethod
    def unparse(tree: ast.AST) -> str:
        """Convert AST back to source string. Requires Python 3.9+."""
        return ast.unparse(tree)

    def transform_file(self, input_path: str, output_path: str) -> None:
        """Convenience: read → mangle → write."""
        with open(input_path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = self.transform(source)
        result = self.unparse(tree)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result)

    def print_table(self) -> None:
        """Print the symbol table to stdout for audit/debugging."""
        print(f"{'Original':<30} {'Mangled':<20}")
        print("-" * 52)
        for orig, mangled in sorted(self.symbol_table.items()):
            print(f"{orig:<30} {mangled:<20}")

    # ------------------------------------------------------------------
    # Name generation
    # ------------------------------------------------------------------

    def _mangle(self, original: str) -> str:
        """
        Generate a deterministic mangled name.

        Strategy: SHA-256 of (seed_bytes + original_name), take first 4 hex
        chars, prepend prefix. Collisions are resolved by appending a counter.
        The result is a valid Python identifier that looks like ``_Xa3f10``.
        """
        seed_bytes = self._rng.randbytes(8)
        digest = hashlib.sha256(seed_bytes + original.encode()).hexdigest()[:4]
        candidate = f"{self._prefix}{digest}"
        # Resolve collision
        counter = 0
        base = candidate
        used = set(self.symbol_table.values())
        while candidate in used:
            counter += 1
            candidate = f"{base}{counter}"
        return candidate


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

def mangle_names(
    source: str,
    seed: Optional[int] = None,
    preserve: Optional[set[str]] = None,
    entry_point: str = "main",
) -> str:
    """
    One-liner: mangle all user-defined names in *source*.

    Example::

        obfuscated = mangle_names(open('app.py').read(), seed=42)
    """
    mg = NameMangler(seed=seed, preserve=preserve, entry_point=entry_point)
    tree = mg.transform(source)
    return mg.unparse(tree)
