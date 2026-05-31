#!/usr/bin/env bash
set -e

# Start the Agent brain process after checking the local database exists.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/agent"

if [ ! -d "venv" ]; then
  echo "[info] agent/venv does not exist."
  echo "       Create one with: python3 -m venv venv"
  echo "       Then install deps: source venv/bin/activate && pip install -r requirements.txt"
  python3 -m venv venv
  echo "[done] Created agent/venv"
fi

# shellcheck disable=SC1091
source venv/bin/activate

if [ ! -f "data/xiao_an.db" ]; then
  echo "[error] data/xiao_an.db does not exist."
  echo "        Run from the repository root: bash scripts/init_db.sh"
  exit 1
fi

if [ -f "requirements.txt" ]; then
  echo "[info] If dependencies are missing, run: pip install -r requirements.txt"
fi

echo "[start] python core/brain.py"
python core/brain.py

