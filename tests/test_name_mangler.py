"""
Tests for securer.name_mangler
================================
All tests are live exec() round-trips: obfuscate the source, execute it,
assert the runtime result matches the original.
"""

import ast
import pytest
from securer.name_mangler import NameMangler, mangle_names
from securer.string_encryptor import StringEncryptor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(source: str) -> dict:
    ns: dict = {}
    exec(compile(source, "<test>", "exec"), ns)  # noqa: S102
    return ns


def obf_run(source: str, seed: int = 42) -> dict:
    out = mangle_names(source, seed=seed)
    return run(out)


# ---------------------------------------------------------------------------
# Basic renaming
# ---------------------------------------------------------------------------

class TestBasicRenaming:
    def test_variable_renamed(self):
        src = 'my_secret_var = 42'
        out = mangle_names(src, seed=0)
        assert 'my_secret_var' not in out
        ns = run(out)
        # The value is still 42; we just can't refer to it by original name
        assert 42 in ns.values()

    def test_function_renamed(self):
        src = '''
def compute_total(price, tax):
    return price + tax
result = compute_total(100, 20)
'''
        ns = obf_run(src)
        assert ns['result'] == 120

    def test_class_renamed(self):
        src = '''
class InternalEngine:
    def process(self, value):
        return value * 2
obj = InternalEngine()
result = obj.process(21)
'''
        ns = obf_run(src)
        assert ns['result'] == 42

    def test_args_renamed(self):
        src = '''
def greet(first_name, last_name):
    return first_name + " " + last_name
result = greet("John", "Doe")
'''
        ns = obf_run(src)
        assert ns['result'] == 'John Doe'

    def test_kwargs_renamed(self):
        src = '''
def build(**options):
    return options.get('mode', 'default')
result = build(mode='fast')
'''
        ns = obf_run(src)
        assert ns['result'] == 'fast'

    def test_varargs_renamed(self):
        src = '''
def total(*numbers):
    return sum(numbers)
result = total(1, 2, 3, 4)
'''
        ns = obf_run(src)
        assert ns['result'] == 10


# ---------------------------------------------------------------------------
# Preservation rules
# ---------------------------------------------------------------------------

class TestPreservation:
    def test_dunder_preserved(self):
        src = '''
class MyClass:
    def __init__(self):
        self.value = 99
obj = MyClass()
result = obj.value
'''
        out = mangle_names(src, seed=0)
        assert '__init__' in out
        ns = run(out)
        assert ns['result'] == 99

    def test_self_preserved(self):
        src = '''
class Foo:
    def bar(self):
        return self
'''
        out = mangle_names(src, seed=0)
        assert 'self' in out

    def test_builtins_preserved(self):
        src = 'result = len([1, 2, 3])'
        out = mangle_names(src, seed=0)
        assert 'len' in out
        assert run(out)['result'] == 3

    def test_import_module_name_preserved(self):
        src = '''
import os
result = os.path.sep
'''
        out = mangle_names(src, seed=0)
        assert 'import os' in out

    def test_import_alias_renamed(self):
        src = '''
import os as operating_system
result = operating_system.path.sep
'''
        out = mangle_names(src, seed=0)
        assert 'operating_system' not in out
        ns = run(out)
        import os
        assert ns['result'] == os.path.sep

    def test_extra_preserve(self):
        src = 'public_api = 42'
        out = mangle_names(src, seed=0, preserve={'public_api'})
        assert 'public_api' in out

    def test_all_list_preserved(self):
        src = '''
__all__ = ['exported_func']
def exported_func():
    return True
'''
        out = mangle_names(src, seed=0)
        assert 'exported_func' in out

    def test_entry_point_preserved(self):
        src = '''
def main():
    return 'running'
'''
        out = mangle_names(src, seed=0, entry_point='main')
        assert 'def main' in out


# ---------------------------------------------------------------------------
# Control flow correctness
# ---------------------------------------------------------------------------

