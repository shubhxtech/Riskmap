# RiskMap Build and Installer Guide

## Quick Start

### 1. Build the Executable
```bash
cd C:\Users\ashas\Desktop\Risk\RiskMap
python build_exe.py
```
This creates `dist\RiskMap.exe` (may take 5-10 minutes)

### 2. Compile the Installer
1. Open Inno Setup Compiler
2. Open `installer\RiskMap-local.iss`
3. Click **Build** > **Compile**
4. Installer will be created in `installer\output\RiskMapInstaller_Local.exe`

### 3. Test the Installer
- Run the installer
- Install to default location
- Launch RiskMap and verify all features work

## Build Options

### Local Offline Installer (Recommended)
**File:** `installer\RiskMap-local.iss`
- Packages everything locally
- No internet required
- Single file distribution

### Online Installer
**File:** `installer\RiskMap-release.iss`
- Downloads exe and models from GitHub
- Requires active GitHub release
- Smaller installer size

## Troubleshooting

### PyInstaller Build Issues
- **Missing modules**: Add to `hiddenimports` in `build_exe.py`
- **Large exe size**: Check if models are bundled (should be ~35-50 MB without models)
- **Import errors**: Verify all dependencies in `requirements.txt`

### Inno Setup Compilation Issues
- **File not found**: Check paths in .iss file match your directory structure
- **Missing tools**: Ensure 7za.exe is in `installer\tools\` (for release version)

### Installation Issues
- **App won't launch**: Check Windows Defender / antivirus didn't block it
- **Missing features**: Verify all config files are in install directory
- **Models not loading**: Check models folder exists or re-download

## File Size Reference
- Executable only: ~35-50 MB
- With models: ~500-800 MB
- Final installer: Varies based on compression
