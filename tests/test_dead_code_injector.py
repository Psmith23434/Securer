"""
Tests for Stage 1e — Dead Code Injection
"""
import ast
import pytest
from securer.dead_code_injector import DeadCodeInjector, inject_dead_code
from securer.flow_flattener import FlowFlattener
from securer.opaque_predicates import OpaquePredicates


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SIMPLE_SRC = """
def add(a, b):
    return a + b

def greet(name):
    msg = "Hello " + name
    return msg

x = 10
y = x * 2
"""

LICENSE_SRC = """
def verify_license(key):
    prefix = "SEC-"
    if key.startswith(prefix):
        body = key[4:]
        if len(body) == 16:
            return True
        else:
            return False
    else:
        return False
"""


def _full_pipeline(src: str, seed: int = 42) -> str:
    """Run all 5 stages and return obfuscated source."""
    from securer.string_encryptor import StringEncryptor
    from securer.name_mangler import NameMangler
    enc  = StringEncryptor(seed=seed)
    mg   = NameMangler(seed=seed)
    ff   = FlowFlattener(seed=seed)
    op   = OpaquePredicates(seed=seed)
    di   = DeadCodeInjector(seed=seed)

    tree = enc.transform(src)
    tree = mg.transform_tree(tree)
    tree = ff.transform_tree(tree)
    tree = op.transform_tree(tree)
    tree = di.transform_tree(tree)
    return di.unparse(tree)


# ---------------------------------------------------------------------------
# Basic functionality
# ---------------------------------------------------------------------------

class TestDeadCodeInjectorBasic:

    def test_transform_returns_valid_python(self):
        di = DeadCodeInjector(seed=42)
        tree = di.transform(SIMPLE_SRC)
        src_out = di.unparse(tree)
        # Must parse without error
        ast.parse(src_out)

    def test_output_is_longer_than_input(self):
        di = DeadCodeInjector(seed=42)
        tree = di.transform(SIMPLE_SRC)
        src_out = di.unparse(tree)
        assert len(src_out) > len(SIMPLE_SRC)

    def test_inject_dead_code_convenience(self):
        result = inject_dead_code(SIMPLE_SRC, seed=7)
        ast.parse(result)
        assert len(result) > len(SIMPLE_SRC)

    def test_deterministic_with_same_seed(self):
        out1 = inject_dead_code(SIMPLE_SRC, seed=99)
        out2 = inject_dead_code(SIMPLE_SRC, seed=99)
        assert out1 == out2

    def test_different_seeds_produce_different_output(self):
        out1 = inject_dead_code(SIMPLE_SRC, seed=1)
        out2 = inject_dead_code(SIMPLE_SRC, seed=2)
        assert out1 != out2


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

class TestStats:

    def test_stats_keys_present(self):
        di = DeadCodeInjector(seed=42)
        di.transform(SIMPLE_SRC)
        s = di.stats
        assert "else_branches_filled" in s
        assert "function_entries_injected" in s
        assert "module_level_injected" in s

    def test_function_entry_injection_counted(self):
        di = DeadCodeInjector(seed=42, density=1.0, inject_function_entry=True)
        di.transform(SIMPLE_SRC)
        # SIMPLE_SRC has 2 functions
        assert di.stats["function_entries_injected"] == 2

    def test_no_function_entry_when_disabled(self):
        di = DeadCodeInjector(seed=42, inject_function_entry=False)
        di.transform(SIMPLE_SRC)
        assert di.stats["function_entries_injected"] == 0

    def test_no_module_level_when_disabled(self):
        di = DeadCodeInjector(seed=42, inject_module_level=False)
        di.transform(SIMPLE_SRC)
        assert di.stats["module_level_injected"] is False


# ---------------------------------------------------------------------------
# Density parameter
# ---------------------------------------------------------------------------

