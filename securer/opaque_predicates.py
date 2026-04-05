"""
Stage 1d — Opaque Predicate Injection
=======================================
Inserts always-true and always-false branches into the AST that are
mathematically provable tautologies / contradictions but are opaque to
static analysis tools (IDA Pro, Ghidra, Binary Ninja, Decompiler Explorer).

What makes a predicate "opaque"?
---------------------------------
A static analyser proves a branch dead (or live) by resolving the condition
to a constant. Simple predicates like ``if True:`` or ``if 1 == 1:`` are
immediately simplified. Opaque predicates frustrate this by:

1. **Reading runtime-bound variables** — the analyser cannot know their
   value at analysis time.
2. **Using non-linear arithmetic** — ``x*x >= 0`` is always True for real
   numbers, but a solver needs the algebraic identity to prove it.
3. **Hash / modular identities** — ``(n * (n+1)) % 2 == 0`` is always True
   (product of consecutive integers is always even), but many solvers give up
   on mod-arithmetic.
4. **Multiple chained comparisons** — the conjunction of two opaque tests is
   harder to simplify than either alone.

The injection sites
--------------------
Every ``if _st == STATE:`` arm produced by :class:`~securer.flow_flattener.
FlowFlattener` is a suitable injection point. We insert a guarding
``if <always_true_predicate>:`` around the arm body. This means:

- The real code is inside the true branch (always taken).
- An optional ``else:`` branch contains dead code (never taken) to further
  confuse the decompiler — this is wired up in Stage 1e.

Usage
------
Standalone::

    from securer.opaque_predicates import OpaquePredicates

    op = OpaquePredicates(seed=42)
    tree = op.transform(source_code)          # parse + inject
    print(op.unparse(tree))

Pipeline (after FlowFlattener)::

    from securer.string_encryptor import StringEncryptor
    from securer.name_mangler import NameMangler
    from securer.flow_flattener import FlowFlattener
    from securer.opaque_predicates import OpaquePredicates

    src  = open('app.py').read()
    enc  = StringEncryptor(seed=42)
    mg   = NameMangler(seed=42)
    ff   = FlowFlattener(seed=42)
    op   = OpaquePredicates(seed=42)

    tree = enc.transform(src)
    tree = mg.transform_tree(tree)
    tree = ff.transform_tree(tree)
    tree = op.transform_tree(tree)   # ← Stage 1d
    open('app_obf.py', 'w').write(op.unparse(tree))

Design notes
-------------
- All injected helper names (``_op_v``, ``_op_r``) are short, generic, and
  intentionally collision-prone — they collide with the mangled names from
  Stage 1b, adding to the visual noise.
- The ``_op_v`` variable is initialised to ``id(object)`` at function entry
  so it carries a runtime-bound integer value. Because ``id()`` returns the
  memory address of the ``object`` singleton, it is never zero and satisfies
  ``_op_v * _op_v >= 0`` and ``(_op_v | (~_op_v)) == -1`` identities.
- The injection density (``density`` parameter, default 0.8) controls what
  fraction of state-machine arms receive an opaque wrapper. Setting it to
  1.0 wraps every arm; 0.5 wraps roughly half at random.
- Injected predicates are selected from a pool that grows with the
  ``seed`` — different seeds produce different predicate styles.
"""

import ast
import random
from typing import Optional

# ---------------------------------------------------------------------------
# Names used for the injected runtime variable
# ---------------------------------------------------------------------------

_OP_VAR   = "_op_v"   # holds id(object) — runtime-bound, never 0
_OP_RVAR  = "_op_r"   # scratch variable for multi-step predicates

# Canonical AST helpers (mirrors the style in flow_flattener.py)

def _name_load(name: str) -> ast.Name:
    return ast.Name(id=name, ctx=ast.Load())

def _name_store(name: str) -> ast.Name:
    return ast.Name(id=name, ctx=ast.Store())

def _num(v: int) -> ast.Constant:
    return ast.Constant(value=v)

def _assign(target: str, value: ast.expr) -> ast.Assign:
    return ast.Assign(
        targets=[_name_store(target)],
        value=value,
        lineno=0, col_offset=0,
    )


# ---------------------------------------------------------------------------
# Predicate factory
# ---------------------------------------------------------------------------

