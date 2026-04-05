# Securer — Python Source Obfuscation Pipeline

A custom pre-compilation obfuscation toolkit that transforms Python source
into heavily mangled code before handing it to Nuitka for native compilation.

## Architecture

```
Your source .py
      │
      ▼
┌─────────────────────────────┐
│   STAGE 1: Obfuscator       │
│  [x] Stage 1a: Strings      │  ← Step 1 ✓
│  [x] Stage 1b: Names        │  ← Step 2 ✓
│  [ ] Stage 1c: Flow flatten │  ← Step 3
│  [ ] Stage 1d: Predicates   │  ← Step 4
│  [ ] Stage 1e: Dead code    │  ← Step 5
└─────────────┬───────────────┘
              │  mangled_source.py
              ▼
┌─────────────────────────────┐
│   STAGE 2: Nuitka           │  external tool
│   Python → C → .exe         │
└─────────────┬───────────────┘
              │  app.exe
              ▼
┌─────────────────────────────┐
│   STAGE 3: Runtime Shield   │  ← Step 6
│  Anti-debug + tamper check  │
└─────────────────────────────┘
```

## Quick Start

```bash
pip install -r requirements.txt

# Run all tests
pytest tests/ -v
```

## Pipeline Usage

```python
from securer.string_encryptor import StringEncryptor
from securer.name_mangler import NameMangler

src = open('app.py').read()
enc = StringEncryptor(seed=42)   # Stage 1a: encrypt strings
mg  = NameMangler(seed=42)       # Stage 1b: mangle names

tree = enc.transform(src)
tree = mg.transform_tree(tree)   # accepts already-parsed AST
open('app_obf.py', 'w').write(mg.unparse(tree))

# Audit what got renamed
mg.print_table()
```

## Stages

### Stage 1a — String Encryption ✓

Every string literal replaced with an XOR-encrypted byte blob + unique
per-string lambda decryptor. Keys are random per build.

**Before:** `error_msg = "Invalid license key"`  
**After:** `_dec_a3f1(_key_a3f1, _dat_a3f1)`

### Stage 1b — Name Mangling ✓

All user-defined identifiers renamed to `_X{sha256_hash}` names.

**Renamed:** functions, classes, variables, arguments, import aliases,
for-loop targets, comprehension variables, exception aliases.

**Preserved:** `__dunder__` names, Python builtins, bare import module
names, names listed in `__all__`, `self`, `cls`, the entry point (`main`).

**Before:**
```python
def compute_license_hash(key, secret):
    return key + secret
```
**After:**
```python
def _Xa3f1(_Xb2e0, _Xc1d3):
    return _Xb2e0 + _Xc1d3
```

### Stage 1c — Control Flow Flattening (Step 3)

Function bodies rewritten as `while True` / state-machine dispatchers.

### Stage 1d — Opaque Predicates (Step 4)

Always-true/always-false branches inserted to confuse static analysis.

### Stage 1e — Dead Code Injection (Step 5)

Realistic-looking but never-executed paths injected throughout.

### Stage 3 — Runtime Shield (Step 6)

`IsDebuggerPresent()` check + SHA-256 binary integrity verification.

## Project Structure

```
Securer/
├── securer/
│   ├── __init__.py
│   ├── string_encryptor.py     # Stage 1a ✓
│   ├── name_mangler.py         # Stage 1b ✓
│   ├── flow_flattener.py       # Step 3
│   ├── opaque_predicates.py    # Step 4
│   ├── dead_code_injector.py   # Step 5
│   └── runtime_shield.py       # Step 6
├── tests/
│   ├── test_string_encryptor.py
│   ├── test_name_mangler.py
│   └── fixtures/
│       └── sample_app.py
├── README.md
├── requirements.txt
└── .gitignore
```

## Requirements

- Python 3.10+
- No external dependencies for the core pipeline (stdlib `ast` + `hashlib` only)
- `pytest` for tests
- `nuitka` + MSVC Build Tools for final compilation

## License

Private — do not distribute.
