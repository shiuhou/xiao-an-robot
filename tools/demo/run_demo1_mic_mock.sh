#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON="${REPO_ROOT}/.venv/bin/python"

if [[ ! -x "${PYTHON}" ]]; then
  echo "Missing .venv Python: ${PYTHON}" >&2
  exit 1
fi

cd "${REPO_ROOT}"
exec "${PYTHON}" tools/demo/demo1_usb_mic_to_agent_screen.py \
  --mock-text "${DEMO1_MOCK_TEXT:-帮我记一下，今晚八点修改报告第三章}" \
  "$@"
