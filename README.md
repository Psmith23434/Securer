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
│  [x] Stage 1c: Flow flatten │  ← Step 3 ✓
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
pytest tests/ -v
```

## Full Pipeline Usage

```python
from securer.string_encryptor import StringEncryptor
from securer.name_mangler import NameMangler
from securer.flow_flattener import FlowFlattener

src  = open('app.py').read()
enc  = StringEncryptor(seed=42)   # Stage 1a: encrypt strings
mg   = NameMangler(seed=42)       # Stage 1b: mangle names
ff   = FlowFlattener(seed=42)     # Stage 1c: flatten control flow

tree = enc.transform(src)
tree = mg.transform_tree(tree)
tree = ff.transform_tree(tree)
open('app_obf.py', 'w').write(ff.unparse(tree))

# Optional: print what got renamed
mg.print_table()
```

## Stages

### Stage 1a — String Encryption ✓

Every string literal replaced with XOR-encrypted bytes + unique lambda decryptor.

### Stage 1b — Name Mangling ✓

All user-defined identifiers renamed to `_X{sha256_hash}` names.

### Stage 1c — Control Flow Flattening ✓

Every function body rewritten as a `while True` state-machine dispatcher
with random 32-bit state integers per block per build.

**Before:**
```python
def verify_key(api_key):
    prefix = "SEC-"
    if api_key.startswith(prefix):
        return True
    else:
        return False
```

**After (simplified):**
```python
def _Xa3f1(_Xb2e0):
    _st = 0x3A1F9C4B
    _rv = None
    while True:
        if _st == 0x3A1F9C4B:
            _Xc1d3 = _dec_f3a1(_key_f3a1, _dat_f3a1)  # "SEC-"
            _st = 0x7D2E1A05 if _Xb2e0.startswith(_Xc1d3) else 0xC4B83F11
        elif _st == 0x7D2E1A05:
            _rv = True
            _st = 0xF0912E88
        elif _st == 0xC4B83F11:
            _rv = False
            _st = 0xF0912E88
        elif _st == 0xF0912E88:
            return _rv
```

None of the original names, strings, or logical structure survive in the output.

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
│   ├── flow_flattener.py       # Stage 1c ✓
│   ├── opaque_predicates.py    # Step 4
│   ├── dead_code_injector.py   # Step 5
│   └── runtime_shield.py       # Step 6
├── tests/
│   ├── test_string_encryptor.py
│   ├── test_name_mangler.py
│   ├── test_flow_flattener.py
│   └── fixtures/
│       └── sample_app.py
├── README.md
├── requirements.txt
└── .gitignore
```

## Requirements

- Python 3.10+
- No external dependencies (stdlib `ast`, `hashlib`, `random` only)
- `pytest` for tests
- `nuitka` + MSVC Build Tools for final compilation

## License

Private — do not distribute.
