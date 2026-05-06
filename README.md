# RAPID-Lens (RiskMap)

**AI-powered seismic risk assessment platform** — street-level building detection, structural typology classification, and fragility-based loss estimation using deep learning and geospatial analysis.

---

## Table of Contents

1. [Overview](#overview)
2. [Features](#features)
3. [System Requirements](#system-requirements)
4. [Setup — Windows](#setup--windows)
5. [Setup — macOS (Apple Silicon)](#setup--macos-apple-silicon)
6. [Running the Application](#running-the-application)
7. [GPU Acceleration (Optional)](#gpu-acceleration-optional)
8. [Project Structure](#project-structure)
9. [Configuration](#configuration)
10. [Building a Windows Installer](#building-a-windows-installer)
11. [3D Reconstruction (NodeODM)](#3d-reconstruction-nodeodm)
12. [Troubleshooting](#troubleshooting)
13. [License](#license)

---

## Overview

RAPID-Lens is a desktop application built with **PyQt5** that automates the end-to-end pipeline for urban seismic risk assessment:

1. **Download** — Acquire street-level imagery via Google Street View API
2. **Process** — Crop, clean, and prepare images for analysis
3. **Detect** — Identify buildings in panoramic images using TensorFlow Hub (Faster R-CNN)
4. **Classify** — Assign structural typologies (24 classes) using a BEiT vision transformer (PyTorch)
5. **Assess Risk** — Compute seismic damage probabilities and loss ratios using the Boore-Atkinson 2008 GMPE and lognormal fragility curves
6. **Visualize** — Interactive Folium maps with color-coded risk overlays
7. **3D Reconstruction** — Drone photogrammetry via NodeODM integration

---

## Features

| Module | Description |
|---|---|
| **Download** | Google Street View API integration with metadata-driven scanning |
| **Image Processing** | Cropping, building detection (TF Hub Faster R-CNN), deduplication |
| **Classification** | BEiT-based structural typology classifier (24 building classes) |
| **Model Training** | Fine-tune ResNet50 / MobileNetV2 / InceptionV3 on custom datasets |
| **Risk Assessment** | Real-time video detection + scenario-based seismic risk engine |
| **Results Viewer** | Classified image browser with geospatial scatter plots |
| **3D Reconstruction** | NodeODM/WebODM tab for drone orthophoto and mesh generation |

---

## System Requirements

| Requirement | Minimum | Recommended |
|---|---|---|
| **OS** | Windows 10 / macOS 12+ | Windows 11 / macOS 14+ |
| **Python** | 3.10 (required) | 3.10 |
| **RAM** | 8 GB | 16 GB+ |
| **Disk** | 10 GB free | 20 GB+ (models + data) |
| **GPU** | Not required (CPU works) | NVIDIA GPU with 4+ GB VRAM |

> **Note:** Python **3.10** is required. TensorFlow 2.10 (the last version with native Windows GPU support) does not support Python 3.11+.

---

## Setup — Windows

### Step 1: Install Prerequisites

1. **Install Miniconda** (if not already installed):
   - Download from: https://docs.conda.io/en/latest/miniconda.html
   - During install, check **"Add to PATH"** or use the Anaconda Prompt

2. **Install Visual C++ Redistributable** (required for TensorFlow):
   - Download from: https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist

### Step 2: Clone the Repository

```bat
git clone https://github.com/shubhxtech/Riskmap.git
cd Riskmap
```

### Step 3: Create the Conda Environment

Open **Anaconda Prompt** (or any terminal with conda available):

```bat
conda create -n riskmap python=3.10 -y
conda activate riskmap
```

### Step 4: Install Dependencies

```bat
pip install -r requirements_windows.txt
```

> **GPU users:** See the [GPU Acceleration](#gpu-acceleration-optional) section below before running `pip install`. You'll want to install CUDA-enabled PyTorch first.

### Step 5: Verify Installation

Run the following to confirm all critical packages are installed:

```bat
python -c "import sys; print(f'Python: {sys.version}')"
python -c "import numpy; print(f'numpy: {numpy.__version__}')"
python -c "import torch; print(f'torch: {torch.__version__}')"
python -c "import tensorflow as tf; print(f'tensorflow: {tf.__version__}')"
python -c "from PyQt5.QtWidgets import QApplication; print('PyQt5: OK')"
python -c "from PyQt5.QtWebEngineWidgets import QWebEngineView; print('PyQtWebEngine: OK')"
python -c "import folium; print(f'folium: {folium.__version__}')"
python -c "from bs4 import BeautifulSoup; print('beautifulsoup4: OK')"
```

All lines should print without errors. You are now ready to run the app.

### Step 6: Run the Application

```bat
conda activate riskmap
cd src
python main.py
```

---

## Setup — macOS (Apple Silicon)

### Option A: Automated Setup (Recommended)

```bash
chmod +x setup_mac.sh
./setup_mac.sh
```

This script will:
1. Install Miniforge (if conda is not found)
2. Create a `riskmap` conda environment with Python 3.10
3. Install all dependencies from `requirements_mac.txt`
4. Verify critical imports

### Option B: Manual Setup

```bash
# 1. Install Miniforge (Apple Silicon native)
brew install miniforge
# — OR —
curl -L -O https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-MacOSX-arm64.sh
bash Miniforge3-MacOSX-arm64.sh -b -p $HOME/miniforge3
eval "$($HOME/miniforge3/bin/conda shell.zsh hook)"

# 2. Create environment
conda create -n riskmap python=3.10 -y
conda activate riskmap

# 3. Install dependencies
pip install -r requirements_mac.txt

# 4. Verify
python -c "
import sys; print(f'Python: {sys.version}')
import numpy; print(f'numpy: {numpy.__version__}')
import torch; print(f'torch: {torch.__version__}')
import tensorflow as tf; print(f'tensorflow: {tf.__version__}')
from PyQt5.QtWidgets import QApplication; print('PyQt5: OK')
from PyQt5.QtWebEngineWidgets import QWebEngineView; print('PyQtWebEngine: OK')
"

# 5. Run
cd src && python main.py
```

> **macOS Note:** On Apple Silicon, TensorFlow uses the `tensorflow-macos` + `tensorflow-metal` plugin for GPU acceleration via the Apple M-series Neural Engine. No NVIDIA CUDA setup is needed.

---

## Running the Application

After completing setup on either platform:

```bash
conda activate riskmap
cd src
python main.py
```

The application will open with the following tabs:

| Tab | Purpose |
|---|---|
| **Download** | Configure API keys and download street-level imagery |
| **Image Processing** | Crop panoramas and run building detection |
| **Train Model** | Fine-tune classification models on your dataset |
| **Analyze & Filter** | Classify buildings and remove duplicates |
| **Results** | Browse classified images with metadata |
| **Risk Assessment** | Run seismic risk scenarios on detected buildings |
| **3D Reconstruction** | Upload drone imagery to NodeODM for 3D models |

### First-Time Setup Inside the App

1. **API Key**: Go to the **Download** tab → enter your Google Street View API key
2. **Models**: The app will prompt to download required ML models on first use
3. **Region**: Configure your target region coordinates in the settings

---

## GPU Acceleration (Optional)

### Windows — NVIDIA GPU

#### PyTorch with CUDA 11.8

Install CUDA-enabled PyTorch **before** the main requirements:

```bat
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
pip install -r requirements_windows.txt
```

#### TensorFlow with GPU

TensorFlow 2.10 is the last version with native Windows GPU support. After `pip install`:

```bat
conda install -c conda-forge cudatoolkit=11.2 cudnn=8.1.0 -y
```

Restart the app — TensorFlow will auto-detect the GPU.

#### Verifying GPU Access

```python
python -c "import torch; print('CUDA:', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"
python -c "import tensorflow as tf; print('TF GPUs:', tf.config.list_physical_devices('GPU'))"
```

### macOS — Apple Silicon (M1/M2/M3/M4)

GPU acceleration is automatic via:
- **PyTorch**: MPS (Metal Performance Shaders) backend — enabled by default
- **TensorFlow**: `tensorflow-metal` plugin — install via `pip install tensorflow-metal`

---

## Project Structure

```
RiskMap/
├── src/                          # Application source code
│   ├── main.py                   # Entry point — launches PyQt5 app
│   ├── config_.py                # Configuration manager
│   ├── config_.ini               # Runtime configuration file
│   ├── styles.py                 # UI themes (dark/light/brand)
│   ├── utils.py                  # Path resolution utilities
│   ├── app_logger.py             # JSON-based logging
│   │
│   ├── api_window.py             # Street View API download tab
│   ├── crop_window.py            # Image cropping / processing
│   ├── building_detection.py     # TF Hub Faster R-CNN detection
│   ├── building_detection_window.py  # Detection UI
│   ├── classification.py         # BEiT typology classifier
│   ├── duplicates.py             # Duplicate image removal
│   ├── model_training.py         # Model fine-tuning UI
│   ├── results_window.py         # Classification results viewer
│   ├── risk_engine.py            # Seismic risk calculation engine
│   ├── geoscatter.py             # Geographic scatter plots
│   ├── streetview_scanner.py     # Street View scanning logic
│   ├── tile_downloader.py        # Map tile downloader
│   ├── notify_result.py          # Website change monitor utility
│   │
│   ├── rapidscan/                # Risk Assessment sub-module
│   │   ├── __init__.py
│   │   ├── _window.py            # Main RapidScan UI
│   │   ├── _video_processor.py   # Video-based building detection
│   │   ├── _risk_panel.py        # Risk assessment UI panel
│   │   ├── _constants.py         # UI color/style constants
│   │   └── odm_tab.py            # NodeODM 3D reconstruction tab
│   │
│   ├── assets/                   # Icons, UI assets
│   │   └── models/               # Downloaded ML models (git-ignored)
│   └── data/                     # Working data directory (git-ignored)
│
├── assets/
│   └── models/                   # Shared model storage
│
├── requirements.txt              # Base requirements (generic)
├── requirements_windows.txt      # Windows-specific requirements
├── requirements_mac.txt          # macOS-specific requirements
├── setup_mac.sh                  # macOS automated setup script
│
├── build_windows.py              # Windows PyInstaller build script
├── RiskMap.spec                  # PyInstaller spec file
├── RiskMap_Local_Build.iss        # Inno Setup installer script
├── BUILD_INSTALLER.md            # Installer build instructions
│
├── app.ico                       # Application icon
├── version.json                  # Version metadata
├── latlongid.csv                 # Coordinate reference data
├── pga_actual.csv                # Empirical PGA ground motion data
└── risk_results.csv              # Sample risk output
```

---

## Configuration

The application is configured via `src/config_.ini`. Key sections:

| Section | Description |
|---|---|
| `[General]` | App name, version, image sizes, region |
| `[Paths]` | Data directories, log file, database path |
| `[Download]` | Street View face size, scan spacing |
| `[BUILDING_DETECTION]` | Detection model URL, threshold, expand factor |
| `[Duplicates]` | Deduplication model path, batch size |
| `[Classification]` | Classifier model, 24 class names, confidence threshold |
| `[Model_Training]` | Training hyperparameters (epochs, LR, batch size, etc.) |

Settings can also be modified from within the app via the Settings panel.

### Environment Variables

Create a `src/secrets.env` file (git-ignored) for API keys:

```env
GOOGLE_API_KEY=your_google_street_view_api_key_here
```

---

## Building a Windows Installer

See [BUILD_INSTALLER.md](BUILD_INSTALLER.md) for detailed instructions. Quick summary:

```bat
conda activate riskmap
pip install -r requirements_windows.txt

:: Build the .exe
python build_windows.py

:: Output: dist\RiskMap\RiskMap.exe
```

The build produces a portable folder at `dist\RiskMap\` that can be zipped and distributed.

---

## 3D Reconstruction (NodeODM)

The **3D Reconstruction** tab connects to a NodeODM server for drone photogrammetry.

### Setup NodeODM (requires Docker)

```bash
# Install Docker Desktop first: https://www.docker.com/products/docker-desktop

# Start NodeODM (one-time)
docker run -d -p 3000:3000 --name nodeodm opendronemap/nodeodm

# With GPU support (NVIDIA)
docker run -d -p 3000:3000 --gpus all --name nodeodm opendronemap/nodeodm
```

Then in the app, connect to `localhost:3000` from the **3D Reconstruction** tab.

---

## Troubleshooting

### Installation Issues

| Problem | Solution |
|---|---|
| `pip install` fails for PyQt5 on Windows | Use `conda install pyqt` instead |
| `ModuleNotFoundError: PyQtWebEngine` | `pip install PyQtWebEngine==5.15.6` |
| `tensorflow` install fails on Python 3.11+ | Use Python 3.10 — TF 2.10 requires it |
| `cartopy` install fails | `conda install -c conda-forge cartopy` |
| `opencv-python` build errors | `pip install opencv-python-headless` as fallback |

### Runtime Issues

| Problem | Solution |
|---|---|
| Black screen / app doesn't start | Run `python main.py` from terminal to see errors |
| `tensorflow DLL load failed` (Windows) | Install the [Visual C++ Redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist) |
| `ModuleNotFoundError: rapidscan` | Ensure `src/rapidscan/` has an `__init__.py` |
| `QtWebEngineProcess not found` | Reinstall `PyQtWebEngine` in the conda env |
| GPU not detected by PyTorch | Check CUDA version matches PyTorch install (cu118/cu121/cu128) |
| `CUDA out of memory` | Close other GPU apps; reduce batch size in config |
| Very slow inference (no GPU) | See [GPU Acceleration](#gpu-acceleration-optional) section |
| RTX 5000 series not working with PyTorch | Upgrade: `pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128` |
| Map not loading in Risk Assessment | Check internet connection (Folium uses online tile servers) |

### Platform-Specific Notes

**Windows:**
- Always use **Anaconda Prompt** or ensure conda is in your PATH
- If `conda activate` doesn't work in PowerShell, run: `conda init powershell` then restart the terminal
- Firewall may block NodeODM Docker connections — allow port 3000

**macOS:**
- On Apple Silicon, use Miniforge instead of Anaconda for native ARM packages
- If `PyQt5` fails to install via pip, try: `conda install -c conda-forge pyqt`
- Grant camera/screen permissions if using video-based detection

---

## License

This project is developed for research purposes at IIT Mandi.
