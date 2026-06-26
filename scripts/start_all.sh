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
echo "1. Check OpenClaw Gateway is listening at ws://127.0.0.1:18789"
echo "2. bash scripts/start_base_station.sh"
echo "3. bash scripts/run_mock_robot.sh"
echo "4. bash scripts/start_local_api.sh"
echo "5. cd frontend && npm run dev"
echo "6. XIAO_AN_OPENCLAW_BACKEND=gateway XIAO_AN_OPENCLAW_GATEWAY_URL=ws://127.0.0.1:18789 XIAO_AN_OPENCLAW_AGENT=xiaoan-runtime .venv/bin/python tools/send_frontend_message.py \"你好小安，请用 caring 表情回应我\" --verbose"
echo ""
echo "Open each command in a separate terminal so logs stay visible."
