@echo off
REM ======================================
REM   RiskMap Windows Setup Script
REM   Run from Anaconda Prompt or any
REM   terminal with conda on PATH.
REM ======================================

echo.
echo ======================================
echo   RiskMap Windows Setup
echo ======================================
echo.

REM --- Check for conda ---
where conda >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] conda not found on PATH.
    echo         Install Miniconda from: https://docs.conda.io/en/latest/miniconda.html
    echo         Then re-run this script from Anaconda Prompt.
    pause
    exit /b 1
)

set ENV_NAME=riskmap

REM --- Check if environment already exists ---
conda env list | findstr /C:"%ENV_NAME%" >nul 2>&1
if %ERRORLEVEL%==0 (
    echo [OK] Environment '%ENV_NAME%' already exists. Activating...
) else (
    echo [SETUP] Creating conda environment '%ENV_NAME%' with Python 3.10...
    conda create -n %ENV_NAME% python=3.10 -y
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create conda environment.
        pause
        exit /b 1
    )
)

call conda activate %ENV_NAME%
echo [OK] Activated environment: %ENV_NAME%
python --version

REM --- Install requirements ---
echo.
echo [SETUP] Installing dependencies...
pip install -r requirements_windows.txt
if %ERRORLEVEL% neq 0 (
    echo.
    echo [WARNING] Some packages may have failed. Check output above.
    echo           Common fix: conda install -c conda-forge cartopy
    echo.
)

REM --- Verify imports ---
echo.
echo [VERIFY] Checking critical imports...
python -c "import sys; print(f'  Python: {sys.version}')"
python -c "import numpy; print(f'  numpy: {numpy.__version__}')"
python -c "import torch; print(f'  torch: {torch.__version__}')"
python -c "import tensorflow as tf; print(f'  tensorflow: {tf.__version__}')"
python -c "from PyQt5.QtWidgets import QApplication; print('  PyQt5: OK')"
python -c "from PyQt5.QtWebEngineWidgets import QWebEngineView; print('  PyQtWebEngine: OK')"
python -c "import folium; print(f'  folium: {folium.__version__}')"
python -c "from bs4 import BeautifulSoup; print('  beautifulsoup4: OK')"

if %ERRORLEVEL%==0 (
    echo.
    echo   === ALL IMPORTS SUCCESSFUL ===
)

echo.
echo ======================================
echo   Setup Complete!
echo ======================================
echo.
echo To activate the environment:
echo   conda activate %ENV_NAME%
echo.
echo To run the app:
echo   cd src
echo   python main.py
echo.
pause
