# M600 Base Station Deployment Note

## Purpose

This document tells Codex what my Morefine M600 mini PC is, how it should be used in the `xiao-an-robot` project, and what the safe next steps are.

Do not treat this as a brand-new project. This repository already has an existing base-station / agent / robot firmware architecture. The M600 should be used to bring up and test the existing base-station path, not to create an unrelated new server from scratch.

---

## My Hardware

I have a Morefine M600 mini PC.

Known specs:

* Model: Morefine M600
* CPU: AMD Ryzen 7 7840HS
* RAM: 32GB DDR5 5600
* Storage: 1TB PCIe 4.0 NVMe SSD
* GPU: AMD Radeon 780M integrated GPU
* OS plan: Windows 11 + WSL2 Ubuntu 24.04

Main development location on M600 Ubuntu / WSL:

```bash
~/robot_lab/xiao-an-robot
```

The M600 should temporarily play the role of the project's local base station. The original project mentions Intel DK-2500 / Core Ultra, but for my current bring-up work, the M600 is the machine that should run the base-station server, mock tests, Python tools, OpenCV experiments, and later lightweight AI / agent logic.

---

## What I Want The M600 To Do

The M600 should become the robot base station for Xiao An.

Target system:

```text
ESP32-S3 robot body
    - camera
    - TFT face display
    - motors / servos
    - touch / buttons
    - mic / speaker later

        <-> Wi-Fi WebSocket

Morefine M600 base station
    - WebSocket server
    - robot session management
    - command dispatch
    - local perception / OpenCV later
    - Agent / OpenClaw / LLM path later
    - logging and debugging
```

The first real goal is not full AI. The first real goal is:

```text
Run the existing base_station on M600
-> Run the existing mock_robot
-> Confirm /control WebSocket works locally
-> Send expression / motion / TTS test commands
-> Replace mock_robot with real ESP32-S3 firmware
-> Make real ESP32 send device.hello and receive system.welcome
-> Make TFT expression change from a base-station command
```

---

## Important Repo Context

Before modifying anything, read these files and folders first:

```text
README.md
AGENTS.md
docs/status/2026-06-22.md
docs/protocol/protocol.md
base_station/
agent/
shared/
tests/mocks/mock_robot.py
robot/firmware/platformio.ini
```

After reading, summarize what already exists.

Do not assume this is an empty repo. The repo already appears to contain:

* `base_station/` for WebSocket server, perception, monitor, ASR/emotion runtime
* `agent/` for Agent brain, skills, gateway, memory/context shell
* `shared/` for protocol constants, schemas, examples
* `tests/mocks/mock_robot.py` for fake robot `/control` testing
* `robot/firmware/` for ESP32-S3 firmware and isolated PlatformIO hardware tests
* `docs/protocol/protocol.md` as the WebSocket contract between ESP32 and base station

---

## Codex First Task

Your first task is investigation only.

Do not modify code yet.

Please produce a short report:

1. Current repo structure
2. Existing base-station entry points
3. Existing WebSocket routes
4. How `/control` currently works
5. How to run the base station on M600 Ubuntu / WSL
6. How to run `tests/mocks/mock_robot.py`
7. How to send a test command to the mock robot
8. What is missing before connecting the real ESP32-S3
9. Which files are safe to edit next
10. Which files should not be touched yet

After the report, ask me before making code changes.

---

## M600 Bring-Up Strategy

Use the existing repo architecture first.

Do not create a separate unrelated `websocket_server.py` unless it is only a temporary learning test outside the main project.

For the real project, prefer the existing path:

```text
base_station/ws_server/
tests/mocks/mock_robot.py
tools/send_robot_command.py
shared/
robot/firmware/
```

The first M600 milestone should be:

```text
M600 local base-station test
    1. create Python venv
    2. install base_station requirements
    3. run base_station server
    4. run mock_robot
    5. send expression command
    6. observe mock_robot receiving command
```

Then:

```text
Real ESP32-S3 /control test
    1. configure ESP32 Wi-Fi
    2. configure base-station IP
    3. flash main firmware env
    4. ESP32 connects to ws://M600_LOCAL_IP:8765/control
    5. ESP32 sends device.hello
    6. M600 replies system.welcome
    7. M600 sends display.expression
    8. ESP32 changes TFT face expression
```

---

## Expected Protocol Direction

The project protocol should remain:

```text
/control
    bidirectional JSON control channel

/audio
    robot-to-base binary audio stream, later

/video
    robot-to-base JPEG frame stream, later

/agent
    local agent-to-base command route
```

For now, focus on `/control`.

Do not make `/video`, `/audio`, OpenVINO, Qwen, ASR, TTS, or OpenClaw real deployment blockers for the first visible demo.

---

## First Demo Priority

The first useful demo should be:

```text
Base station command
-> display.expression
-> ESP32 TFT face changes

Base station command
-> motion.execute
-> ESP32 motor moves briefly and safely
-> ESP32 returns motion.completed
```

Only after that is stable should we add:

```text
low-rate camera /video
OpenCV perception
Agent decision
OpenClaw / LLM path
audio / ASR / TTS
```

---

## Safety Rules For Codex

Follow these rules:

1. Read current files before changing anything.
2. Do not overwrite active work.
3. Do not delete or revert files unless I explicitly ask.
4. Do not restructure the repo.
5. Do not merge unrelated branches.
6. Do not add Docker, ROS2, OpenVINO, Qwen, or YOLO in the first bring-up step.
7. Do not touch hardware pin assumptions unless the exact wiring is confirmed.
8. Do not run broad PlatformIO builds blindly.
9. Use targeted firmware envs only.
10. Keep generated files out of Git.

---

## Windows / WSL Split

Use this split:

### Windows side

Use Windows mainly for:

```text
VS Code UI
PlatformIO extension if needed
USB serial / COM port flashing
Obsidian
browser tools
```

### Ubuntu / WSL side

Use Ubuntu / WSL mainly for:

```text
Python base_station
mock_robot
agent tests
OpenCV experiments
WebSocket server runtime
Codex CLI
repo inspection
```

For Python/base-station work, prefer WSL paths:

```bash
~/robot_lab/xiao-an-robot
```

Do not put Linux Python virtual environments inside Windows `C:\Users\...` paths.

---

## Suggested First Commands For M600 Ubuntu

From M600 Ubuntu / WSL:

```bash
cd ~/robot_lab
git clone https://github.com/shiuhou/xiao-an-robot.git
cd xiao-an-robot
git status
```

Create a safe branch:

```bash
git checkout -b m600-base-station-bringup
```

Then inspect first:

```bash
ls
find base_station agent shared tests/mocks -maxdepth 3 -type f | sort
```

Then create a venv only after confirming requirements:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

Then install only the needed requirements after checking the files:

```bash
python -m pip install -r base_station/requirements.txt
```

Run checks before changing code:

```bash
python -m unittest discover -s tests -p "test_*.py"
python tools/check_runtime_env.py
```

---

## What I Want Codex To Output First

Before writing or editing code, output this:

```text
M600 Base-Station Bring-Up Report

1. Repo structure summary
2. Base-station startup command
3. Mock robot startup command
4. Command sender usage
5. Current /control message flow
6. Missing real ESP32 configuration
7. Risks / unknowns
8. Recommended next 3 actions
```

Then stop and wait for my confirmation.
