#!/usr/bin/env bash
set -e

# Start the DK2500 base station WebSocket server.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/base_station"

if [ ! -d "venv" ]; then
  echo "[info] base_station/venv does not exist."
  echo "       Create one with: python3 -m venv venv"
  echo "       Then install deps: source venv/bin/activate && pip install -r requirements.txt"
  python3 -m venv venv
  echo "[done] Created base_station/venv"
fi

# shellcheck disable=SC1091
source venv/bin/activate

if [ -f "requirements.txt" ]; then
  echo "[info] If dependencies are missing, run: pip install -r requirements.txt"
fi

echo "[start] python -m ws_server.server"
python -m ws_server.server
