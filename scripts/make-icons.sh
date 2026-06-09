#!/usr/bin/env bash
# Generate all home-screen / PWA icon sizes from a single square source image.
#   1. save your icon (ideally 1024x1024 PNG) to frontend/icon.png
#   2. run: ./scripts/make-icons.sh
set -euo pipefail
cd "$(dirname "$0")/../frontend"
SRC="${1:-icon.png}"

if [[ ! -f "$SRC" ]]; then
  echo "✗ No source icon found at frontend/$SRC"
  echo "  Save your icon image there (square, ~1024x1024 PNG) then re-run this."
  exit 1
fi

# sips is built into macOS — no dependencies needed.
sips -z 180 180 "$SRC" --out apple-touch-icon.png >/dev/null   # iOS home screen
sips -z 192 192 "$SRC" --out icon-192.png        >/dev/null   # Android / PWA
sips -z 512 512 "$SRC" --out icon-512.png        >/dev/null   # PWA hi-res / splash
sips -z 64  64  "$SRC" --out favicon.png         >/dev/null   # browser tab

echo "✓ generated: apple-touch-icon.png · icon-192.png · icon-512.png · favicon.png"
