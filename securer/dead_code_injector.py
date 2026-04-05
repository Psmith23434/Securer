"""
Stage 1e — Dead Code Injection
================================
Injects realistic-looking but never-executed code paths into the AST
produced by the earlier pipeline stages.

Why dead code injection?
-------------------------
A reverse engineer working through a decompiled binary must decide which
branches are real and which are noise. If every function contains 30–50%
more code than actually runs, the effort per real instruction increases
dramatically. Combined with the opaque predicates from Stage 1d (which
control the always-false guards), the dead branches look structurally
identical to real branches.

Design principles
-----------------
1. **Semantic realism** — dead code is not ``pass`` or ``raise
   NotImplementedError``. It is plausible Python: hash computations,
   string manipulations, list comprehensions, arithmetic. It looks like
   code a developer would actually write.
2. **Name reuse** — injected names are drawn from the same mangled-name
   pool used by Stage 1b (``_X{hex}`` style). A reader cannot tell
   injected names from real names.
3. **No side effects** — all injected statements are pure: they read
   variables or perform computations but never write to globals, files,
   sockets, or any external state.  This keeps the injected code
   behaviourally inert.
4. **Integration with Stage 1d** — OpaquePredicates leaves empty
   ``else:`` branches on state-machine arms. DeadCodeInjector fills
   those branches. It can also inject standalone dead ``if False:``
   blocks at the module and function level.
5. **Density control** — the ``density`` parameter (0–1) controls
   how many eligible injection points receive dead code.

Usage
------
Standalone::

    from securer.dead_code_injector import DeadCodeInjector

    inj = DeadCodeInjector(seed=42)
    tree = inj.transform(source_code)
    print(inj.unparse(tree))

Full pipeline (run after OpaquePredicates)::

    from securer.string_encryptor import StringEncryptor
    from securer.name_mangler import NameMangler
    from securer.flow_flattener import FlowFlattener
    from securer.opaque_predicates import OpaquePredicates
    from securer.dead_code_injector import DeadCodeInjector

    src = open('app.py').read()
    enc = StringEncryptor(seed=42)
    mg  = NameMangler(seed=42)
    ff  = FlowFlattener(seed=42)
    op  = OpaquePredicates(seed=42)
    di  = DeadCodeInjector(seed=42)

    tree = enc.transform(src)
    tree = mg.transform_tree(tree)
    tree = ff.transform_tree(tree)
    tree = op.transform_tree(tree)
    tree = di.transform_tree(tree)   # ← Stage 1e
    open('app_obf.py', 'w').write(di.unparse(tree))
"""

import ast
import random
import hashlib
from typing import Optional


# ---------------------------------------------------------------------------
# Helpers shared with other stages
# ---------------------------------------------------------------------------

def _name_load(name: str) -> ast.Name:
    return ast.Name(id=name, ctx=ast.Load())

def _name_store(name: str) -> ast.Name:
    return ast.Name(id=name, ctx=ast.Store())

def _num(v: int) -> ast.Constant:
    return ast.Constant(value=v)

def _str(v: str) -> ast.Constant:
    return ast.Constant(value=v)

def _assign(target: str, value: ast.expr) -> ast.Assign:
    node = ast.Assign(
        targets=[_name_store(target)],
        value=value,
        lineno=0, col_offset=0,
    )
    return node


# ---------------------------------------------------------------------------
# Mangled-name generator (mirrors Stage 1b style)
# ---------------------------------------------------------------------------

def _mangle(seed_str: str, rng: random.Random) -> str:
    """Return a ``_X{hex8}`` style name deterministically derived from a seed string."""
    salt = rng.randint(0, 0xFFFF_FFFF)
    raw = hashlib.sha256(f"{seed_str}{salt}".encode()).hexdigest()[:8]
    return f"_X{raw}"


# ---------------------------------------------------------------------------
# Dead-code snippet factory
# ---------------------------------------------------------------------------

