#!/usr/bin/env bash
set -e

# Start the DK2500 base station WebSocket server.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -d "base_station/venv" ]; then
  echo "[info] base_station/venv does not exist."
  echo "       Create one with: python3 -m venv base_station/venv"
  echo "       Then install deps: source base_station/venv/bin/activate && pip install -r base_station/requirements.txt"
  python3 -m venv base_station/venv
  echo "[done] Created base_station/venv"
fi

# shellcheck disable=SC1091
source base_station/venv/bin/activate

if [ -f "base_station/requirements.txt" ]; then
  echo "[info] If dependencies are missing, run: pip install -r base_station/requirements.txt"
fi

echo "[start] python -m base_station.ws_server.server"
python -m base_station.ws_server.server