class _PredicateFactory:
    """
    Generates AST expression nodes for always-true and always-false
    conditions that are opaque to static analysis.

    All predicates read ``_op_v`` (= ``id(object)``), which carries a
    runtime-bound non-zero integer value.  The mathematical identities
    used are listed next to each method.
    """

    def __init__(self, rng: random.Random):
        self._rng = rng
        self._true_pool  = [
            self._square_nonneg,      # x*x >= 0          (always true)
            self._bitwise_tautology,  # (x | ~x) == -1    (always true)
            self._consecutive_even,   # (x*(x+1)) % 2 == 0 (always true)
            self._double_neg,         # x - (-x) == 2*x   eliminated → x*2==x+x
            self._mod_self,           # x % (abs(x)+1) != x+1 (always true when x>=0)
            self._xor_self,           # (x ^ x) == 0      (always true)
        ]
        self._false_pool = [
            self._square_neg,         # x*x < 0           (always false)
            self._bitwise_contradiction, # (x & ~x) != 0  (always false)
            self._xor_nonzero,        # (x ^ x) > 0       (always false)
            self._consecutive_odd,    # (x*(x+1)) % 2 != 0 (always false)
        ]

    # ------------------------------------------------------------------ true

    def _square_nonneg(self) -> ast.expr:
        """_op_v * _op_v >= 0  — squares are non-negative."""
        return ast.Compare(
            left=ast.BinOp(
                left=_name_load(_OP_VAR),
                op=ast.Mult(),
                right=_name_load(_OP_VAR),
            ),
            ops=[ast.GtE()],
            comparators=[_num(0)],
        )

    def _bitwise_tautology(self) -> ast.expr:
        """(_op_v | ~_op_v) == -1  — OR of a value and its complement is all-ones."""
        return ast.Compare(
            left=ast.BinOp(
                left=_name_load(_OP_VAR),
                op=ast.BitOr(),
                right=ast.UnaryOp(op=ast.Invert(), operand=_name_load(_OP_VAR)),
            ),
            ops=[ast.Eq()],
            comparators=[_num(-1)],
        )

    def _consecutive_even(self) -> ast.expr:
        """(_op_v * (_op_v + 1)) % 2 == 0  — n*(n+1) is always even."""
        product = ast.BinOp(
            left=_name_load(_OP_VAR),
            op=ast.Mult(),
            right=ast.BinOp(
                left=_name_load(_OP_VAR), op=ast.Add(), right=_num(1)
            ),
        )
        return ast.Compare(
            left=ast.BinOp(left=product, op=ast.Mod(), right=_num(2)),
            ops=[ast.Eq()],
            comparators=[_num(0)],
        )

    def _double_neg(self) -> ast.expr:
        """_op_v + _op_v == _op_v * 2  — distributive identity."""
        lhs = ast.BinOp(
            left=_name_load(_OP_VAR), op=ast.Add(), right=_name_load(_OP_VAR)
        )
        rhs = ast.BinOp(
            left=_name_load(_OP_VAR), op=ast.Mult(), right=_num(2)
        )
        return ast.Compare(left=lhs, ops=[ast.Eq()], comparators=[rhs])

    def _mod_self(self) -> ast.expr:
        """(_op_v % (_op_v + 1)) < (_op_v + 1)  — always true (modulo < divisor)."""
        divisor = ast.BinOp(
            left=_name_load(_OP_VAR), op=ast.Add(), right=_num(1)
        )
        lhs = ast.BinOp(
            left=_name_load(_OP_VAR), op=ast.Mod(), right=divisor
        )
        rhs = ast.BinOp(
            left=_name_load(_OP_VAR), op=ast.Add(), right=_num(1)
        )
        return ast.Compare(left=lhs, ops=[ast.Lt()], comparators=[rhs])

    def _xor_self(self) -> ast.expr:
        """(_op_v ^ _op_v) == 0  — XOR of a value with itself is zero."""
        return ast.Compare(
            left=ast.BinOp(
                left=_name_load(_OP_VAR),
                op=ast.BitXor(),
                right=_name_load(_OP_VAR),
            ),
            ops=[ast.Eq()],
            comparators=[_num(0)],
        )

    # ----------------------------------------------------------------- false

    def _square_neg(self) -> ast.expr:
        """_op_v * _op_v < 0  — always false."""
        return ast.Compare(
            left=ast.BinOp(
                left=_name_load(_OP_VAR),
                op=ast.Mult(),
                right=_name_load(_OP_VAR),
            ),
            ops=[ast.Lt()],
            comparators=[_num(0)],
        )

    def _bitwise_contradiction(self) -> ast.expr:
        """(_op_v & ~_op_v) != 0  — AND of a value and its complement is 0."""
        return ast.Compare(
            left=ast.BinOp(
                left=_name_load(_OP_VAR),
                op=ast.BitAnd(),
                right=ast.UnaryOp(op=ast.Invert(), operand=_name_load(_OP_VAR)),
            ),
            ops=[ast.NotEq()],
            comparators=[_num(0)],
        )

    def _xor_nonzero(self) -> ast.expr:
        """(_op_v ^ _op_v) > 0  — XOR with self is 0, never > 0."""
        return ast.Compare(
            left=ast.BinOp(
                left=_name_load(_OP_VAR),
                op=ast.BitXor(),
                right=_name_load(_OP_VAR),
            ),
            ops=[ast.Gt()],
            comparators=[_num(0)],
        )

    def _consecutive_odd(self) -> ast.expr:
        """(_op_v * (_op_v + 1)) % 2 != 0  — n*(n+1) is never odd."""
        product = ast.BinOp(
            left=_name_load(_OP_VAR),
            op=ast.Mult(),
            right=ast.BinOp(
                left=_name_load(_OP_VAR), op=ast.Add(), right=_num(1)
            ),
        )
        return ast.Compare(
            left=ast.BinOp(left=product, op=ast.Mod(), right=_num(2)),
            ops=[ast.NotEq()],
            comparators=[_num(0)],
        )

    # ---------------------------------------------------------------- public

    def always_true(self) -> ast.expr:
        """Return a randomly chosen always-true opaque predicate expression."""
        return self._rng.choice(self._true_pool)()

    def always_false(self) -> ast.expr:
        """Return a randomly chosen always-false opaque predicate expression."""
        return self._rng.choice(self._false_pool)()


