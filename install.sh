#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BINARY="$SCRIPT_DIR/dist/gpu-manager"
TARGET="${HOME}/.local/bin/gpu-manager"

if [ ! -f "$BINARY" ]; then
    echo "Error: Binary not found at $BINARY"
    echo "Run ./build.sh first."
    exit 1
fi

mkdir -p "${HOME}/.local/bin"
cp "$BINARY" "$TARGET"
chmod +x "$TARGET"

echo "Installed to $TARGET"
echo ""
echo "Make sure ${HOME}/.local/bin is in your PATH."
echo "Run with: gpu-manager"