class _SnippetFactory:
    """
    Generates AST statement lists that look like real code but never affect
    program state. Each snippet reads from a set of ``source_names`` (names
    already in scope) or creates its own local temporaries.

    All snippets are:
    - Pure: no writes to globals / outer scope / I/O
    - Varied: 8 distinct patterns so not all dead branches look identical
    - Realistic: use common Python stdlib idioms
    """

    def __init__(self, rng: random.Random):
        self._rng = rng
        self._methods = [
            self._hash_computation,
            self._list_comprehension,
            self._string_join,
            self._arithmetic_chain,
            self._dict_build,
            self._nested_conditional,
            self._range_loop,
            self._bytes_xor,
        ]

    def generate(self, n_stmts: int = 3) -> list[ast.stmt]:
        """Return a list of *n_stmts* realistic dead statements."""
        stmts: list[ast.stmt] = []
        for _ in range(n_stmts):
            method = self._rng.choice(self._methods)
            stmts.extend(method())
        return stmts

    # ---------------------------------------------------------------- snippets

    def _hash_computation(self) -> list[ast.stmt]:
        """_Xaaaa = __import__('hashlib').sha256(str(id(object)).encode()).hexdigest()"""
        tgt = _mangle("hash", self._rng)
        # __import__('hashlib')
        import_call = ast.Call(
            func=_name_load("__import__"),
            args=[_str("hashlib")],
            keywords=[],
        )
        # .sha256(...)
        sha_call = ast.Call(
            func=ast.Attribute(value=import_call, attr="sha256", ctx=ast.Load()),
            args=[
                ast.Call(
                    func=ast.Attribute(
                        value=ast.Call(
                            func=_name_load("str"),
                            args=[ast.Call(func=_name_load("id"),
                                          args=[_name_load("object")],
                                          keywords=[])],
                            keywords=[],
                        ),
                        attr="encode",
                        ctx=ast.Load(),
                    ),
                    args=[],
                    keywords=[],
                )
            ],
            keywords=[],
        )
        hexdigest = ast.Call(
            func=ast.Attribute(value=sha_call, attr="hexdigest", ctx=ast.Load()),
            args=[],
            keywords=[],
        )
        return [_assign(tgt, hexdigest)]

    def _list_comprehension(self) -> list[ast.stmt]:
        """_Xbbbb = [_i ^ 0xAB for _i in range(16)]"""
        tgt  = _mangle("lc", self._rng)
        loop = _mangle("i", self._rng)
        mask = self._rng.randint(0x10, 0xFF)
        elt = ast.BinOp(
            left=_name_load(loop),
            op=ast.BitXor(),
            right=_num(mask),
        )
        comp = ast.ListComp(
            elt=elt,
            generators=[
                ast.comprehension(
                    target=_name_store(loop),
                    iter=ast.Call(
                        func=_name_load("range"),
                        args=[_num(self._rng.randint(8, 32))],
                        keywords=[],
                    ),
                    ifs=[],
                    is_async=0,
                )
            ],
        )
        return [_assign(tgt, comp)]

    def _string_join(self) -> list[ast.stmt]:
        """_Xcccc = '_'.join(hex(id(object))[k:k+2] for k in range(0,8,2))"""
        tgt  = _mangle("sj", self._rng)
        sep  = self._rng.choice(["-", "_", ":", "."])
        loop = _mangle("k", self._rng)
        step = 2
        stop = self._rng.randint(4, 10) * step
        # hex(id(object))
        hex_call = ast.Call(
            func=_name_load("hex"),
            args=[ast.Call(func=_name_load("id"), args=[_name_load("object")], keywords=[])],
            keywords=[],
        )
        # hex_call[k:k+2]
        sliced = ast.Subscript(
            value=hex_call,
            slice=ast.Slice(
                lower=_name_load(loop),
                upper=ast.BinOp(left=_name_load(loop), op=ast.Add(), right=_num(step)),
            ),
            ctx=ast.Load(),
        )
        gen = ast.GeneratorExp(
            elt=sliced,
            generators=[
                ast.comprehension(
                    target=_name_store(loop),
                    iter=ast.Call(
                        func=_name_load("range"),
                        args=[_num(0), _num(stop), _num(step)],
                        keywords=[],
                    ),
                    ifs=[],
                    is_async=0,
                )
            ],
        )
        join_call = ast.Call(
            func=ast.Attribute(value=_str(sep), attr="join", ctx=ast.Load()),
            args=[gen],
            keywords=[],
        )
        return [_assign(tgt, join_call)]

    def _arithmetic_chain(self) -> list[ast.stmt]:
        """Multi-step arithmetic on id(object) that produces an innocuous int."""
        a = _mangle("ac1", self._rng)
        b = _mangle("ac2", self._rng)
        c = _mangle("ac3", self._rng)
        k1 = self._rng.randint(3, 97)
        k2 = self._rng.randint(2, 31)
        # a = id(object)
        stmt1 = _assign(a, ast.Call(func=_name_load("id"), args=[_name_load("object")], keywords=[]))
        # b = (a * k1) & 0xFFFFFFFF
        stmt2 = _assign(b, ast.BinOp(
            left=ast.BinOp(left=_name_load(a), op=ast.Mult(), right=_num(k1)),
            op=ast.BitAnd(),
            right=_num(0xFFFF_FFFF),
        ))
        # c = b ^ (b >> k2)
        stmt3 = _assign(c, ast.BinOp(
            left=_name_load(b),
            op=ast.BitXor(),
            right=ast.BinOp(left=_name_load(b), op=ast.RShift(), right=_num(k2)),
        ))
        return [stmt1, stmt2, stmt3]

    def _dict_build(self) -> list[ast.stmt]:
        """_Xdddd = {'k1': id(object) & 0xFF, 'k2': id(type) >> 4}"""
        tgt  = _mangle("db", self._rng)
        k1   = hex(self._rng.randint(0x1000, 0xFFFF))
        k2   = hex(self._rng.randint(0x1000, 0xFFFF))
        mask = self._rng.randint(0x0F, 0xFF)
        shift = self._rng.randint(2, 8)
        val1 = ast.BinOp(
            left=ast.Call(func=_name_load("id"), args=[_name_load("object")], keywords=[]),
            op=ast.BitAnd(),
            right=_num(mask),
        )
        val2 = ast.BinOp(
            left=ast.Call(func=_name_load("id"), args=[_name_load("type")], keywords=[]),
            op=ast.RShift(),
            right=_num(shift),
        )
        d = ast.Dict(keys=[_str(k1), _str(k2)], values=[val1, val2])
        return [_assign(tgt, d)]

    def _nested_conditional(self) -> list[ast.stmt]:
        """A short if/else that computes something trivial but looks meaningful."""
        tgt   = _mangle("nc", self._rng)
        pivot = self._rng.randint(0x40, 0xC0)
        # _Xeeee = (id(object) & 0xFF)
        inner = ast.BinOp(
            left=ast.Call(func=_name_load("id"), args=[_name_load("object")], keywords=[]),
            op=ast.BitAnd(),
            right=_num(0xFF),
        )
        # if inner > pivot: tgt = inner - pivot else: tgt = pivot - inner
        test = ast.Compare(left=inner, ops=[ast.Gt()], comparators=[_num(pivot)])
        # We need to compute inner twice (no temp) to keep it expression-based
        lhs_true = ast.BinOp(
            left=ast.BinOp(
                left=ast.Call(func=_name_load("id"), args=[_name_load("object")], keywords=[]),
                op=ast.BitAnd(), right=_num(0xFF)),
            op=ast.Sub(), right=_num(pivot))
        lhs_false = ast.BinOp(
            left=_num(pivot),
            op=ast.Sub(),
            right=ast.BinOp(
                left=ast.Call(func=_name_load("id"), args=[_name_load("object")], keywords=[]),
                op=ast.BitAnd(), right=_num(0xFF)))
        if_node = ast.If(
            test=test,
            body=[_assign(tgt, lhs_true)],
            orelse=[_assign(tgt, lhs_false)],
        )
        return [if_node]

    def _range_loop(self) -> list[ast.stmt]:
        """A short for loop that accumulates into a local — classic red herring."""
        acc  = _mangle("rl_acc", self._rng)
        loop = _mangle("rl_i", self._rng)
        n    = self._rng.randint(4, 12)
        mask = self._rng.randint(0x07, 0x1F)
        # acc = 0
        init = _assign(acc, _num(0))
        # for loop in range(n): acc = (acc + loop) ^ mask
        body_stmt = _assign(
            acc,
            ast.BinOp(
                left=ast.BinOp(
                    left=_name_load(acc), op=ast.Add(), right=_name_load(loop)
                ),
                op=ast.BitXor(),
                right=_num(mask),
            ),
        )
        for_node = ast.For(
            target=_name_store(loop),
            iter=ast.Call(func=_name_load("range"), args=[_num(n)], keywords=[]),
            body=[body_stmt],
            orelse=[],
        )
        return [init, for_node]

    def _bytes_xor(self) -> list[ast.stmt]:
        """XOR two random byte-string literals together into a temp."""
        tgt  = _mangle("bx", self._rng)
        n    = self._rng.randint(4, 12)
        key  = self._rng.randint(1, 255)
        raw  = bytes(self._rng.randint(0, 255) for _ in range(n))
        enc  = bytes(b ^ key for b in raw)
        # _Xffff = bytes(a ^ key for a in enc_bytes)
        loop = _mangle("bx_b", self._rng)
        comp = ast.Call(
            func=_name_load("bytes"),
            args=[
                ast.GeneratorExp(
                    elt=ast.BinOp(
                        left=_name_load(loop),
                        op=ast.BitXor(),
                        right=_num(key),
                    ),
                    generators=[
                        ast.comprehension(
                            target=_name_store(loop),
                            iter=ast.Constant(value=enc),
                            ifs=[],
                            is_async=0,
                        )
                    ],
                )
            ],
            keywords=[],
        )
        return [_assign(tgt, comp)]


