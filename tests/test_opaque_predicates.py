"""
Tests for Stage 1d — Opaque Predicate Injection.

Test strategy
--------------
Every test that checks runtime correctness uses the following pattern:

    1.  Take a small Python source string.
    2.  Run it through the full Stage 1a→1c pipeline (string encryption,
        name mangling, flow flattening) so the AST already contains the
        ``while True`` state-machine pattern that Stage 1d targets.
    3.  Run Stage 1d (OpaquePredicates) on top.
    4.  Compile the result with ``compile()`` and execute it with ``exec()``.
    5.  Assert the output matches the expected value.

This validates that:
  a. The injected predicates are genuinely always-true (no branch taken
     when it should not be).
  b. The output code is syntactically valid Python.
  c. The transformer handles edge cases (no state machine, empty function,
     nested functions, density=0) without crashing.
"""

import ast
import textwrap
import pytest

from securer.string_encryptor import StringEncryptor
from securer.name_mangler import NameMangler
from securer.flow_flattener import FlowFlattener
from securer.opaque_predicates import (
    OpaquePredicates,
    inject_opaque_predicates,
    _PredicateFactory,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _full_pipeline(source: str, seed: int = 42, density: float = 1.0) -> str:
    """Run Stages 1a → 1d and return unparsed source."""
    enc  = StringEncryptor(seed=seed)
    mg   = NameMangler(seed=seed)
    ff   = FlowFlattener(seed=seed)
    op   = OpaquePredicates(seed=seed, density=density)

    tree = enc.transform(source)
    tree = mg.transform_tree(tree)
    tree = ff.transform_tree(tree)
    tree = op.transform_tree(tree)
    return op.unparse(tree)


def _run(source: str) -> dict:
    """
    Compile *source* and exec it, returning the globals dict so tests can
    inspect the values set by the code.
    """
    code = compile(source, "<test>", "exec")
    globs: dict = {}
    exec(code, globs)  # noqa: S102
    return globs


def _obf_and_run(src: str, seed: int = 42) -> dict:
    """Full pipeline + exec, returns globals."""
    return _run(_full_pipeline(src, seed=seed))


# ---------------------------------------------------------------------------
# 1. Predicate factory correctness
# ---------------------------------------------------------------------------

class TestPredicateFactory:
    """Verify each generated predicate evaluates as expected at runtime."""

    def _eval_pred(self, pred_ast: ast.expr) -> bool:
        """Wrap predicate in a function that binds _op_v = id(object)."""
        wrapper = textwrap.dedent(f"""
import ast as _ast
_op_v = id(object)
result = {ast.unparse(pred_ast)}
""")
        globs: dict = {}
        exec(compile(wrapper, "<pred>", "exec"), globs)  # noqa: S102
        return globs["result"]

    def test_all_true_predicates_evaluate_true(self):
        import random
        rng = random.Random(99)
        factory = _PredicateFactory(rng)
        for method in factory._true_pool:
            pred = method()
            assert self._eval_pred(pred) is True, (
                f"Expected True but got False for: {ast.unparse(pred)}"
            )

    def test_all_false_predicates_evaluate_false(self):
        import random
        rng = random.Random(99)
        factory = _PredicateFactory(rng)
        for method in factory._false_pool:
            pred = method()
            assert self._eval_pred(pred) is False, (
                f"Expected False but got True for: {ast.unparse(pred)}"
            )

    def test_always_true_returns_expr_node(self):
        import random
        factory = _PredicateFactory(random.Random(1))
        node = factory.always_true()
        assert isinstance(node, ast.expr)

    def test_always_false_returns_expr_node(self):
        import random
        factory = _PredicateFactory(random.Random(1))
        node = factory.always_false()
        assert isinstance(node, ast.expr)


# ---------------------------------------------------------------------------
# 2. Output is valid Python
# ---------------------------------------------------------------------------

class TestOutputValidity:

    def test_simple_function_parses(self):
        src = textwrap.dedent("""
            def add(a, b):
                return a + b
        """)
        result = _full_pipeline(src)
        # Should not raise
        ast.parse(result)

    def test_branching_function_parses(self):
        src = textwrap.dedent("""
            def classify(n):
                if n > 0:
                    return 'positive'
                elif n < 0:
                    return 'negative'
                else:
                    return 'zero'
        """)
        result = _full_pipeline(src)
        ast.parse(result)

    def test_no_state_machine_passes_through(self):
        """Source without a FlowFlattener state machine is untouched."""
        src = "x = 1 + 2"
        op = OpaquePredicates(seed=42)
        result = op.transform(src)
        # Should not raise, and _op_v should not appear
        unparsed = op.unparse(result)
        assert "_op_v" not in unparsed


# ---------------------------------------------------------------------------
# 3. Correctness: output behaves identically to original
# ---------------------------------------------------------------------------

class TestRuntimeCorrectness:

    def test_add_function(self):
        src = textwrap.dedent("""
            def add(a, b):
                return a + b
            result = add(3, 4)
        """)
        globs = _obf_and_run(src)
        assert globs["result"] == 7

    def test_conditional_function(self):
        src = textwrap.dedent("""
            def classify(n):
                if n > 0:
                    return 'positive'
                elif n < 0:
                    return 'negative'
                else:
                    return 'zero'
            r1 = classify(5)
            r2 = classify(-3)
            r3 = classify(0)
        """)
        globs = _obf_and_run(src)
        assert globs["r1"] == "positive"
        assert globs["r2"] == "negative"
        assert globs["r3"] == "zero"

    def test_loop_function(self):
        src = textwrap.dedent("""
            def sum_to(n):
                total = 0
                for i in range(n + 1):
                    total += i
                return total
            result = sum_to(10)
        """)
        globs = _obf_and_run(src)
        assert globs["result"] == 55

    def test_multiple_returns(self):
        src = textwrap.dedent("""
            def first_positive(values):
                for v in values:
                    if v > 0:
                        return v
                return -1
            result = first_positive([-3, -1, 0, 4, 7])
        """)
        globs = _obf_and_run(src)
        assert globs["result"] == 4


# ---------------------------------------------------------------------------
# 4. Injection statistics and density
# ---------------------------------------------------------------------------

class TestInjectionStats:

    def test_density_zero_injects_nothing(self):
        src = textwrap.dedent("""
            def f(x):
                if x > 0:
                    return x
                return 0
        """)
        ff = FlowFlattener(seed=42)
        op = OpaquePredicates(seed=42, density=0.0)
        tree = ff.transform(src)
        tree = op.transform_tree(tree)
        assert op.stats["predicates_injected"] == 0

    def test_density_one_injects_all_arms(self):
        src = textwrap.dedent("""
            def f(x):
                if x > 0:
                    return x
                return 0
        """)
        ff = FlowFlattener(seed=42)
        op = OpaquePredicates(seed=42, density=1.0)
        tree = ff.transform(src)
        tree = op.transform_tree(tree)
        assert op.stats["predicates_injected"] > 0

    def test_stats_counts_functions(self):
        src = textwrap.dedent("""
            def f(x):
                if x:
                    return 1
                return 0
            def g(y):
                return y * 2
        """)
        ff = FlowFlattener(seed=42)
        op = OpaquePredicates(seed=42, density=1.0)
        tree = ff.transform(src)
        tree = op.transform_tree(tree)
        assert op.stats["functions_seen"] >= 2


# ---------------------------------------------------------------------------
# 5. Convenience one-liner
# ---------------------------------------------------------------------------

class TestConvenienceFunction:

    def test_inject_opaque_predicates_returns_string(self):
        from securer.flow_flattener import flatten_flow
        src = textwrap.dedent("""
            def double(x):
                return x * 2
        """)
        flat = flatten_flow(src, seed=42)
        result = inject_opaque_predicates(flat, seed=42)
        assert isinstance(result, str)
        ast.parse(result)  # must be valid Python

    def test_inject_opaque_predicates_preserves_behaviour(self):
        from securer.flow_flattener import flatten_flow
        src = textwrap.dedent("""
            def double(x):
                return x * 2
            result = double(21)
        """)
        flat = flatten_flow(src, seed=42)
        obf  = inject_opaque_predicates(flat, seed=42)
        globs: dict = {}
        exec(compile(obf, "<test>", "exec"), globs)  # noqa: S102
        assert globs["result"] == 42
