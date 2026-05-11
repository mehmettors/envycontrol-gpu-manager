#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> Installing PySide6 and PyInstaller..."
pip3 install -r requirements.txt
pip3 install pyinstaller

echo "==> Building standalone binary..."
pyinstaller \
    --onefile \
    --name "gpu-manager" \
    --hidden-import "PySide6.QtCore" \
    --hidden-import "PySide6.QtGui" \
    --hidden-import "PySide6.QtWidgets" \
    main.py

echo ""
echo "==> Build complete!"
echo "    Binary: dist/gpu-manager"
echo "    Size: $(du -h dist/gpu-manager | cut -f1)"
