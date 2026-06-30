# Tools

Repository-local Python operation, probe, setup, and maintenance scripts live here.

Run commands from the repository root unless a tool says otherwise.

## Groups

The files are not yet physically grouped into subdirectories. Treat this as the intended ownership map before future `git mv` cleanup.

### Ops

Use these for normal local operation and demo smoke:

| Tool | Purpose |
| --- | --- |
| `send_robot_command.py` | Send expression, motion, local sound, and TTS commands through `/agent`. |
| `run_integration_loop.py` | Integration-loop orchestration. |
| `run_ws_video_runtime.py` | Runtime check for WS video path. |
| `inject_emotion.py` | Inject emotion samples into runtime. |
| `query_emotion_summary.py` | Query local emotion DB summaries. |
| `simulate_emotion_stream.py` | Generate local emotion events for monitor/Agent checks. |
| `run_e2e_emotion_smoke.py` | End-to-end emotion smoke runner. |

### Probes

Use these for manual diagnostics:

| Tool | Purpose |
| --- | --- |
| `probe_camera.py` | Camera source probe. |
| `probe_cv_gate.py` | CV gate probe. |
| `probe_openface_routeA_live.py` | OpenFace Route A live probe. |
| `probe_qwen_vl_openvino.py` | Qwen-VL/OpenVINO probe. |
| `send_test_video_frame.py` | Inject a test JPEG frame. |
| `serial_camera_viewer.py` / `.ps1` | Serial camera viewer. |

### Evaluation

| Tool | Purpose |
| --- | --- |
| `eval_visual_gate_segments.py` | Evaluate visual-gate segments. |
| `eval_vlm_images.py` | Evaluate VLM image outputs. |
| `evaluate_route_a_events.py` | Evaluate Route A event traces. |
| `evaluate_xiaoan_care_clips.py` | Evaluate care-demo clips. |
| `evaluate_xiaoan_care_policy.py` | Evaluate care-policy behavior. |
| `prepare_xiaoan_care_report_assets.py` | Prepare report assets for care-demo review. |

### Setup

| Tool | Purpose |
| --- | --- |
| `setup_models.py` | Model placement/download guidance. |
| `setup_audio_models.py` | Audio model setup/check helpers. |

### Maintenance

| Tool | Purpose |
| --- | --- |
| `check_runtime_env.py` | Check Python/runtime dependencies. |
| `generate_agent_registry.py` | Refresh `docs/agents/_generated/file_inventory.md`. |
| `summarize_route_a_trace.py` | Summarize Route A traces. |

### Legacy / Compatibility

These are useful for older paths or manual inspection, but are not the main demo surface:

- `query_work_activity_summary.py`
- `run_reminder_scheduler.py`
- `send_frontend_message.py`
- `test_agent_brain.py`
- `test_emotion_policy.py`
- `test_emotion_trigger.py`
- `test_openclaw_tool_calls.py`

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
