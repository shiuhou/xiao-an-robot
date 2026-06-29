# Code Structure Inventory — 2026-06-29

> Purpose: keep repo cleanup mechanical and reversible. This file classifies code by current role before moving or archiving files.
> Truth priority remains: live source / `platformio.ini` > `AGENTS.md` > `docs/current_status.md` > latest status snapshot > registries.

## Summary

| Area | Current shape | Cleanup pressure | First action |
|------|---------------|------------------|--------------|
| `robot/mergetesting` | Main DK-2500 integration firmware; app/services split is already clear | Low | Do not move runtime modules during hardware bring-up; only document diagnostic envs |
| `robot/firmware` | Bring-up lab plus reusable module pool; many isolated entrypoints still live in `src/` | Medium | Move confirmed historical snapshots into `archive/`; keep active bring-up entrypoints where `platformio.ini` expects them |
| `base_station` | Runtime is clear, but OpenFace vendor/runtime code is deep under `perception/` | Medium | Keep as-is until model/runtime import paths are audited; document as vendored runtime |
| `agent` | Local compatibility layer plus OpenClaw adapters | Medium | Do not delete legacy compatibility; label deprecated surfaces clearly |
| `tools` / `scripts` | Tools are documented but still flat | Medium | Defer physical moves; tests import `tools.*` modules directly |
| `tests` | Broad but organized by unit/integration/mocks | Low | Keep import paths stable while source moves happen |

## Firmware Line

`robot/firmware` is not the DK-2500 demo path. It should remain a bring-up lab and reusable module pool.

### Keep As Current Bring-up Entrypoints

These are still wired by dedicated PlatformIO envs and should not move without updating `build_src_filter` and the registry in the same commit:

| File | Env | Role |
|------|-----|------|
| `motor_manual_main.cpp` | `motor_manual` | serial WASD motor bring-up |
| `motor_bench_once_main.cpp` | `motor_bench_once` | one-shot motor direction check |
| `motor_wifi_manual_main.cpp` | `motor_wifi_manual` | AP browser motor control |
| `motor_cam_wifi_manual_main.cpp` | `motor_cam_wifi_manual` | AP motor + camera integration smoke |
| `ota_bootstrap_main.cpp` | `ota_bootstrap`, `ota_bootstrap_wifi` | OTA recovery bridge |
| `camtesting_program.cpp` | `camtesting` | camera AP stream |
| `serial_qr_servo_main.cpp` | `serialqrservo` | serial JPEG + PC QR servo |
| `tft_test.cpp` | `display_test` | 128x160 TFT smoke |
| `face240_wire_test.cpp` | `face240_wiretest`, `face240_integrated`, legacy aliases | ST7789 wiring / color smoke |
| `face240_roboeyes_test.cpp` | `face240_roboeyes`, `face240` | 2.4 inch RoboEyes demo |
| `robot_face_9expr_merged_optimized.cpp` | `face240_9expr_merged` | product-like nine-expression face path |
| `tft_espi_probe.cpp` | `tftprobe_hybrid_rawinit` | ST7789 diagnostic |
| `voice_recognition_test.cpp` | `voice_recognition_test` | INMP441 electrical/RMS check |
| `speaker_amp_test.cpp` | `speaker_amp_test` | MAX98357A tone check |

### Archive Candidates

| File | Current evidence | Action |
|------|------------------|--------|
| `src/archive/integrated_main.cpp` | Env is explicitly `esp32-s3-integrated_legacy`; docs say new DK-2500 burns belong in `robot/mergetesting` | Moved out of active `src/` root on 2026-06-29 |
| `archive/face240_espi_test.cpp` | Already archived | Keep |
| `experiments/face240_raw_design_test.cpp` | Still used by `test_face240_raw_dirty_rect.py` | Keep in `experiments/` |

## Mergetesting Line

`robot/mergetesting` is the main integration firmware. The source tree is already split into:

| Path | Role |
|------|------|
| `src/main.cpp` | thin Arduino entrypoint |
| `src/app/` | app loop and hardware/service wiring |
| `src/services/` | command routing, robot state, status, non-blocking motion |
| `src/*.cpp` | hardware modules and transport |

Do not move these modules while the speaker pin map is still under active hardware validation. The safer cleanup is naming and documentation:

| Candidate | Reason | Action |
|-----------|--------|--------|
| speaker phrase/altpins/drain envs | Diagnostic envs are valuable but numerous | Keep, mark as diagnostic in registry and test matrix |
| `docs/setup/m600_deployment.md` | Machine-specific deployment note | Moved out of `robot/mergetesting` on 2026-06-29 |
| `CAPABILITIES.md`, `EXTRACTION_MAP.md`, `MAIN_DEMO.md` | Current local docs | Keep beside firmware project |

## Base Station And Agent

### Keep Stable

| Path | Reason |
|------|--------|
| `base_station/ws_server/` | Current `/control` `/video` `/audio` `/agent` runtime |
| `base_station/perception/audio_diagnostics.py` | Current mic bring-up and regression diagnostics |
| `base_station/perception/openface_ov_runtime/` | Vendored/runtime code with fragile import paths |
| `agent/core/*openclaw*` | OpenClaw bridge surface |

### Label, Do Not Delete Yet

| Path | Status |
|------|--------|
| `base_station/monitor/screen_watcher.py` | deprecated; screen monitoring exited MVP |
| `agent/skills/screen_report.py` | deprecated companion to screen monitoring |
| local memory/tasks/reminders/work_activity code | legacy compatibility for API/tests |

## Tools And Scripts

Physical `tools/` moves are deferred because many tests import `tools.*` directly. The next safe step is to add thin subdirectory wrappers or keep flat files and rely on `tools/README.md` grouping.

| Group | Current files |
|-------|---------------|
| Ops | `send_robot_command.py`, `run_integration_loop.py`, `run_reminder_scheduler.py` |
| Probes | `probe_camera.py`, `probe_cv_gate.py`, `probe_openface_routeA_live.py`, `probe_qwen_vl_openvino.py`, `serial_camera_viewer.py` |
| Evaluation | `eval_*`, `evaluate_*`, `summarize_route_a_trace.py`, `prepare_xiaoan_care_report_assets.py` |
| Maintenance | `check_runtime_env.py`, `generate_agent_registry.py`, `setup_models.py`, `setup_audio_models.py` |
| Manual smoke scripts | `test_agent_brain.py`, `test_emotion_policy.py`, `test_emotion_trigger.py`, `test_openclaw_tool_calls.py` |

## Recommended Cleanup Batches

| Batch | Scope | Risk | Verification |
|-------|-------|------|--------------|
| C1 | Move `robot/firmware/src/integrated_main.cpp` to `robot/firmware/src/archive/` and update docs/env | Done 2026-06-29 | `python -m unittest tests.unit.test_firmware_ota_bootstrap tests.unit.test_mergetesting_layering -v`; optional legacy env build |
| C2 | Move `robot/mergetesting/m600.md` to `docs/setup/m600_deployment.md` if still current | Done 2026-06-29 | Link/rg check |
| C3 | Add deprecation headers to screen monitoring files | Already satisfied | Existing docstrings checked 2026-06-29 |
| C4 | Decide whether tools stay flat or get wrapper packages | Medium | Full Python tests touching `tools.*` imports |
| C5 | Audit `base_station/perception/openface_ov_runtime/` vendored import paths | Medium/high | OpenFace/OpenVINO tests and live route smoke |

## Current Decision

C1 has been applied first because it improves the firmware line boundary without touching active hardware/debug paths. Continue with C2 only after link checks.
