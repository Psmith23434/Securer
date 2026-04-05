"""
Tests for securer.flow_flattener
==================================
All tests are live exec() round-trips.
"""

import ast
import pytest
from securer.flow_flattener import FlowFlattener, flatten_flow
from securer.string_encryptor import StringEncryptor
from securer.name_mangler import NameMangler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(source: str) -> dict:
    ns: dict = {}
    exec(compile(source, "<test>", "exec"), ns)  # noqa: S102
    return ns


def obf_run(source: str, seed: int = 42) -> dict:
    out = flatten_flow(source, seed=seed)
    return run(out)


# ---------------------------------------------------------------------------
# Basic return values
# ---------------------------------------------------------------------------

class TestReturnValues:
    def test_simple_return(self):
        src = '''
def answer():
    x = 6
    y = 7
    return x * y
result = answer()
'''
        ns = obf_run(src)
        assert ns['result'] == 42

    def test_return_none_implicit(self):
        src = '''
def do_nothing():
    x = 1
    y = 2
result = do_nothing()
'''
        ns = obf_run(src)
        assert ns['result'] is None

    def test_return_none_explicit(self):
        src = '''
def early():
    x = 1
    return None
result = early()
'''
        ns = obf_run(src)
        assert ns['result'] is None

    def test_return_string(self):
        src = '''
def greeting():
    name = "world"
    return "hello " + name
result = greeting()
'''
        ns = obf_run(src)
        assert ns['result'] == 'hello world'

    def test_return_list(self):
        src = '''
def make_list():
    a = [1, 2, 3]
    b = [4, 5]
    return a + b
result = make_list()
'''
        ns = obf_run(src)
        assert ns['result'] == [1, 2, 3, 4, 5]


# ---------------------------------------------------------------------------
# Branching
# ---------------------------------------------------------------------------

class TestBranching:
    def test_if_else(self):
        src = '''
def classify(n):
    tag = "init"
    if n > 0:
        tag = "positive"
    else:
        tag = "non-positive"
    return tag
assert classify(5) == "positive"
assert classify(-1) == "non-positive"
assert classify(0) == "non-positive"
'''
        obf_run(src)  # assert inside src, no exception = pass

    def test_if_no_else(self):
        src = '''
def maybe_double(n):
    result = n
    if n > 10:
        result = n * 2
    return result
assert maybe_double(5) == 5
assert maybe_double(20) == 40
'''
        obf_run(src)

    def test_early_return_in_branch(self):
        src = '''
def check(val):
    placeholder = 0
    if val < 0:
        return -1
    placeholder = val * 2
    return placeholder
assert check(-5) == -1
assert check(3) == 6
'''
        obf_run(src)

    def test_both_branches_return(self):
        src = '''
def sign(n):
    dummy = 0
    if n >= 0:
        return 1
    else:
        return -1
assert sign(10) == 1
assert sign(-3) == -1
assert sign(0) == 1
'''
        obf_run(src)

    def test_chained_if_elif(self):
        src = '''
def grade(score):
    letter = "F"
    if score >= 90:
        letter = "A"
    else:
        if score >= 70:
            letter = "B"
        else:
            letter = "F"
    return letter
assert grade(95) == "A"
assert grade(75) == "B"
assert grade(50) == "F"
'''
        obf_run(src)


# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------

class TestArguments:
    def test_positional_args(self):
        src = '''
def add(a, b):
    total = a + b
    return total
result = add(10, 32)
'''
        ns = obf_run(src)
        assert ns['result'] == 42

    def test_default_args(self):
        src = '''
def power(base, exp=2):
    result = base ** exp
    return result
assert power(3) == 9
assert power(2, 10) == 1024
'''
        obf_run(src)

    def test_kwargs(self):
        src = '''
def describe(name, age=0):
    label = name + str(age)
    return label
result = describe(name="Alice", age=30)
'''
        ns = obf_run(src)
        assert ns['result'] == 'Alice30'


# ---------------------------------------------------------------------------
# Loops and try/except (treated as atomic)
# ---------------------------------------------------------------------------

