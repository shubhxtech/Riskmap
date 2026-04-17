# Building RiskMap.exe for Windows

## Prerequisites

| Tool | Download |
|------|----------|
| Anaconda / Miniconda | https://www.anaconda.com/download |
| Visual C++ Redistributable | https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist |
| UPX (optional, smaller exe) | https://github.com/upx/upx/releases — add to PATH |

---

## Step 1 — Create & activate the conda environment

```bat
conda create -n riskmap python=3.10 -y
conda activate riskmap
```

## Step 2 — Install dependencies

```bat
pip install -r requirements_windows.txt
```

**GPU note:** The default `requirements_windows.txt` installs CPU-only PyTorch.  
For CUDA 11.8 GPU acceleration run instead:
```bat
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
pip install -r requirements_windows.txt
```

## Step 3 — Build the executable

Run from the **repo root** (the folder containing this file):

```bat
conda activate riskmap
python build_windows.py
```

This will:
1. Clean any previous `build/` and `dist/` folders
2. Run PyInstaller with `RiskMap.spec`
3. Print the path to the finished `.exe`

## Step 4 — Test

```bat
dist\RiskMap\RiskMap.exe
```

A console window will open alongside the app — this is intentional during testing.  
Once confirmed working, open `RiskMap.spec`, change `console=True` → `console=False`, and rebuild.

## Step 5 — Distribute

Zip the entire `dist\RiskMap\` folder:

```bat
powershell Compress-Archive dist\RiskMap dist\RiskMap_v1.0_Windows.zip
```

Send the zip to end users. They just unzip and run `RiskMap.exe`.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: rapidscan` | Make sure `src/rapidscan/` folder is present and has `__init__.py` |
| `QtWebEngineProcess not found` | Ensure `PyQtWebEngine` is installed in the conda env |
| `tensorflow DLL load failed` | Install the Visual C++ Redistributable (link above) |
| Black screen / app doesn't open | Run with `console=True` first and check the console output |
| `UPX` errors during build | Remove UPX from PATH or set `upx=False` in `RiskMap.spec` |
| Very large .exe (>1 GB) | Expected — TensorFlow + Torch are large frameworks |

---

## File structure after build

```
dist/
  RiskMap/
    RiskMap.exe          ← launch this
    assets/              ← icons, models, maps
    config_.ini
    *.dll                ← dependency libraries
    PyQt5/               ← Qt runtime
    tensorflow/          ← TF runtime
    torch/               ← PyTorch runtime
```
