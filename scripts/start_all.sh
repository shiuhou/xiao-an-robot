#!/usr/bin/env bash
set -e

# Print the recommended startup order. Keeping process management manual avoids
# hiding logs or leaving background services running by accident.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VENV_DIR="$ROOT_DIR/.venv"

if [ ! -f "$VENV_DIR/bin/activate" ]; then
  echo "[error] .venv not found. Run first: bash scripts/setup_intel_board.sh"
  exit 1
fi

echo "[ok] Environment found at $VENV_DIR"
echo ""
echo "Recommended startup order:"
echo "1. bash scripts/start_base_station.sh"
echo "2. bash scripts/start_agent.sh"
echo "3. bash scripts/run_mock_robot.sh"
echo ""
echo "Open each command in a separate terminal so logs stay visible."

