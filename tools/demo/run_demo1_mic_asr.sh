#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON="${REPO_ROOT}/.venv/bin/python"

if [[ ! -x "${PYTHON}" ]]; then
  echo "Missing .venv Python: ${PYTHON}" >&2
  echo "Run: python3 -m venv .venv && .venv/bin/python -m pip install PyAudio -r base_station/requirements-audio.txt" >&2
  exit 1
fi

cd "${REPO_ROOT}"
exec "${PYTHON}" tools/demo/demo1_usb_mic_to_agent_screen.py \
  --device "${DEMO1_MIC_DEVICE:-USB}" \
  --duration "${DEMO1_DURATION:-8}" \
  --asr-backend sensevoice \
  --asr-model-path "${DEMO1_ASR_MODEL_PATH:-base_station/models/sensevoice-small}" \
  "$@"
