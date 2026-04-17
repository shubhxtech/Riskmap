"""
build_windows.py
================
Run this script from the REPO ROOT on a Windows machine to produce
the RiskMap executable.

    cd C:\\path\\to\\RiskMap
    conda activate riskmap
    python build_windows.py

Output: dist\\RiskMap\\RiskMap.exe  (and companion DLLs/data)

Requirements:
    pip install pyinstaller
    (all other deps already in the riskmap conda environment)
"""

import os
import sys
import shutil
import time
import subprocess

# ── Sanity checks ────────────────────────────────────────────────────────────
if sys.platform != "win32":
    print("WARNING: This script is designed for Windows. "
          "Cross-compiling from macOS is not supported by PyInstaller.")
    # Allow continue for testing the script logic itself
    input("Press Enter to continue anyway, or Ctrl+C to abort: ")

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR   = os.path.join(REPO_ROOT, "src")
SPEC_FILE = os.path.join(REPO_ROOT, "RiskMap.spec")

for required in (SRC_DIR, SPEC_FILE, os.path.join(SRC_DIR, "main.py")):
    if not os.path.exists(required):
        print(f"ERROR: Could not find required path: {required}")
        sys.exit(1)

# ── Conda environment PATH fix (Windows) ─────────────────────────────────────
if sys.prefix:
    lib_bin = os.path.join(sys.prefix, "Library", "bin")
    if os.path.exists(lib_bin) and lib_bin not in os.environ.get("PATH", ""):
        os.environ["PATH"] = lib_bin + os.pathsep + os.environ.get("PATH", "")
        print(f"[build] Added to PATH: {lib_bin}")

# ── Clean previous build artifacts ───────────────────────────────────────────
for artifact in ("build", "dist"):
    full = os.path.join(REPO_ROOT, artifact)
    if os.path.exists(full):
        print(f"[build] Removing old {artifact}/ ...")
        for attempt in range(3):
            try:
                shutil.rmtree(full)
                break
            except PermissionError:
                print(f"  Waiting for file lock to release... ({attempt + 1}/3)")
                time.sleep(3)
        else:
            print(f"  ERROR: Could not remove {artifact}/. Close any open windows and retry.")
            sys.exit(1)

# ── PyInstaller ──────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  Starting PyInstaller build…")
print("=" * 60)

try:
    import PyInstaller.__main__ as pyi
except ImportError:
    print("ERROR: PyInstaller not found. Run:  pip install pyinstaller")
    sys.exit(1)

# Build from the repo root so the spec file's relative paths resolve correctly
os.chdir(REPO_ROOT)

pyi.run([
    SPEC_FILE,
    "--clean",           # always fresh compile
    "--noconfirm",       # don't ask before overwriting dist/
])

# ── Post-build checks ────────────────────────────────────────────────────────
exe_path = os.path.join(REPO_ROOT, "dist", "RiskMap", "RiskMap.exe")
dist_dir = os.path.join(REPO_ROOT, "dist", "RiskMap")

print("\n" + "=" * 60)
if os.path.exists(exe_path):
    size_mb = os.path.getsize(exe_path) / (1024 * 1024)
    print(f"  ✓ Build successful!")
    print(f"  EXE : {exe_path}")
    print(f"  Size: {size_mb:.1f} MB")
    print(f"  Dir : {dist_dir}")
    print("\n  To run:  dist\\RiskMap\\RiskMap.exe")
    print("\n  To package for distribution, zip the entire dist\\RiskMap\\ folder.")
else:
    print("  ✗ Build may have failed — RiskMap.exe not found.")
    print(f"    Check build/RiskMap/warn-RiskMap.txt for details.")
print("=" * 60)