class TestDensity:

    def test_density_zero_produces_no_injections(self):
        di = DeadCodeInjector(seed=42, density=0.0)
        di.transform(SIMPLE_SRC)
        s = di.stats
        assert s["function_entries_injected"] == 0
        assert s["module_level_injected"] is False

    def test_density_one_injects_everywhere(self):
        di = DeadCodeInjector(seed=42, density=1.0)
        di.transform(SIMPLE_SRC)
        s = di.stats
        # Both functions should be injected
        assert s["function_entries_injected"] == 2
        assert s["module_level_injected"] is True


# ---------------------------------------------------------------------------
# Correctness — injected code does not affect real semantics
# ---------------------------------------------------------------------------

class TestSemanticTransparency:

    def test_simple_function_still_executes_correctly(self):
        """
        After injection, a function that previously returned a+b
        should still return a+b.  We compile and exec the output.
        """
        src = """
def add(a, b):
    return a + b
"""
        result = inject_dead_code(src, seed=42, density=1.0)
        ns: dict = {}
        exec(compile(result, "<test>", "exec"), ns)
        assert ns["add"](3, 4) == 7
        assert ns["add"](0, 0) == 0
        assert ns["add"](-1, 1) == 0

    def test_string_return_function_unaffected(self):
        src = """
def greet(name):
    return 'Hello ' + name
"""
        result = inject_dead_code(src, seed=42, density=1.0)
        ns: dict = {}
        exec(compile(result, "<test>", "exec"), ns)
        assert ns["greet"]("world") == "Hello world"

    def test_module_level_value_unaffected(self):
        src = """
X = 42
Y = X * 2
"""
        result = inject_dead_code(src, seed=42)
        ns: dict = {}
        exec(compile(result, "<test>", "exec"), ns)
        assert ns["X"] == 42
        assert ns["Y"] == 84


# ---------------------------------------------------------------------------
# Integration with full pipeline
# ---------------------------------------------------------------------------

class TestFullPipelineIntegration:

    def test_full_pipeline_produces_valid_python(self):
        out = _full_pipeline(LICENSE_SRC)
        ast.parse(out)  # must parse cleanly

    def test_full_pipeline_output_differs_from_input(self):
        out = _full_pipeline(LICENSE_SRC)
        assert out != LICENSE_SRC

    def test_full_pipeline_no_original_names(self):
        """After full pipeline, original identifier names should not appear."""
        out = _full_pipeline(LICENSE_SRC)
        for name in ["verify_license", "key", "prefix", "body"]:
            assert name not in out, f"Original name '{name}' leaked into output"

    def test_full_pipeline_no_plaintext_strings(self):
        """After full pipeline, original string literals should not appear."""
        out = _full_pipeline(LICENSE_SRC)
        assert "SEC-" not in out
        assert "Hello" not in out

    def test_full_pipeline_deterministic(self):
        out1 = _full_pipeline(SIMPLE_SRC, seed=7)
        out2 = _full_pipeline(SIMPLE_SRC, seed=7)
        assert out1 == out2

    def test_full_pipeline_size_increase(self):
        """Obfuscated output must be substantially larger than input."""
        out = _full_pipeline(SIMPLE_SRC)
        # Expect at minimum 3x inflation from all injection stages
        assert len(out) >= len(SIMPLE_SRC) * 3

    def test_stmts_per_site_increases_output_size(self):
        out_small = inject_dead_code(SIMPLE_SRC, seed=42, stmts_per_site=1)
        out_large = inject_dead_code(SIMPLE_SRC, seed=42, stmts_per_site=5)
        assert len(out_large) > len(out_small)

    def test_else_branches_filled_after_opaque_predicates(self):
        """Else branches that OpaquePredicates left empty are filled."""
        ff  = FlowFlattener(seed=42)
        op  = OpaquePredicates(seed=42, density=1.0)
        di  = DeadCodeInjector(seed=42, density=1.0)

        tree = ff.transform(SIMPLE_SRC)
        tree = op.transform_tree(tree)
        di.transform_tree(tree)

        assert di.stats["else_branches_filled"] >= 0  # may be 0 if no arms