class TestAtomicStatements:
    def test_for_loop_atomic(self):
        src = '''
def sum_range(n):
    total = 0
    for i in range(n):
        total += i
    return total
result = sum_range(5)
'''
        ns = obf_run(src)
        assert ns['result'] == 10

    def test_while_loop_atomic(self):
        src = '''
def countdown(n):
    count = n
    while count > 0:
        count -= 1
    return count
result = countdown(5)
'''
        ns = obf_run(src)
        assert ns['result'] == 0

    def test_try_except_atomic(self):
        src = '''
def safe_div(a, b):
    result = 0
    try:
        result = a // b
    except ZeroDivisionError:
        result = -1
    return result
assert safe_div(10, 2) == 5
assert safe_div(10, 0) == -1
'''
        obf_run(src)


# ---------------------------------------------------------------------------
# Structure checks (output must contain state machine markers)
# ---------------------------------------------------------------------------

class TestStructure:
    def test_while_true_present(self):
        src = '''
def work(x):
    a = x + 1
    b = a * 2
    return b
'''
        out = flatten_flow(src, seed=0)
        assert 'while True' in out

    def test_state_var_present(self):
        src = '''
def work(x):
    a = x + 1
    b = a * 2
    return b
'''
        out = flatten_flow(src, seed=0)
        assert '_st' in out

    def test_no_original_structure_visible(self):
        """The original if/else shape must not be recognisable in output."""
        src = '''
def check(x):
    status = "start"
    if x > 100:
        status = "big"
    else:
        status = "small"
    return status
'''
        out = flatten_flow(src, seed=0)
        # The top-level structure should now be while/dispatch, not if/else
        tree = ast.parse(out)
        func = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
        # The function body should contain a While node
        has_while = any(isinstance(n, ast.While) for n in func.body)
        assert has_while

    def test_small_function_skipped(self):
        """Single-statement functions below min_stmts threshold are not flattened."""
        src = 'def trivial(): return 42'
        out = flatten_flow(src, seed=0, min_stmts=2)
        assert 'while True' not in out

    def test_output_is_valid_python(self):
        src = '''
def process(items):
    results = []
    for item in items:
        if item > 0:
            results.append(item)
    total = sum(results)
    return total
'''
        out = flatten_flow(src, seed=0)
        tree = ast.parse(out)  # must not raise SyntaxError
        assert tree is not None


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_seed_same_output(self):
        src = '''
def fn(x):
    a = x + 1
    return a
'''
        assert flatten_flow(src, seed=7) == flatten_flow(src, seed=7)

    def test_different_seeds_differ(self):
        src = '''
def fn(x):
    a = x + 1
    return a
'''
        assert flatten_flow(src, seed=1) != flatten_flow(src, seed=2)


# ---------------------------------------------------------------------------
# Full three-stage pipeline
# ---------------------------------------------------------------------------

class TestFullPipeline:
    def test_all_three_stages(self):
        src = '''
def verify_key(api_key):
    prefix = "SEC-"
    if api_key.startswith(prefix):
        return True
    else:
        return False
result_ok = verify_key("SEC-abc123")
result_bad = verify_key("INVALID")
'''
        enc = StringEncryptor(seed=42)
        mg  = NameMangler(seed=42)
        ff  = FlowFlattener(seed=42)

        tree = enc.transform(src)
        tree = mg.transform_tree(tree)
        tree = ff.transform_tree(tree)
        out  = ff.unparse(tree)

        # None of the original names or strings appear
        assert 'verify_key' not in out
        assert 'api_key' not in out
        assert 'SEC-' not in out
        assert 'prefix' not in out

        # But the logic still works
        ns: dict = {}
        exec(compile(out, '<test>', 'exec'), ns)  # noqa: S102
        assert ns['result_ok'] is True
        assert ns['result_bad'] is False

    def test_class_with_methods(self):
        src = '''
class LicenseChecker:
    def check(self, key):
        valid_prefix = "PROD-"
        if not key.startswith(valid_prefix):
            return False
        return True

checker = LicenseChecker()
result = checker.check("PROD-xyz")
'''
        enc = StringEncryptor(seed=99)
        mg  = NameMangler(seed=99)
        ff  = FlowFlattener(seed=99)

        tree = enc.transform(src)
        tree = mg.transform_tree(tree)
        tree = ff.transform_tree(tree)
        out  = ff.unparse(tree)

        assert 'LicenseChecker' not in out
        assert 'PROD-' not in out

        ns: dict = {}
        exec(compile(out, '<test>', 'exec'), ns)  # noqa: S102
        assert ns['result'] is True
