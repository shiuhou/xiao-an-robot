#!/usr/bin/env bash
set -e

# Check the minimum local environment needed for development and DK2500 setup.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

echo "[check] repository root: $ROOT_DIR"

if [ ! -d "base_station" ] || [ ! -d "agent" ] || [ ! -d "robot" ]; then
  echo "[error] Please run this script from the xiao-an-robot repository root."
  exit 1
fi

if command -v python3 >/dev/null 2>&1; then
  echo "[ok] python3: $(python3 --version)"
else
  echo "[error] python3 was not found. Install Python 3.10+ before continuing."
  exit 1
fi

if command -v pip >/dev/null 2>&1; then
  echo "[ok] pip: $(pip --version)"
elif command -v pip3 >/dev/null 2>&1; then
  echo "[ok] pip3: $(pip3 --version)"
else
  echo "[error] pip was not found. Install pip for your Python environment."
  exit 1
fi

if [ -f "base_station/requirements.txt" ]; then
  echo "[ok] base_station/requirements.txt"
else
  echo "[error] Missing base_station/requirements.txt"
  exit 1
fi

if [ -f "agent/requirements.txt" ]; then
  echo "[ok] agent/requirements.txt"
else
  echo "[error] Missing agent/requirements.txt"
  exit 1
fi

if command -v sqlite3 >/dev/null 2>&1; then
  echo "[ok] sqlite3: $(sqlite3 --version)"
else
  echo "[warn] sqlite3 was not found. Install it with your package manager, for example:"
  echo "       Ubuntu/Debian: sudo apt install sqlite3"
  echo "       macOS: brew install sqlite"
  echo "       Windows: install SQLite tools or use WSL"
fi

echo "[done] environment check complete"