# ---------------------------------------------------------------------------
# Public transformer
# ---------------------------------------------------------------------------

class DeadCodeInjector(ast.NodeTransformer):
    """
    AST NodeTransformer that injects dead code into three locations:

    1. **Empty else-branches** left by :class:`~securer.opaque_predicates.
       OpaquePredicates` on state-machine arms — these are filled with
       realistic dead snippets.
    2. **Function entry points** — a randomly chosen dead snippet is
       inserted at the top of each function body (before the ``_st``
       initialisation), making the function opening look like a setup
       block.
    3. **Module top-level** — a small dead block is prepended to the
       module body so the file header looks like real initialisation code.

    Parameters
    ----------
    seed : int, optional
        RNG seed for reproducible builds.
    density : float
        Fraction of eligible injection sites that receive dead code.
        Default 0.75.
    stmts_per_site : int
        Number of dead statements inserted per injection site. Default 2.
    inject_module_level : bool
        Whether to inject a dead block at module top-level. Default True.
    inject_function_entry : bool
        Whether to inject dead code at function entry. Default True.
    """

    def __init__(
        self,
        seed: Optional[int] = None,
        density: float = 0.75,
        stmts_per_site: int = 2,
        inject_module_level: bool = True,
        inject_function_entry: bool = True,
    ):
        self._rng      = random.Random(seed)
        self._factory  = _SnippetFactory(random.Random(seed))
        self._density  = max(0.0, min(1.0, density))
        self._n        = max(1, stmts_per_site)
        self._mod_lvl  = inject_module_level
        self._fn_entry = inject_function_entry

        # stats
        self._sites_filled    = 0
        self._fn_entries_done = 0
        self._mod_done        = False

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def transform(self, source: str) -> ast.Module:
        """Parse *source*, inject dead code, return modified AST."""
        tree = ast.parse(source)
        return self.transform_tree(tree)

    def transform_tree(self, tree: ast.Module) -> ast.Module:
        """Inject dead code into an already-parsed AST."""
        new_tree = self.visit(tree)
        ast.fix_missing_locations(new_tree)
        return new_tree

    @staticmethod
    def unparse(tree: ast.AST) -> str:
        return ast.unparse(tree)

    @property
    def stats(self) -> dict:
        return {
            "else_branches_filled": self._sites_filled,
            "function_entries_injected": self._fn_entries_done,
            "module_level_injected": self._mod_done,
        }

    # ------------------------------------------------------------------
    # Module level — prepend a dead block
    # ------------------------------------------------------------------

    def visit_Module(self, node: ast.Module) -> ast.Module:
        self.generic_visit(node)
        if self._mod_lvl and self._rng.random() <= self._density:
            # Wrap dead stmts in an always-false if block so they are
            # syntactically inert even without OpaquePredicates
            dead = self._factory.generate(self._n)
            guard = ast.If(
                test=ast.Compare(
                    left=_num(0), ops=[ast.Gt()], comparators=[_num(1)]
                ),
                body=dead or [ast.Pass()],
                orelse=[],
            )
            ast.fix_missing_locations(guard)
            node.body.insert(0, guard)
            self._mod_done = True
        return node

    # ------------------------------------------------------------------
    # Function level — inject at entry + fill empty else branches
    # ------------------------------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        self.generic_visit(node)

        if self._fn_entry and self._rng.random() <= self._density:
            dead = self._factory.generate(self._n)
            for s in dead:
                ast.fix_missing_locations(s)
            # Insert after any docstring
            insert_at = 1 if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ) else 0
            for i, s in enumerate(dead):
                node.body.insert(insert_at + i, s)
            self._fn_entries_done += 1

        return node

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Fill empty else-branches left by OpaquePredicates
    # ------------------------------------------------------------------

    def visit_If(self, node: ast.If) -> ast.If:
        """Recursively fill empty ``orelse`` branches with dead code."""
        self.generic_visit(node)

        if (
            not node.orelse          # else branch is empty
            and self._rng.random() <= self._density
            and self._is_opaque_arm(node)
        ):
            dead = self._factory.generate(self._n)
            for s in dead:
                ast.fix_missing_locations(s)
            node.orelse = dead
            self._sites_filled += 1

        return node

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_opaque_arm(node: ast.If) -> bool:
        """
        Returns True if this ``if`` node looks like an opaque-predicate
        wrapper (i.e., its test contains ``_op_v``, the runtime variable
        injected by OpaquePredicates).
        """
        src = ast.unparse(node.test)
        return "_op_v" in src


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

def inject_dead_code(
    source: str,
    seed: Optional[int] = None,
    density: float = 0.75,
    stmts_per_site: int = 2,
) -> str:
    """
    One-liner: inject dead code into *source* and return new source.

    Designed to run after :func:`~securer.opaque_predicates.inject_opaque_predicates`::

        from securer.flow_flattener import flatten_flow
        from securer.opaque_predicates import inject_opaque_predicates
        from securer.dead_code_injector import inject_dead_code

        result = inject_dead_code(
            inject_opaque_predicates(
                flatten_flow(src, seed=42), seed=42
            ),
            seed=42,
        )
    """
    inj = DeadCodeInjector(seed=seed, density=density, stmts_per_site=stmts_per_site)
    tree = inj.transform(source)
    return inj.unparse(tree)
