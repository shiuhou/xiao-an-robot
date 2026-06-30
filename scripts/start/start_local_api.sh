#!/usr/bin/env bash
set -e

# Start the Xiao An Local API for the DK-2500 software runtime smoke.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

VENV_PYTHON="$ROOT_DIR/.venv/bin/python"

if [ ! -x "$VENV_PYTHON" ]; then
  echo "[error] .venv python not found. Run first: bash scripts/setup_intel_board.sh"
  exit 1
fi

export XIAO_AN_OPENCLAW_BACKEND="${XIAO_AN_OPENCLAW_BACKEND:-gateway}"
export XIAO_AN_OPENCLAW_GATEWAY_URL="${XIAO_AN_OPENCLAW_GATEWAY_URL:-ws://127.0.0.1:18789}"
export XIAO_AN_OPENCLAW_AGENT="${XIAO_AN_OPENCLAW_AGENT:-xiaoan-runtime}"

echo "[start] XIAO_AN_OPENCLAW_BACKEND=$XIAO_AN_OPENCLAW_BACKEND"
echo "[start] XIAO_AN_OPENCLAW_GATEWAY_URL=$XIAO_AN_OPENCLAW_GATEWAY_URL"
echo "[start] XIAO_AN_OPENCLAW_AGENT=$XIAO_AN_OPENCLAW_AGENT"
exec "$VENV_PYTHON" -m base_station.api.server \
  --host 127.0.0.1 \
  --port 8787 \
  --db-path agent/data/xiao_an.db \
  --verbose
