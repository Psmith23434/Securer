#!/usr/bin/env python3
"""
Master build runner for all Securer apps.
Usage: python build_all.py [app_name]
       python build_all.py           # builds all apps
       python build_all.py snippet_tool
"""
import subprocess
import sys
import shutil
import os
from pathlib import Path

APPS = [
    "snippet_tool",
]


def load_config(cfg_path: Path) -> dict:
    config = {}
    if not cfg_path.exists():
        return config
    section = None
    for line in cfg_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if "=" in line and section == "nuitka":
            k, _, v = line.partition("=")
            config[k.strip()] = v.strip()
    return config


def compile_cython_modules(app_dir: Path):
    """Compile any .pyx or annotated .py files in core/ to .pyd native extensions."""
    cython_script = Path("cython_build.py")
    core_dir = app_dir / "core"
    if not core_dir.exists():
        return
    for py_file in core_dir.glob("*.py"):
        # Only compile files marked with # COMPILE_TO_PYD header
        content = py_file.read_text(errors="ignore")
        if "# COMPILE_TO_PYD" in content:
            print(f"  [cython] Compiling {py_file} -> .pyd")
            result = subprocess.run(
                [sys.executable, str(cython_script), str(py_file)],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                print(f"  [cython] WARNING: {result.stderr[:300]}")
            else:
                print(f"  [cython] OK")


def build_app(app_name: str):
    app_dir = Path(app_name)
    if not app_dir.exists():
        print(f"[ERROR] App directory '{app_name}' not found.")
        return False

    cfg = load_config(app_dir / "build.cfg")
    version_file = app_dir / "version.txt"
    version = version_file.read_text().strip() if version_file.exists() else "1.0.0"

    app_display_name = cfg.get("app_name", app_name)
    company = cfg.get("windows_company_name", "MyCompany")
    product_name = cfg.get("windows_product_name", app_display_name)
    description = cfg.get("windows_file_description", app_display_name)
    icon_path = app_dir / cfg.get("icon", "assets/icon.ico")

    out_filename = f"{app_display_name}_v{version}_win64.exe"
    dist_dir = Path("dist")
    dist_dir.mkdir(exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  Building: {app_display_name} v{version}")
    print(f"{'='*60}")

    # Step 1: Compile sensitive core modules to .pyd
    print("[1/3] Compiling Cython modules...")
    compile_cython_modules(app_dir)

    # Step 2: Build with Nuitka
    print("[2/3] Running Nuitka...")
    cmd = [
        sys.executable, "-m", "nuitka",
        "--onefile",
        "--windows-console-mode=disable",
        f"--output-filename={out_filename}",
        f"--output-dir={dist_dir}",
        f"--windows-company-name={company}",
        f"--windows-product-version={version}",
        f"--windows-product-name={product_name}",
        f"--windows-file-description={description}",
        "--assume-yes-for-downloads",
        "--enable-plugin=anti-bloat",
        "--follow-imports",
        f"--include-data-dir={app_dir}/assets=assets",
    ]
    if icon_path.exists():
        cmd.append(f"--windows-icon-from-ico={icon_path}")

    cmd.append(str(app_dir / "main.py"))

    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"[ERROR] Nuitka build failed for {app_name}")
        return False

    exe_path = dist_dir / out_filename

    # Step 3: Code signing (optional — requires signtool on PATH)
    print("[3/3] Signing executable...")
    if shutil.which("signtool"):
        sign_result = subprocess.run([
            "signtool", "sign",
            "/tr", "http://timestamp.digicert.com",
            "/td", "sha256",
            "/fd", "sha256",
            "/a",
            str(exe_path)
        ])
        if sign_result.returncode == 0:
            print("  Signed OK")
        else:
            print("  WARNING: Signing failed — distributing unsigned")
    else:
        print("  signtool not found — skipping signing (install Windows SDK for code signing)")

    print(f"\n  Output: {exe_path}")
    return True


if __name__ == "__main__":
    targets = sys.argv[1:] if len(sys.argv) > 1 else APPS
    failed = []
    for app in targets:
        ok = build_app(app)
        if not ok:
            failed.append(app)
    if failed:
        print(f"\n[SUMMARY] Failed: {failed}")
        sys.exit(1)
    else:
        print("\n[SUMMARY] All builds succeeded.")
