# Mergetesting Layered Firmware Slice Implementation Plan

> **STATUS: COMPLETE (2026-06-26).** Phase 1 landed in `robot/mergetesting/src/app/` and `src/services/`. Keep for history; do not treat open tasks as current work. See `03_mergetesting_registry.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the working DK-2500 mergetesting firmware toward the layered firmware spec without rewriting the verified `/video` JPEG return path.

**Architecture:** Keep `robot/mergetesting` as the integration firmware. Convert `main.cpp` into a thin app entrypoint, move runtime state and `/control` command behavior into `services/`, and keep camera frame capture plus `WSClient::sendVideoBinary()` unchanged.

**Tech Stack:** PlatformIO, Arduino ESP32-S3, ArduinoJson, WebSocketsClient, existing Xiao-An mergetesting firmware.

## Global Constraints

- Preserve existing PlatformIO env names.
- Do not move DK-2500 integration behavior into `robot/firmware`.
- Do not rewrite the verified `/video` binary JPEG packet format.
- Keep `config.local.h` ignored and use `config.local.example.h` only for examples.
- Validate with specific envs: `mergetesting_display_only`, `mergetesting_cam_only`, and `mergetesting_cam_only_ota` when possible.

---

### Task 1: Add Layered Service Skeleton

**Files:**
- Create: `robot/mergetesting/src/services/robot_state.h`
- Create: `robot/mergetesting/src/services/robot_state.cpp`
- Create: `robot/mergetesting/src/services/status_service.h`
- Create: `robot/mergetesting/src/services/status_service.cpp`

**Interfaces:**
- Produces: `RobotState`, `StatusService::sendCurrent()`, `StatusService::ack()`, `StatusService::error()`, `StatusService::motionCompleted()`.
- Consumes: `WSClient::sendStatus()`, `sendCommandAck()`, `sendErrorReport()`, `sendMotionCompleted()`.

- [ ] Create `RobotState` with expression, motion, camera, busy, docked, WiFi, control, video, and audio status.
- [ ] Create `StatusService` as the only service that sends status, ack, error, and motion completion messages.
- [ ] Keep state defaults compatible with current `main.cpp`: expression `neutral`, motion `idle`, camera `cam_off`, busy `false`, docked `false`.

### Task 2: Extract Motion and Command Routing

**Files:**
- Create: `robot/mergetesting/src/services/motion_service.h`
- Create: `robot/mergetesting/src/services/motion_service.cpp`
- Create: `robot/mergetesting/src/services/command_router.h`
- Create: `robot/mergetesting/src/services/command_router.cpp`

**Interfaces:**
- Consumes: `RobotState`, `StatusService`, `MotorController`, `display_*`, `speaker_*`, `WSClient`.
- Produces: `MotionService::execute(JsonObject payload)` and `CommandRouter::handle(const String& type, JsonObject payload)`.

- [ ] Move `motionParamFromPayload()` and `finalPositionForAction()` into `motion_service.cpp`.
- [ ] Move `handleDisplayExpression()`, `handleMotionExecute()`, audio handlers, config update, shutdown, and unsupported-command handling into `CommandRouter`.
- [ ] Preserve command ordering: for `motion.execute`, send current status before motion, then `motion.completed`, then `command.ack`, then final status.
- [ ] Preserve busy rejection behavior: send `error.report` and `command.ack error`.

### Task 3: Make `main.cpp` a Thin App Entrypoint

**Files:**
- Create: `robot/mergetesting/src/app/mergetesting_app.h`
- Create: `robot/mergetesting/src/app/mergetesting_app.cpp`
- Modify: `robot/mergetesting/src/main.cpp`
- Modify: `robot/mergetesting/src/ws_client.h`
- Modify: `robot/mergetesting/src/ws_client.cpp`

**Interfaces:**
- Produces: `MergetestingApp::setup()` and `MergetestingApp::loop()`.
- Consumes: existing `WSClient`, `MotorController`, `CamStream`, `MicStream`, `CommandRouter`.

- [ ] Move WiFi, OTA, serial mock ASR, setup, and loop orchestration into `MergetestingApp`.
- [ ] Replace `main.cpp` with a global app instance and Arduino `setup()` / `loop()` forwarding.
- [ ] Add a `WSClient` busy provider so heartbeats use `RobotState::isBusy()` instead of always sending `busy=false`.
- [ ] Make `device.hello` capability flags reflect compile-time feature macros for display, motion, speaker, camera, mic, and OTA.

### Task 4: Align Hardware Defaults With Current Wiring

**Files:**
- Modify: `robot/mergetesting/src/hardware_pins.h`
- Modify: `robot/mergetesting/platformio.ini`
- Modify: docs that describe mergetesting pin/env status.

**Interfaces:**
- Consumes: current AGENTS.md wiring contract.
- Produces: canonical DRV8833 defaults left GPIO1/GPIO2 and right GPIO3/GPIO48, with TFT backlight tied to 3V3 (`TFT_BL=-1`).

- [ ] Update mergetesting motor pin defaults to GPIO1/GPIO2/GPIO3/GPIO48.
- [ ] Update integrated TFT build flag `TFT_BL=-1`.
- [ ] Do not change the camera-only env's verified video packet route.

### Task 5: Verify and Document

**Files:**
- Modify: `README.md`
- Modify: `docs/agents/03_mergetesting_registry.md`
- Modify: `robot/mergetesting/README.md`
- Modify: `hardware/wiring/esp32_pinout.md` only if pin facts changed from docs.

**Commands:**

```powershell
cd robot\mergetesting
pio run -e mergetesting_display_only
pio run -e mergetesting_cam_only
pio run -e mergetesting_cam_only_ota
cd ..\..
python -m unittest discover -s tests -p "test_*.py"
git diff --check
```

- [ ] Record whether each command passed, failed, or was skipped.
- [ ] Confirm `robot/mergetesting/src/cam_stream.cpp` still owns frame capture and `WSClient::sendVideoBinary()` still owns the binary packet send.
- [ ] Update docs to mark the layered refactor as started, with Phase 1 service/app split landed.
