# -*- mode: python ; coding: utf-8 -*-
# ============================================================
#  RiskMap — PyInstaller build spec  (Windows x64)
#  Run from repo root:  pyinstaller RiskMap.spec
# ============================================================
import os
from PyInstaller.utils.hooks import collect_all, collect_data_files

SRC = os.path.join(os.path.dirname(SPEC), "src")
ROOT = os.path.dirname(SPEC)

# ── Data files ──────────────────────────────────────────────
datas = [
    (os.path.join(SRC, "assets"),        "assets"),
    (os.path.join(SRC, "config_.ini"),   "."),
    (os.path.join(SRC, "index_map.json"),"." ),
    (os.path.join(SRC, "model_data.json"),"."),
    (os.path.join(SRC, "cities.txt"),    "."),
    (os.path.join(SRC, "secrets.env"),   "."),
    # rapidscan package (Python source + any data inside it)
    (os.path.join(SRC, "rapidscan"),     "rapidscan"),
]

binaries = []

# ── Hidden imports ──────────────────────────────────────────
hiddenimports = [
    # PyQt5 WebEngine (must be explicit — PyInstaller misses them)
    "PyQt5.QtWebEngineWidgets",
    "PyQt5.QtWebEngineCore",
    "PyQt5.QtWebChannel",
    "PyQt5.QtPrintSupport",
    # Internal modules
    "utils",
    "app_logger",
    "risk_engine",
    "streetview_scanner",
    "rapidscan",
    "rapidscan._constants",
    "rapidscan._video_processor",
    "rapidscan._risk_panel",
    "rapidscan._window",
    "building_detection",
    "building_detection_window",
    "unified_processing",
    "crop_window",
    "model_download",
    "split_processing_window",
    "RapidScanWindow",
    "model_training",
    "results_window",
    "search_results_window",
    "classification",
    "duplicates",
    "geoscatter",
    "map_index_maker",
    "api_window",
    "rapid_scan_window",
    # TensorFlow
    "tensorflow",
    "tensorflow.python.autograph.impl.api",
    "tensorflow.python.platform.gfile",
    # Scikit-learn (Cython extensions not auto-detected)
    "sklearn.utils._cython_blas",
    "sklearn.neighbors.typedefs",
    "sklearn.neighbors.quad_tree",
    "sklearn.tree._utils",
    "sklearn.utils._weight_vector",
    # HuggingFace
    "tokenizers",
    "huggingface_hub",
    # Misc
    "babel.numbers",
    "PIL._tkinter_finder",
    "cv2",
]

# ── collect_all for heavy packages ──────────────────────────
for pkg in ("torch", "torchvision", "tensorflow", "tensorflow_hub", "transformers",
            "tokenizers", "branca", "folium", "qtawesome", "cartopy", "scipy"):
    td, tb, ti = collect_all(pkg)
    datas     += td
    binaries  += tb
    hiddenimports += ti

# ── Analysis ────────────────────────────────────────────────
a = Analysis(
    [os.path.join(SRC, "main.py")],
    pathex=[SRC],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Dev / notebook tools never needed at runtime
        "IPython", "jupyter", "notebook", "nbformat", "nbconvert",
        "zmq", "pytest", "unittest",
        "matplotlib.tests", "numpy.random._examples",
        "mkdocs", "mkdocs_material",
        # These are imported only for linting/type-check, not runtime
        "mypy", "pyflakes", "pylint",
    ],
    noarchive=False,
    optimize=1,   # strip docstrings → smaller .pyc
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RiskMap",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    # windowed=True  → no black console window
    # Set console=False once you're happy it launches correctly.
    # Keep console=True during testing so you can see error messages.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, "app.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=["vcruntime140.dll", "python*.dll"],  # don't UPX these — breaks on Windows
    name="RiskMap",
)
