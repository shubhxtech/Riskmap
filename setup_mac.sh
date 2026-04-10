#!/bin/bash
# RiskMap macOS Setup Script
# Creates conda environment and installs all dependencies

set -e

echo "======================================"
echo "  RiskMap macOS Setup"
echo "======================================"
echo ""

# Check for conda
if ! command -v conda &> /dev/null; then
    CONDA_PATH="$HOME/miniforge3/bin/conda"
    if [ ! -f "$CONDA_PATH" ]; then
        echo "❌ Conda not found. Installing Miniforge..."
        curl -L -O "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-MacOSX-arm64.sh"
        bash Miniforge3-MacOSX-arm64.sh -b -p $HOME/miniforge3
        rm Miniforge3-MacOSX-arm64.sh
        echo "✅ Miniforge installed"
    fi
    eval "$($HOME/miniforge3/bin/conda shell.bash hook)"
else
    eval "$(conda shell.bash hook)"
fi

ENV_NAME="riskmap"

# Create environment if it doesn't exist
if conda env list | grep -q "^${ENV_NAME} "; then
    echo "📦 Environment '${ENV_NAME}' already exists. Activating..."
else
    echo "📦 Creating conda environment '${ENV_NAME}' with Python 3.10..."
    conda create -n $ENV_NAME python=3.10 -y
fi

conda activate $ENV_NAME
echo "✅ Activated environment: $ENV_NAME (Python $(python --version 2>&1))"

# Install requirements
echo ""
echo "📥 Installing dependencies..."
pip install -r requirements_mac.txt

# Verify imports
echo ""
echo "🔍 Verifying imports..."
python -c "
import sys
print(f'  Python: {sys.version}')
import numpy; print(f'  numpy: {numpy.__version__}')
import torch; print(f'  torch: {torch.__version__}')
import tensorflow as tf; print(f'  tensorflow: {tf.__version__}')
from PyQt5.QtWidgets import QApplication; print('  PyQt5: OK')
from PyQt5.QtWebEngineWidgets import QWebEngineView; print('  PyQtWebEngine: OK')
import folium; print(f'  folium: {folium.__version__}')
print()
print('  === ALL IMPORTS SUCCESSFUL ===')
"

echo ""
echo "======================================"
echo "  ✅ Setup Complete!"
echo "======================================"
echo ""
echo "To activate the environment:"
echo "  conda activate $ENV_NAME"
echo ""
echo "To run the app:"
echo "  cd src && python main.py"
echo ""
