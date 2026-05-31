# DK2500 Device Checklist

Use this checklist before running an integrated demo on the DK2500.

- Network is connected and stable.
- GitHub access works for clone, pull, and dependency inspection.
- Python 3 is installed.
- `python3 -m venv` can create virtual environments.
- Camera is detected and accessible.
- Microphone is detected and accessible.
- Speaker output works.
- OpenVINO runtime imports successfully.
- WebSocket control port, usually `8765`, is available.
- Agent database exists at `agent/data/xiao_an.db`.
- `bash scripts/check_env.sh` passes or has only understood warnings.
- `bash scripts/run_mock_robot.sh` can connect after the base station starts.

