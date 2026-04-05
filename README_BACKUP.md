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
│  [x] Stage 1d: Predicates   │  ← Step 4 ✓
│  [x] Stage 1e: Dead code    │  ← Step 5 ✓
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
│   STAGE 3: Runtime Shield   │  ← Step 6 ✓
│  Anti-debug + tamper check  │
└─────────────────────────────┘
```

## Quick Start

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Full Pipeline Usage (Stages 1a–1e + Shield)

```python
from securer.string_encryptor import StringEncryptor
from securer.name_mangler import NameMangler
from securer.flow_flattener import FlowFlattener
from securer.opaque_predicates import OpaquePredicates
from securer.dead_code_injector import DeadCodeInjector
from securer.runtime_shield import RuntimeShield

src = open('app.py').read()
enc = StringEncryptor(seed=42)    # Stage 1a: encrypt strings
mg  = NameMangler(seed=42)         # Stage 1b: mangle names
ff  = FlowFlattener(seed=42)       # Stage 1c: flatten control flow
op  = OpaquePredicates(seed=42)    # Stage 1d: opaque predicates
di  = DeadCodeInjector(seed=42)    # Stage 1e: dead code injection

tree = enc.transform(src)
tree = mg.transform_tree(tree)
tree = ff.transform_tree(tree)
tree = op.transform_tree(tree)
tree = di.transform_tree(tree)
open('app_obf.py', 'w').write(di.unparse(tree))

# Optional: inspect what changed
mg.print_table()
print(di.stats)

# Stage 3: embed in your entry point after Nuitka build
# RuntimeShield.EXPECTED_HASH = "<sha256 from compute_current_hash()>"
# RuntimeShield.guard()
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

### Stage 1d — Opaque Predicates ✓

Always-true/always-false branches inserted to confuse static analysis.
Every state-machine arm from Stage 1c is wrapped in a mathematically
tautological guard (e.g. `(_op_v * _op_v) >= 0`) that no static analyser
can simplify without knowing the runtime value of `_op_v`.

### Stage 1e — Dead Code Injection ✓

Realistic-looking but never-executed code paths injected at three sites:

1. **Empty else-branches** left by Stage 1d — filled with plausible snippets
   (hash computations, list comprehensions, arithmetic chains, dict builds)
2. **Function entry points** — a dead block inserted before `_st` init
3. **Module top-level** — wrapped in an always-false guard at file header

Eight distinct snippet types are used so repeated patterns are minimised.
All injected names follow the same `_X{hex}` style as Stage 1b mangling.

### Stage 3 — Runtime Shield ✓

Two independent runtime defences applied to the compiled `.exe`:

1. **Anti-debug guard**
   - Windows: `IsDebuggerPresent()` + `NtQueryInformationProcess` (catches
     remote debuggers and tools like x64dbg, WinDbg, OllyDbg)
   - Cross-platform fallback: timing-delta heuristic (≥50 ms gap between two
     `perf_counter` calls indicates single-stepping under a debugger)
   - Terminates via `os._exit(1)` — uncatchable from Python exception handlers

2. **Binary self-integrity check**
   - SHA-256 of the running `.exe` is compared against a hash embedded at
     build time via `RuntimeShield.EXPECTED_HASH`
   - Constant-time comparison (`hmac.compare_digest`) prevents timing
     side-channel attacks on the hash comparison itself
   - Any byte-patch, loader injection, or resource modification causes
     immediate `os._exit(1)`

**Build workflow:**
```python
# 1. Build your app.exe with Nuitka (no EXPECTED_HASH yet)
# 2. Run once to get the clean hash:
from securer.runtime_shield import RuntimeShield
print(RuntimeShield.compute_current_hash())   # → "a3f1...de09"

# 3. Set the hash, rebuild → now the exe verifies itself on every launch
RuntimeShield.EXPECTED_HASH = "a3f1...de09"
RuntimeShield.guard()   # call at top of main.py
```

## Step 7 — GUI (next)

Build a full CustomTkinter desktop GUI for Securer:

- **Sidebar navigation**: Pipeline, Settings, About
- **Pipeline view**: drag-and-drop .py file input, toggle for each stage
  (1a–1e + Shield), live log panel showing obfuscation progress, output
  file path selector, Run button
- **Settings view**: seed input, output directory, theme toggle (dark/light)
- **About view**: version, pipeline summary, links

Files to create:

```
gui/
├── app.py                   ← CustomTkinter root window + theme init
├── views/
│   ├── pipeline_view.py     ← main obfuscation UI
│   ├── settings_view.py     ← seed, output dir, theme
│   └── about_view.py        ← version + info
└── components/
    ├── sidebar.py           ← animated collapsible sidebar
    ├── log_panel.py         ← scrollable real-time log output
    └── toast.py             ← non-blocking toast notifications
main.py                      ← GUI entry point
```

## Project Structure

```
Securer/
├── securer/
│   ├── __init__.py
│   ├── string_encryptor.py     # Stage 1a ✓
│   ├── name_mangler.py         # Stage 1b ✓
│   ├── flow_flattener.py       # Stage 1c ✓
│   ├── opaque_predicates.py    # Stage 1d ✓
│   ├── dead_code_injector.py   # Stage 1e ✓
│   └── runtime_shield.py       # Stage 3 ✓
├── gui/                        # Step 7 — next
│   ├── app.py
│   ├── views/
│   │   ├── pipeline_view.py
│   │   ├── settings_view.py
│   │   └── about_view.py
│   └── components/
│       ├── sidebar.py
│       ├── log_panel.py
│       └── toast.py
├── main.py                     # Step 7 — GUI entry point
├── tests/
│   ├── test_string_encryptor.py
│   ├── test_name_mangler.py
│   ├── test_flow_flattener.py
│   ├── test_opaque_predicates.py
│   ├── test_dead_code_injector.py
│   ├── test_runtime_shield.py  # ✓
│   └── fixtures/
│       └── sample_app.py
├── build/
│   ├── build_securer.py        # Nuitka build of Securer.exe
│   └── cython_build.py         # compile securer/ to .pyd
├── README.md
├── requirements.txt
└── .gitignore
```

## Requirements

- Python 3.10+
- No external dependencies for core pipeline (stdlib `ast`, `hashlib`, `random` only)
- `pytest` for tests
- `customtkinter` for GUI (Step 7)
- `nuitka` + MSVC Build Tools for final compilation

## License

Private — do not distribute.
