# DK2500 Device Checklist

Use this checklist before running an integrated demo on the DK2500.

- [ ] Network is connected and stable on the robot/base-station LAN.
- [ ] GitHub access works for clone, fetch, dependency inspection, and planned PR work.
- [ ] Python 3.10+ is installed.
- [ ] `python -m venv` or `python3 -m venv` can create virtual environments.
- [ ] `python tools/check_runtime_env.py` runs and missing optional packages are understood.
- [ ] `python tools/check_runtime_env.py --check-camera` can open the selected camera, or the camera gap is documented.
- [ ] Microphone is detected by the OS.
- [ ] Speaker output works.
- [ ] OpenVINO runtime imports successfully before real model testing.
- [ ] WebSocket control port `8765` is available.
- [ ] `agent/data/xiao_an.db` exists after applying `agent/data/schema.sql`.
- [ ] `python -m base_station.ws_server.server` starts without import errors.
- [ ] `python tests/mocks/mock_robot.py --host 127.0.0.1 --port 8765` can connect after the base station starts.
- [ ] Agent command sender can reach `/agent` and forward a test expression/motion command.

Current staged expectation: fake/mock perception may pass before real OpenVINO/ASR/VAD/TTS packages and models are installed.

