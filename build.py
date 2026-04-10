import PyInstaller.__main__
import os
import shutil
import sys

# Clean up previous build/dist folders
for folder in ("build", "dist"):
    if os.path.exists(folder):
        shutil.rmtree(folder)

# Define paths
src_path = os.path.abspath("src")
icon_path = os.path.abspath("app.ico")
main_script = os.path.join(src_path, "main.py")

# Ensure src is in sys.path
sys.path.insert(0, src_path)

args = [
    main_script,
    "--name=RiskMap",

    # Using --onedir (more reliable than --onefile)
    "--onedir",
    "--windowed",
    f"--icon={icon_path}",
    "--clean",

    # Paths
    f"--paths={src_path}",

    # PyQt5 (CRITICAL: Include ALL web engine modules)
    "--hidden-import=PyQt5.QtCore",
    "--hidden-import=PyQt5.QtGui",
    "--hidden-import=PyQt5.QtWidgets",
    "--hidden-import=PyQt5.QtWebEngineWidgets",
    "--hidden-import=PyQt5.QtWebEngineCore",
    "--hidden-import=PyQt5.QtWebChannel",
    "--hidden-import=PyQt5.QtPrintSupport",
    
    # sklearn
    "--hidden-import=sklearn.utils._cython_blas",
    "--hidden-import=sklearn.neighbors.typedefs",
    "--hidden-import=sklearn.neighbors.quad_tree",
    "--hidden-import=sklearn.tree._utils",

    # Torch - MUST use --collect-all to get all DLLs
    "--collect-all=torch",
    "--collect-all=torchvision",
    
    # Exclude CUDA (CPU-only build)
    "--exclude-module=torch.cuda",
    "--exclude-module=torch.distributed",

    # Your internal modules
    "--hidden-import=utils",
    "--hidden-import=AppLogger",
    "--hidden-import=babel.numbers",

    # Data files
    f"--add-data={os.path.join(src_path, 'assets')};assets",
    f"--add-data={os.path.join(src_path, 'config_.ini')};.",
    f"--add-data={os.path.join(src_path, 'index_map.json')};.",
    f"--add-data={os.path.join(src_path, 'model_data.json')};.",
    f"--add-data={os.path.join(src_path, 'cities.txt')};.",

    # CRITICAL FIX for WinError 1114: Explicitly include libiomp5md.dll
    f"--add-binary={os.path.join(sys.prefix, 'Lib', 'site-packages', 'torch', 'lib', 'libiomp5md.dll')};.",
    
    # Exclude unnecessary packages to reduce size and fix extraction errors
    "--exclude-module=IPython",
    "--exclude-module=jupyter",
    "--exclude-module=notebook",
    "--exclude-module=zmq",
    "--exclude-module=pytest",
    "--exclude-module=test",
    "--exclude-module=tests",
    
    # Optional cleanups
    "--exclude-module=matplotlib.tests",
    "--exclude-module=numpy.random._examples",
]

print("Starting PyInstaller build...")
PyInstaller.__main__.run(args)

print("Build finished.")
print("Check dist/RiskMap.exe")

