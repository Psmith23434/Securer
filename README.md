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
│   STAGE 2: Nuitka           │  ← Step 8 ✓
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
python main.py
```

## Run Tests

```bash
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

---

## Completed Steps

### Stage 1a — String Encryption ✓

Every string literal replaced with XOR-encrypted bytes + unique lambda decryptor. Each string gets a unique random key (0x01–0xFE) so identical strings produce different ciphertext. All helper assignments are hoisted to module level so Nuitka's C backend compiles cleanly.

### Stage 1b — Name Mangling ✓

All user-defined identifiers renamed to `_X{sha256_hash}` names.

### Stage 1c — Control Flow Flattening ✓

Every function body rewritten as a `while True` state-machine dispatcher with random 32-bit state integers per block per build.

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

Always-true/always-false branches inserted to confuse static analysis. Every state-machine arm from Stage 1c is wrapped in a mathematically tautological guard (e.g. `(_op_v * _op_v) >= 0`) that no static analyser can simplify without knowing the runtime value.

### Stage 1e — Dead Code Injection ✓

Realistic-looking but never-executed code paths injected at three sites:

1. **Empty else-branches** left by Stage 1d — filled with plausible snippets (hash computations, list comprehensions, arithmetic chains, dict builds)
2. **Function entry points** — a dead block inserted before `_st` init
3. **Module top-level** — wrapped in an always-false guard at file header

Eight distinct snippet types are used to minimise repeating patterns. All injected names follow the same `_X{hex}` style as Stage 1b.

### Stage 3 — Runtime Shield ✓

Two independent runtime defences applied to the compiled `.exe`:

1. **Anti-debug guard (3a)**
   - Windows: `IsDebuggerPresent()` + `NtQueryInformationProcess` (catches remote debuggers and tools like x64dbg, WinDbg, OllyDbg)
   - Cross-platform fallback: timing-delta heuristic (≥50 ms gap between two `perf_counter` calls indicates single-stepping)
   - Terminates via `os._exit(1)` — uncatchable from Python exception handlers

2. **Binary self-integrity check (3b)**
   - SHA-256 of the running `.exe` compared against a hash embedded at build time
   - Constant-time comparison (`hmac.compare_digest`) prevents timing side-channel attacks
   - Any byte-patch, loader injection, or resource modification causes immediate `os._exit(1)`
   - **Disabled by default** — requires a two-pass build; incompatible with `--onefile`

**Build workflow:**
```python
# 1. Build app.exe with Nuitka (no EXPECTED_HASH yet)
# 2. Get the clean hash:
from securer.runtime_shield import RuntimeShield
print(RuntimeShield.compute_current_hash())   # → "a3f1...de09"

# 3. Set the hash, rebuild → exe verifies itself on every launch
RuntimeShield.EXPECTED_HASH = "a3f1...de09"
RuntimeShield.guard()
```

### Step 7 — GUI ✓

Full CustomTkinter desktop GUI — complete and functional.

- **Sidebar navigation**: Pipeline, Settings, About — collapsible with animation
- **Pipeline view**: drag-and-drop file input, 7 stage toggles (1a–1e + 3a Anti-Debug + 3b Integrity Hash), seed + output dir options, Run button, live color-coded log panel
- **Settings view**: default seed, output directory, dark/light/system theme
- **About view**: version, architecture diagram, stage reference table
- **Toast notifications**: non-blocking fade-out overlays for success/error/warning

### Step 8 — Nuitka GUI Integration ✓

After obfuscation completes, a `_CompileDialog` prompts the user to compile with Nuitka. `NuitkaRunner` streams stdout/stderr live into the log panel. Defaults to `--standalone` (not `--onefile`) to avoid antivirus false-positives from temp-folder self-extraction.

- Standalone vs onefile toggle with explanation tooltip
- Hide console window option
- Custom output directory picker
- "Open Folder" button on success

### Step 9 — Drag-and-Drop Input ✓

Drop zone in `pipeline_view.py` accepts `.py` files dragged from Explorer/Finder.

