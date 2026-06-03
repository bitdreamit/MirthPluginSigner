#!/usr/bin/env bash
# ============================================================
#  MirthPluginSigner — Linux / macOS build script
# ============================================================
set -e

echo ""
echo " ============================================================"
echo "  Building MirthPluginSigner (Linux/macOS)"
echo " ============================================================"
echo ""

# Check Python
python3 --version || { echo "[ERROR] Python3 not found."; exit 1; }

# tkinter check
python3 -c "import tkinter" 2>/dev/null || {
    echo "[INFO] Installing tkinter..."
    sudo apt-get install -y python3-tk 2>/dev/null || \
    sudo dnf install -y python3-tkinter 2>/dev/null || \
    brew install python-tk 2>/dev/null || \
    { echo "[ERROR] Install tkinter manually."; exit 1; }
}

# PyInstaller
pip3 install pyinstaller --break-system-packages 2>/dev/null || pip3 install pyinstaller

echo "[INFO] Building..."
python3 -m PyInstaller MirthPluginSigner.spec --clean

echo ""
echo " ============================================================"
echo "  SUCCESS → dist/MirthPluginSigner"
echo "  Make executable: chmod +x dist/MirthPluginSigner"
echo "  Run:             ./dist/MirthPluginSigner"
echo " ============================================================"
echo ""
