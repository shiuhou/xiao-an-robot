#!/usr/bin/env bash
set -e

# Start the fake robot client for local /control channel testing.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

HOST="${BASE_STATION_HOST:-127.0.0.1}"
PORT="${CONTROL_WS_PORT:-8765}"

python3 tests/mocks/mock_robot.py --host "$HOST" --port "$PORT"

