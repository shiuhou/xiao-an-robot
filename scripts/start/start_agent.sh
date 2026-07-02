#!/usr/bin/env bash
set -e

# Start the Agent brain process after checking the local database exists.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

VENV_DIR="$ROOT_DIR/.venv"

if [ ! -f "$VENV_DIR/bin/activate" ]; then
  echo "[error] .venv not found. Run first: bash scripts/setup_intel_board.sh"
  exit 1
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

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
