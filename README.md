# Securer — Python Source Obfuscation Pipeline

A custom pre-compilation obfuscation toolkit that transforms Python source
into heavily mangled code before handing it to Nuitka for native compilation.

## Architecture

```
Your source .py
      │
      ▼
┌─────────────────────────────┐
│   STAGE 1: Obfuscator       │  ← this repo
│  [x] String encryption      │
│  [ ] Name mangling          │  ← Step 2
│  [ ] Control flow flatten   │  ← Step 3
│  [ ] Opaque predicates      │  ← Step 4
│  [ ] Dead code injection    │  ← Step 5
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

# Encrypt strings in a single file
python -m securer.cli --input my_app.py --output dist/ --encrypt-strings

# Full obfuscation pipeline (all stages, once built)
python -m securer.cli --input my_app.py --output dist/ --all
```

## Stages

### Stage 1a — String Encryption (this step)

Every string literal is replaced with an encrypted byte blob and a unique
per-string XOR lambda decryptor. Keys are randomised at each build, so
two builds of the same source produce different encrypted bytes.

**Before:**
```python
error_msg = "Invalid license key"
url = "https://api.example.com/validate"
```

**After:**
```python
_dec_a3f1 = lambda k, d: bytes(a ^ b for a, b in zip(d, (bytes([k]) * len(d)))).decode('utf-8', errors='replace')
_key_a3f1 = 0x4F
_dat_a3f1 = b'\x16\x1c\x09...'
error_msg = _dec_a3f1(_key_a3f1, _dat_a3f1)

_dec_b2e0 = lambda k, d: bytes(a ^ b for a, b in zip(d, (bytes([k]) * len(d)))).decode('utf-8', errors='replace')
_key_b2e0 = 0x71
_dat_b2e0 = b'\x39\x15\x06...'
url = _dec_b2e0(_key_b2e0, _dat_b2e0)
```

Each string gets its own decryptor name so static grep/search across the
binary finds nothing useful. The key is embedded as a hex literal, not a
named constant, making pattern matching harder.

### Stage 1b — Name Mangling (Step 2)

All variable, function, class, and argument names replaced with `_Ξ{hash}`
identifiers that are valid Python but meaningless to a human reader.

### Stage 1c — Control Flow Flattening (Step 3)

Function bodies rewritten as `while True` / state-machine dispatchers.
Most effective technique against Ghidra/IDA decompilation.

### Stage 1d — Opaque Predicates (Step 4)

Always-true/always-false branches inserted throughout to confuse static
analysis and waste reverse engineer time.

### Stage 1e — Dead Code Injection (Step 5)

Realistic-looking but never-executed code paths injected throughout.

### Stage 3 — Runtime Shield (Step 6)

- `IsDebuggerPresent()` check on Windows (silent exit)
- SHA-256 integrity check against baked-in binary hash
- Anti-VM heuristics (optional)

## Project Structure

```
Securer/
├── securer/
│   ├── __init__.py
│   ├── cli.py                  # entry point
│   ├── string_encryptor.py     # Stage 1a ✓
│   ├── name_mangler.py         # Stage 1b (Step 2)
│   ├── flow_flattener.py       # Stage 1c (Step 3)
│   ├── opaque_predicates.py    # Stage 1d (Step 4)
│   ├── dead_code_injector.py   # Stage 1e (Step 5)
│   └── runtime_shield.py       # Stage 3  (Step 6)
├── tests/
│   ├── test_string_encryptor.py
│   └── fixtures/
│       └── sample_app.py
├── README.md
├── requirements.txt
└── .gitignore
```

## Requirements

- Python 3.10+
- No external dependencies for the core pipeline (uses stdlib `ast` only)
- `pytest` for tests
- `nuitka` + MSVC Build Tools for final compilation step

## License

Private — do not distribute.
