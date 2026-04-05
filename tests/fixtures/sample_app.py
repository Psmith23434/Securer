"""
Fixture: sample_app.py
=======================
A non-trivial multi-function Python module used as the canonical test target
for the full Securer pipeline (Stages 1a through 1d, and eventually 1e + 3).

Design goals:
- Contains enough variety to stress every transformation stage.
- Uses strings, branching, loops, nested functions, early returns.
- Is self-contained — no external imports.
- Has a ``main()`` function that exercises all code paths and
  returns a dict of results so tests can assert on values.

Do NOT import this file at test time — it is fed to each stage as source text
via ``open('tests/fixtures/sample_app.py').read()``.
"""

# --- constants (strings: targeted by Stage 1a) ---

APP_NAME    = "SnippetTool"
APP_VERSION = "1.0.0"
LICENSE_PREFIX = "LIC-"


# --- simple arithmetic (flow: targeted by Stage 1c) ---

def add(a, b):
    return a + b


def multiply(a, b):
    return a * b


# --- branching (if/elif/else: all three branches targeted by 1c + 1d) ---

def classify(n):
    if n > 0:
        return "positive"
    elif n < 0:
        return "negative"
    else:
        return "zero"


# --- loop (for-loop body kept atomic per FlowFlattener design) ---

def sum_range(n):
    total = 0
    for i in range(n + 1):
        total += i
    return total


# --- early return inside loop ---

def first_match(items, predicate):
    for item in items:
        if predicate(item):
            return item
    return None


# --- nested function (inner should also be flattened) ---

def make_adder(x):
    def adder(y):
        return x + y
    return adder


# --- string operations (heavy string use: all literal strings encrypted by 1a) ---

def validate_license(key):
    """Return True if *key* starts with the correct prefix and has the right length."""
    if not isinstance(key, str):
        return False
    if not key.startswith(LICENSE_PREFIX):
        return False
    if len(key) != 19:
        return False
    parts = key.split("-")
    if len(parts) != 4:
        return False
    return True


# --- class (name mangler Stage 1b targets class + method names) ---

class SnippetStore:
    """Minimal in-memory snippet store."""

    def __init__(self):
        self._snippets = {}
        self._counter  = 0

    def add(self, title, body):
        self._counter += 1
        sid = f"snip_{self._counter:04d}"
        self._snippets[sid] = {"title": title, "body": body}
        return sid

    def get(self, sid):
        return self._snippets.get(sid)

    def count(self):
        return len(self._snippets)

    def search(self, query):
        results = []
        for sid, data in self._snippets.items():
            if query.lower() in data["title"].lower():
                results.append(sid)
        return results


# --- main: exercises all paths, returns results dict ---

def main():
    results = {}

    results["add"]       = add(3, 4)
    results["multiply"]  = multiply(6, 7)
    results["classify"]  = [classify(5), classify(-3), classify(0)]
    results["sum_range"] = sum_range(10)
    results["first_match"] = first_match([1, -2, 3, -4], lambda x: x > 2)
    results["make_adder"] = make_adder(10)(5)

    results["license_valid"]   = validate_license("LIC-AAAA-BBBB-1234")
    results["license_invalid"] = validate_license("BAD-KEY")

    store = SnippetStore()
    s1 = store.add("Hello World", "print('hello')")
    s2 = store.add("Python Tips", "Use list comprehensions")
    results["store_count"]  = store.count()
    results["store_get"]    = store.get(s1)["title"]
    results["store_search"] = store.search("python")

    return results


if __name__ == "__main__":
    import pprint
    pprint.pprint(main())
