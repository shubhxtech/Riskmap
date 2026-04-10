import PyInstaller.__main__
import os
import shutil
import sys

# PyInstaller --add-data uses ';' on Windows, ':' on macOS/Linux
DATA_SEP = ';' if sys.platform == 'win32' else ':'

# Clean up previous build/dist folders
import time
for folder in ("build", "dist"):
    if os.path.exists(folder):
        try:
            shutil.rmtree(folder)
        except PermissionError:
            print(f"Waiting for {folder} to be released...")
            time.sleep(2)
            try:
                shutil.rmtree(folder)
            except Exception as e:
                print(f"Could not remove {folder}: {e}")
                print("Please close any open folders or running instances.")

# Define paths
src_path = os.path.abspath("src")
icon_path = os.path.abspath("app.ico")
main_script = os.path.join(src_path, "main.py")

# Ensure src is in sys.path
sys.path.insert(0, src_path)

# Environment fix for Conda
if sys.prefix:
    library_bin = os.path.join(sys.prefix, "Library", "bin")
    if os.path.exists(library_bin):
        os.environ["PATH"] = library_bin + os.pathsep + os.environ.get("PATH", "")
        print(f"Added to PATH: {library_bin}")

args = [
    main_script,
    "--name=RiskMap",
    "--onedir",
    "--console", # Changed from --windowed to see errors
    f"--icon={icon_path}",
    "--clean",
    
    f"--paths={src_path}",
    
    # Torch (Let PyInstaller handle it)
    "--collect-all=torch",
    "--collect-all=torchvision",
    
    # TensorFlow (Code uses it, so we must collect it. Conflicts handled by removing manual injections)
    "--collect-all=tensorflow",
    "--hidden-import=tensorflow",
    "--hidden-import=tensorflow.python.autograph.impl.api",
    
    # Branca / Folium (Fix for 'templates' directory error)
    "--collect-all=branca",
    "--collect-all=folium",
    
    # Transformers & Tokenizers
    "--collect-all=transformers",
    "--collect-all=tokenizers",
    "--hidden-import=tokenizers",
    "--hidden-import=huggingface_hub",

    # PyQt WebEngine
    "--hidden-import=PyQt5.QtWebEngineWidgets",
    "--hidden-import=PyQt5.QtWebEngineCore",
    "--hidden-import=PyQt5.QtWebChannel",
    "--hidden-import=PyQt5.QtPrintSupport",
    
    # Scikit-learn
    "--hidden-import=sklearn.utils._cython_blas",
    "--hidden-import=sklearn.neighbors.typedefs",
    "--hidden-import=sklearn.neighbors.quad_tree",
    "--hidden-import=sklearn.tree._utils",
    
    # Internal
    "--hidden-import=utils",
    "--hidden-import=AppLogger",
    "--hidden-import=babel.numbers",
    
    # Data Files
    f"--add-data={os.path.join(src_path, 'assets')}{DATA_SEP}assets",
    f"--add-data={os.path.join(src_path, 'config_.ini')}{DATA_SEP}.",
    f"--add-data={os.path.join(src_path, 'index_map.json')}{DATA_SEP}.",
    f"--add-data={os.path.join(src_path, 'model_data.json')}{DATA_SEP}.",
    f"--add-data={os.path.join(src_path, 'cities.txt')}{DATA_SEP}.",
    
    # Excludes
    "--exclude-module=IPython",
    "--exclude-module=jupyter",
    "--exclude-module=notebook",
    "--exclude-module=zmq",
    "--exclude-module=pytest",
    # "--exclude-module=unittest", # Needed for TF
    "--exclude-module=test",
    "--exclude-module=tests",
    "--exclude-module=matplotlib.tests",
    "--exclude-module=numpy.random._examples",
]

print("\nStarting Clean PyInstaller build...")
PyInstaller.__main__.run(args)

print("\nBuild finished.")
print("Check dist/RiskMap/")