- Uses `tkinterdnd2` when available — dashed-border drop zone with hover highlight
- Falls back silently to Browse-button-only mode if `tkinterdnd2` is not installed
- Clicking the drop zone also opens the file browser

---

## Remaining Steps

### Step 10 — Build Securer.exe *(optional)*

> **This step is optional.** Securer is fully functional as a Python app (`python main.py`). Only follow this step if you want to distribute a standalone `.exe` that requires no Python installation.

1. Compile `securer/` core modules to `.pyd` via Cython (`cython_build.py`)
2. Package entire app with Nuitka (`build_securer.py`) — GUI + obfuscated core
3. Embed `RuntimeShield` hash into the compiled binary
4. Output: single `Securer.exe` — no Python installation required

---

## Future Improvements — Stronger Encryption

The four planned upgrades below all target the same weak point: the current XOR-based string encryptor stores the key as a plaintext integer (`_key_XXXX = 0x4F`) right next to the ciphertext. A one-liner can break every string in under a second.

### F1 — Replace XOR with AES-256-GCM

Switch `string_encryptor.py` from single-byte XOR to AES-256-GCM at build time, with a key derived from a compile-time master secret + per-string salt via HKDF. The master key is **never stored as a plaintext integer** — it is split into several byte-array fragments across the module and XOR-reconstructed in RAM only at the moment of decryption.

```python
# Current (breakable in one line):
_key_a3f1 = 0x4F
_dat_a3f1 = b'\x16\x1c...'

# Target:
_kp1 = b'\xde\xad...'   # piece 1
_kp2 = b'\xbe\xef...'   # piece 2
_mk  = bytes(a ^ b for a, b in zip(_kp1, _kp2))  # master key, only ever in RAM
# AES-GCM decrypt with _mk + per-string nonce
```

### F2 — Multi-layer Encryption

Run `StringEncryptor` twice with different seeds. The second pass encrypts the already-obfuscated decryptor lambda names from pass 1, creating a two-deep decryption chain that forces an attacker to unroll two layers before any plaintext is visible.

### F3 — Polymorphic Decryptors

Currently every lambda has the same structure — a static analyser can grep all of them in one pass. Instead, generate 4–5 structurally different decryption implementations (list comprehension variant, `map()` variant, `bytearray` loop, `struct.unpack`) and randomly assign one to each string so there is no single pattern to match.

### F4 — Key Splitting + Runtime Reconstruction

Split each encryption key into 3 integer fragments stored at different locations in the module. The real key is computed as `k1 ^ (k2 << 8) ^ k3` only at call time — it is never stored whole anywhere in the source or bytecode.

---

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
│   ├── runtime_shield.py       # Stage 3  ✓
│   └── nuitka_runner.py        # Stage 2  ✓
├── gui/                        # Steps 7–9 ✓
│   ├── app.py
│   ├── views/
│   │   ├── pipeline_view.py
│   │   ├── settings_view.py
│   │   └── about_view.py
│   └── components/
│       ├── sidebar.py
│       ├── log_panel.py
│       └── toast.py
├── main.py
├── tests/
│   ├── test_string_encryptor.py
│   ├── test_name_mangler.py
│   ├── test_flow_flattener.py
│   ├── test_opaque_predicates.py
│   ├── test_dead_code_injector.py
│   ├── test_runtime_shield.py
│   └── fixtures/
│       └── sample_app.py
├── build/
│   ├── build_securer.py        # Step 10 (optional)
│   └── cython_build.py         # Step 10 (optional)
├── README.md
├── README_BACKUP.md
├── requirements.txt
└── .gitignore
```

## Requirements

- Python 3.10+
- `customtkinter>=5.2` for GUI
- `tkinterdnd2` for drag-and-drop (Step 9 — optional, falls back gracefully)
- `pytest` for tests
- `nuitka` + MSVC Build Tools for compilation (Steps 8 & 10, optional)
  - https://visualstudio.microsoft.com/visual-cpp-build-tools/

## License

Private — do not distribute.
