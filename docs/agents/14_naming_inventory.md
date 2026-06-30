# Code Naming Inventory - 2026-06-30

> Purpose: track code names whose wording does not match their current role before renaming. Keep each rename small, reversible, and paired with compatibility wrappers where external commands or imports may exist.

Truth priority remains: live source / `platformio.ini` > `AGENTS.md` > `docs/current_status.md` > latest status snapshot > registries.

## Naming Rules

| Pattern | Use for | Avoid when |
|---------|---------|------------|
| `*_main.cpp` | PlatformIO firmware entrypoints selected by `build_src_filter` | The file is a library/module included by another entrypoint |
| `*_smoke.py` | Manual end-to-end or operator-run smoke checks | The file is an automated unittest/pytest test |
| `probe_*` | Diagnostic probes that inspect one subsystem | The script changes durable runtime state |
| `*_diagnostic` / `*_diag` | Isolated hardware or runtime diagnostics | The path is part of the normal demo loop |
| `legacy_*` | Compatibility implementation with no new feature ownership | The code is still the current product path |
| `deprecated_*` | Kept only to avoid import/route breaks | The feature is still allowed to grow |

## Batch N1 - Tools Manual Smoke Names

Status: in progress 2026-06-30.

These files were named like automated tests but are manual smoke helpers. The implementation files should use `manual_*_smoke.py`; root-level `tools/test_*.py` wrappers remain for compatibility.

| Old implementation | New implementation | Compatibility |
|--------------------|--------------------|---------------|
| `tools/legacy/test_agent_brain.py` | `tools/legacy/manual_agent_brain_smoke.py` | `tools/test_agent_brain.py` wrapper stays |
| `tools/legacy/test_emotion_policy.py` | `tools/legacy/manual_emotion_policy_smoke.py` | `tools/test_emotion_policy.py` wrapper stays |
| `tools/legacy/test_emotion_trigger.py` | `tools/legacy/manual_emotion_trigger_smoke.py` | `tools/test_emotion_trigger.py` wrapper stays |
| `tools/legacy/test_openclaw_tool_calls.py` | `tools/legacy/manual_openclaw_tool_call_smoke.py` | `tools/test_openclaw_tool_calls.py` wrapper stays |

Verification:

```powershell
python -m unittest tests.unit.test_openclaw_tool_call_runtime -v
python tools\test_openclaw_tool_calls.py --tool note.add --text hello
git diff --check
```

## Batch N2 - Firmware Bring-up Entrypoint Names

Status: planned, not started.

Several firmware entrypoints use `_test.cpp` even though they are PlatformIO hardware bring-up programs. Renaming these has higher risk because `platformio.ini`, docs, generated inventory, and sometimes hardware checklists must move together.

| Current file | More accurate candidate | Notes |
|--------------|-------------------------|-------|
| `robot/firmware/src/voice_recognition_test.cpp` | `inmp441_rms_check_main.cpp` | Current role is INMP441 electrical/RMS check, not real ASR |
| `robot/firmware/src/speaker_amp_test.cpp` | `max98357a_tone_check_main.cpp` | Current role is MAX98357A tone check |
| `robot/firmware/src/tft_test.cpp` | `display128_tft_smoke_main.cpp` | Current role is 128x160 TFT smoke |
| `robot/firmware/src/face240_wire_test.cpp` | `face240_wire_check_main.cpp` | Current role is ST7789 wiring/color check |
| `robot/firmware/src/face240_roboeyes_test.cpp` | `face240_roboeyes_demo_main.cpp` | Current role is RoboEyes demo path |
| `robot/firmware/src/keep_face_center_test.cpp` | `camera_motor_centering_demo_main.cpp` | Current role is minimal camera-to-motor validation demo |

Do not rename envs in the same first pass unless the old env names are kept as aliases.

## Batch N3 - Runtime And Legacy Boundaries

Status: planned, not started.

| Current path | Issue | Safer action |
|--------------|-------|--------------|
| `base_station/monitor/emotion_runtime.py` | Runtime now covers CV/OpenFace/VLM context, not only simple emotion samples | Defer physical rename; first add a public module alias if a new name is introduced |
| `agent/core/local_tools.py` | Contains local compatibility tools, not the future OpenClaw-owned tool surface | Defer split until OpenClaw runtime ownership is stable |
| `base_station/monitor/screen_watcher.py` | Deprecated screen monitoring placeholder | Keep as-is with deprecation label until imports disappear |
| `agent/skills/screen_report.py` | Deprecated companion to screen monitoring | Keep as-is with deprecation label until imports disappear |

## Do Not Rename Yet

| Path | Reason |
|------|--------|
| `robot/mergetesting` env names | They are documented hardware/demo contracts and used during active bring-up |
| `base_station/perception/openface_ov_runtime/` | Vendored import paths are fragile; moving requires a live OpenFace/OpenVINO smoke window |
| Protocol strings such as `asr.transcript.mock`, `audio.play_tts`, `display.expression` | These are wire contracts, not just local names |
