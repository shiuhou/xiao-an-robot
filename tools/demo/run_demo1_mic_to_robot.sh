#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON="${REPO_ROOT}/.venv/bin/python"

if [[ ! -x "${PYTHON}" ]]; then
  echo "Missing .venv Python: ${PYTHON}" >&2
  echo "Run the Demo 1 setup first; see docs/runbooks/demo1_usb_mic_to_agent_screen.md" >&2
  exit 1
fi

cd "${REPO_ROOT}"
exec "${PYTHON}" tools/demo/demo1_usb_mic_to_agent_screen.py \
  --device "${DEMO1_MIC_DEVICE:-USB}" \
  --duration "${DEMO1_DURATION:-8}" \
  --asr-backend sensevoice \
  --asr-model-path "${DEMO1_ASR_MODEL_PATH:-base_station/models/sensevoice-small}" \
  --route-agent \
  "$@"