# ---------------------------------------------------------------------------
# Public transformer
# ---------------------------------------------------------------------------

class OpaquePredicates(ast.NodeTransformer):
    """
    AST NodeTransformer that injects opaque predicates into the
    state-machine dispatch arms emitted by :class:`~securer.flow_flattener.
    FlowFlattener`.

    Every ``if _st == STATE:`` arm is optionally wrapped in::

        if <always_true_predicate>:   # e.g. (_op_v * _op_v) >= 0
            <original arm body>
        # else branch left empty — Stage 1e will fill it with dead code

    This makes the state-machine dispatch look like deeply nested conditional
    logic to a decompiler, with no obvious relationship between the branches.

    Parameters
    ----------
    seed : int, optional
        RNG seed for reproducible builds.
    density : float
        Fraction of eligible arms that receive an opaque wrapper.  Default
        0.8 — slightly below 1.0 so not every arm looks identical.
    inject_false_guard : bool
        When True, also inserts an always-false ``if`` before some arms
        (guarding dead code).  Defaults to False — enable after Stage 1e
        dead-code injector is ready, so the else branches have content.
    """

    # Name used by FlowFlattener for the state variable
    _STATE_VAR = "_st"

    def __init__(
        self,
        seed: Optional[int] = None,
        density: float = 0.8,
        inject_false_guard: bool = False,
    ):
        self._rng     = random.Random(seed)
        self._factory = _PredicateFactory(self._rng)
        self._density = max(0.0, min(1.0, density))
        self._inject_false = inject_false_guard
        self._injected_count  = 0   # stats
        self._functions_seen  = 0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def transform(self, source: str) -> ast.Module:
        """Parse *source*, inject predicates, return modified AST."""
        tree = ast.parse(source)
        return self.transform_tree(tree)

    def transform_tree(self, tree: ast.Module) -> ast.Module:
        """Inject predicates into an already-parsed AST."""
        new_tree = self.visit(tree)
        ast.fix_missing_locations(new_tree)
        return new_tree

    @staticmethod
    def unparse(tree: ast.AST) -> str:
        return ast.unparse(tree)

    @property
    def stats(self) -> dict:
        """Return injection statistics."""
        return {
            "functions_seen": self._functions_seen,
            "predicates_injected": self._injected_count,
        }

    # ------------------------------------------------------------------
    # NodeTransformer — function level
    # ------------------------------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        """
        Walk function body.  If a ``while True`` state machine is present,
        inject the opaque-variable initialisation at the top and then
        rewrite each dispatch arm.
        """
        self.generic_visit(node)
        self._functions_seen += 1

        # Detect the state-machine pattern: _st = ...; _rv = None; while True:
        if not self._has_state_machine(node):
            return node

        # Prepend: _op_v = id(object)  — runtime-bound integer, never 0
        init_stmt = _assign(
            _OP_VAR,
            ast.Call(
                func=_name_load("id"),
                args=[_name_load("object")],
                keywords=[],
            ),
        )

        # Find the while True loop (always the last stmt in the state machine)
        while_idx = self._find_while_true(node.body)
        if while_idx is None:
            return node

        # Rewrite dispatch arms inside the while loop body
        while_node: ast.While = node.body[while_idx]  # type: ignore[assignment]
        while_node.body = [self._rewrite_dispatch(while_node.body[0])]

        # Inject _op_v init before the _st init
        node.body.insert(0, init_stmt)

        return node

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _has_state_machine(node: ast.FunctionDef) -> bool:
        """
        Returns True if the function contains the canonical FlowFlattener
        pattern:  ``_st = <int>`` followed by ``while True:``.
        """
        assigns_st = any(
            isinstance(s, ast.Assign)
            and len(s.targets) == 1
            and isinstance(s.targets[0], ast.Name)
            and s.targets[0].id == OpaquePredicates._STATE_VAR
            for s in node.body
        )
        has_while = any(
            isinstance(s, ast.While)
            and isinstance(s.test, ast.Constant)
            and s.test.value is True
            for s in node.body
        )
        return assigns_st and has_while

    @staticmethod
    def _find_while_true(stmts: list[ast.stmt]) -> Optional[int]:
        """Return index of the first ``while True:`` statement, or None."""
        for i, s in enumerate(stmts):
            if (
                isinstance(s, ast.While)
                and isinstance(s.test, ast.Constant)
                and s.test.value is True
            ):
                return i
        return None

    def _rewrite_dispatch(self, node: ast.stmt) -> ast.stmt:
        """
        Recursively rewrite the if/elif chain that forms the state dispatch.
        Each ``if _st == X:`` arm is optionally wrapped in an opaque guard.
        """
        if not isinstance(node, ast.If):
            return node

        # Recurse into the orelse chain first (tail of elif)
        if node.orelse:
            node.orelse = [self._rewrite_dispatch(node.orelse[0])]

        # Determine if this arm is a state-machine dispatch arm
        if not self._is_state_arm(node):
            return node

        # Randomly skip based on density
        if self._rng.random() > self._density:
            return node

        # Wrap the arm body in an always-true opaque predicate
        guard = ast.If(
            test=self._factory.always_true(),
            body=node.body if node.body else [ast.Pass()],
            orelse=[],   # Stage 1e will populate this
        )
        ast.copy_location(guard, node)
        node.body = [guard]
        self._injected_count += 1

        # Optionally also insert an always-false dead stub before the arm
        if self._inject_false and self._rng.random() < 0.4:
            dead_guard = ast.If(
                test=self._factory.always_false(),
                body=[ast.Pass()],   # Stage 1e replaces this
                orelse=[],
            )
            ast.copy_location(dead_guard, node)
            node.body = [dead_guard] + node.body

        return node

    @staticmethod
    def _is_state_arm(node: ast.If) -> bool:
        """
        Returns True if *node* is a ``if _st == <constant>:`` arm.
        """
        return (
            isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == OpaquePredicates._STATE_VAR
            and len(node.test.ops) == 1
            and isinstance(node.test.ops[0], ast.Eq)
            and len(node.test.comparators) == 1
            and isinstance(node.test.comparators[0], ast.Constant)
        )


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

def inject_opaque_predicates(
    source: str,
    seed: Optional[int] = None,
    density: float = 0.8,
) -> str:
    """
    One-liner: inject opaque predicates into *source* and return new source.

    Designed to run after :func:`~securer.flow_flattener.flatten_flow`::

        from securer.flow_flattener import flatten_flow
        from securer.opaque_predicates import inject_opaque_predicates

        result = inject_opaque_predicates(flatten_flow(src, seed=42), seed=42)
    """
    op = OpaquePredicates(seed=seed, density=density)
    tree = op.transform(source)
    return op.unparse(tree)
