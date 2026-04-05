#!/usr/bin/env python3
"""
Compiles a single Python source file to a native .pyd extension via Cython.
Usage: python cython_build.py path/to/module.py

The original .py file is kept (renamed to .py.bak during compilation).
The resulting .pyd is placed next to the original file.

Only use this on files marked with # COMPILE_TO_PYD at the top.
"""
import sys
import subprocess
import shutil
import tempfile
from pathlib import Path


def compile_to_pyd(source_path: str):
    src = Path(source_path).resolve()
    if not src.exists():
        print(f"[ERROR] File not found: {src}")
        sys.exit(1)

    module_name = src.stem
    parent = src.parent

    # Work in a temp directory to avoid polluting source tree
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        pyx_file = tmp / f"{module_name}.pyx"

        # Copy source as .pyx
        shutil.copy(src, pyx_file)

        setup_content = f"""from setuptools import setup
from Cython.Build import cythonize
setup(
    name='{module_name}',
    ext_modules=cythonize(
        '{module_name}.pyx',
        compiler_directives={{
            'language_level': '3',
            'boundscheck': False,
            'wraparound': False,
        }}
    )
)
"""
        setup_file = tmp / "setup.py"
        setup_file.write_text(setup_content)

        result = subprocess.run(
            [sys.executable, "setup.py", "build_ext", "--inplace"],
            cwd=tmp,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"[ERROR] Cython compilation failed:\n{result.stderr}")
            sys.exit(1)

        # Find the built .pyd / .so file
        built = list(tmp.glob(f"{module_name}*.pyd")) + list(tmp.glob(f"{module_name}*.so"))
        if not built:
            print("[ERROR] No .pyd/.so output found after compilation")
            sys.exit(1)

        dest = parent / built[0].name
        shutil.copy(built[0], dest)
        print(f"[OK] Compiled: {dest}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python cython_build.py path/to/module.py")
        sys.exit(1)
    compile_to_pyd(sys.argv[1])
