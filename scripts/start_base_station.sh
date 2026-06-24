#!/usr/bin/env bash
set -e

# Start the DK2500 base station WebSocket server.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VENV_DIR="$ROOT_DIR/.venv"

if [ ! -f "$VENV_DIR/bin/activate" ]; then
  echo "[error] .venv not found. Run first: bash scripts/setup_intel_board.sh"
  exit 1
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

if [ -f "base_station/requirements.txt" ]; then
  echo "[info] If dependencies are missing, run: pip install -r base_station/requirements.txt"
fi

echo "[start] python -m base_station.ws_server.server"
python -m base_station.ws_server.server
