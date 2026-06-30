# Tools

Repository-local Python operation, probe, setup, and maintenance scripts live here.

Run commands from the repository root unless a tool says otherwise.

## Groups

Tool implementations are physically grouped by ownership. Root-level `tools/*.py` files remain as compatibility wrappers, so existing commands such as `python tools\send_robot_command.py ...` and imports such as `from tools.send_robot_command import ...` continue to work.

### Ops

Use these for normal local operation and demo smoke:

| Tool | Purpose |
| --- | --- |
| `ops/send_robot_command.py` | Send expression, motion, local sound, and TTS commands through `/agent`. |
| `ops/run_integration_loop.py` | Integration-loop orchestration. |
| `ops/run_ws_video_runtime.py` | Runtime check for WS video path. |
| `ops/inject_emotion.py` | Inject emotion samples into runtime. |
| `ops/query_emotion_summary.py` | Query local emotion DB summaries. |
| `ops/simulate_emotion_stream.py` | Generate local emotion events for monitor/Agent checks. |
| `ops/run_e2e_emotion_smoke.py` | End-to-end emotion smoke runner. |

### Probes

Use these for manual diagnostics:

| Tool | Purpose |
| --- | --- |
| `probes/probe_camera.py` | Camera source probe. |
| `probes/probe_cv_gate.py` | CV gate probe. |
| `probes/probe_openface_routeA_live.py` | OpenFace Route A live probe. |
| `probes/probe_qwen_vl_openvino.py` | Qwen-VL/OpenVINO probe. |
| `probes/send_test_video_frame.py` | Inject a test JPEG frame. |
| `probes/serial_camera_viewer.py` / `.ps1` | Serial camera viewer. |

### Evaluation

| Tool | Purpose |
| --- | --- |
| `evaluation/eval_visual_gate_segments.py` | Evaluate visual-gate segments. |
| `evaluation/eval_vlm_images.py` | Evaluate VLM image outputs. |
| `evaluation/evaluate_route_a_events.py` | Evaluate Route A event traces. |
| `evaluation/evaluate_xiaoan_care_clips.py` | Evaluate care-demo clips. |
| `evaluation/evaluate_xiaoan_care_policy.py` | Evaluate care-policy behavior. |
| `evaluation/prepare_xiaoan_care_report_assets.py` | Prepare report assets for care-demo review. |

### Setup

| Tool | Purpose |
| --- | --- |
| `setup/setup_models.py` | Model placement/download guidance. |
| `setup/setup_audio_models.py` | Audio model setup/check helpers. |

### Maintenance

| Tool | Purpose |
| --- | --- |
| `maintenance/check_runtime_env.py` | Check Python/runtime dependencies. |
| `maintenance/generate_agent_registry.py` | Refresh `docs/agents/_generated/file_inventory.md`. |
| `maintenance/summarize_route_a_trace.py` | Summarize Route A traces. |

### Legacy / Compatibility

These are useful for older paths or manual inspection, but are not the main demo surface:

- `legacy/query_work_activity_summary.py`
- `legacy/run_reminder_scheduler.py`
- `legacy/send_frontend_message.py`
- `legacy/manual_agent_brain_smoke.py`
- `legacy/manual_emotion_policy_smoke.py`
- `legacy/manual_emotion_trigger_smoke.py`
- `legacy/manual_openclaw_tool_call_smoke.py`

Root-level `tools/test_agent_brain.py`, `tools/test_emotion_policy.py`, `tools/test_emotion_trigger.py`, and `tools/test_openclaw_tool_calls.py` remain compatibility wrappers for older commands/imports.

Move true tests into `tests/` over time; keep probe/manual scripts named as probes when they are not automated tests.

## Main Smoke

```powershell
python tools\send_robot_command.py --device-id xiaoan_robot_01 expression happy
python tools\send_robot_command.py --device-id xiaoan_robot_01 motion forward --bench --speed 0.56 --duration-ms 2000 --timeout-ms 2200
python tools\send_robot_command.py --device-id xiaoan_robot_01 local care_01
```

## Related Docs

- [../docs/current_status.md](../docs/current_status.md)
- [../docs/runbooks/main_demo_care_loop.md](../docs/runbooks/main_demo_care_loop.md)
- [../docs/agents/04_base_station_agent_registry.md](../docs/agents/04_base_station_agent_registry.md)
- [../docs/agents/10_repo_map.md](../docs/agents/10_repo_map.md)