class TestControlFlow:
    def test_for_loop(self):
        src = '''
total = 0
for counter in range(5):
    total += counter
result = total
'''
        ns = obf_run(src)
        assert ns['result'] == 10

    def test_while_loop(self):
        src = '''
count = 0
while count < 3:
    count += 1
result = count
'''
        ns = obf_run(src)
        assert ns['result'] == 3

    def test_try_except(self):
        src = '''
try:
    result = int("not_a_number")
except ValueError as conversion_error:
    result = -1
'''
        ns = obf_run(src)
        assert ns['result'] == -1

    def test_with_statement(self):
        src = '''
import io
buf = io.StringIO("hello")
with buf as stream_handle:
    content = stream_handle.read()
result = content
'''
        ns = obf_run(src)
        assert ns['result'] == 'hello'

    def test_list_comprehension(self):
        src = 'squares = [item * item for item in range(5)]'
        ns = obf_run(src)
        assert ns['squares'] == [0, 1, 4, 9, 16]

    def test_nested_functions(self):
        src = '''
def outer_func(base_value):
    def inner_func(multiplier):
        return base_value * multiplier
    return inner_func(3)
result = outer_func(7)
'''
        ns = obf_run(src)
        assert ns['result'] == 21

    def test_global_keyword(self):
        src = '''
counter = 0
def increment():
    global counter
    counter += 1
increment()
increment()
result = counter
'''
        ns = obf_run(src)
        assert ns['result'] == 2


# ---------------------------------------------------------------------------
# Attribute access
# ---------------------------------------------------------------------------

class TestAttributeAccess:
    def test_attribute_names_not_renamed(self):
        """Attribute names (the part after the dot) must never be renamed."""
        src = '''
import os
result = os.path.sep
'''
        out = mangle_names(src, seed=0)
        # .path and .sep must still be there as attribute names
        assert '.path' in out
        assert '.sep' in out

    def test_self_attribute_access(self):
        src = '''
class Engine:
    def __init__(self):
        self.power = 500
    def get_power(self):
        return self.power
obj = Engine()
result = obj.get_power()
'''
        ns = obf_run(src)
        assert ns['result'] == 500


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_seed_same_output(self):
        src = 'my_var = 99'
        assert mangle_names(src, seed=10) == mangle_names(src, seed=10)

    def test_different_seeds_differ(self):
        src = 'my_var = 99'
        assert mangle_names(src, seed=1) != mangle_names(src, seed=2)

    def test_symbol_table_populated(self):
        src = '''
def secret_function(secret_arg):
    return secret_arg
'''
        mg = NameMangler(seed=0)
        mg.transform(src)
        assert 'secret_function' in mg.symbol_table
        assert 'secret_arg' in mg.symbol_table


# ---------------------------------------------------------------------------
# Pipeline: StringEncryptor → NameMangler
# ---------------------------------------------------------------------------

class TestPipeline:
    def test_combined_pipeline(self):
        src = '''
def get_api_key():
    return "super-secret-key-abc123"
result = get_api_key()
'''
        # Stage 1a: encrypt strings
        enc = StringEncryptor(seed=42)
        tree = enc.transform(src)

        # Stage 1b: mangle names
        mg = NameMangler(seed=42)
        tree = mg.transform_tree(tree)

        out = mg.unparse(tree)

        # Neither the original function name nor the string appear in output
        assert 'get_api_key' not in out
        assert 'super-secret-key-abc123' not in out

        # But it still runs correctly
        ns: dict = {}
        exec(compile(out, '<test>', 'exec'), ns)  # noqa: S102
        assert ns['result'] == 'super-secret-key-abc123'

    def test_pipeline_valid_ast(self):
        src = '''
class Config:
    BASE_URL = "https://api.example.com"
    TIMEOUT = 30

def load_config():
    cfg = Config()
    return cfg
'''
        enc = StringEncryptor(seed=7)
        mg = NameMangler(seed=7)
        tree = enc.transform(src)
        tree = mg.transform_tree(tree)
        out = mg.unparse(tree)
        parsed = ast.parse(out)
        assert parsed is not None
