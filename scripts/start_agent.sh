#!/usr/bin/env bash
set -e

# Start the Agent brain process after checking the local database exists.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -d "agent/venv" ]; then
  echo "[info] agent/venv does not exist."
  echo "       Create one with: python3 -m venv agent/venv"
  echo "       Then install deps: source agent/venv/bin/activate && pip install -r agent/requirements.txt"
  python3 -m venv agent/venv
  echo "[done] Created agent/venv"
fi

# shellcheck disable=SC1091
source agent/venv/bin/activate

if [ ! -f "agent/data/xiao_an.db" ]; then
  echo "[error] agent/data/xiao_an.db does not exist."
  echo "        Run from the repository root: bash scripts/init_db.sh"
  exit 1
fi

if [ -f "agent/requirements.txt" ]; then
  echo "[info] If dependencies are missing, run: pip install -r agent/requirements.txt"
fi

echo "[start] python -m agent.core.brain"
python -m agent.core.brain
