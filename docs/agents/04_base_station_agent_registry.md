# 基站 & Agent 注册表

## Base Station — `base_station/`

### WebSocket — `ws_server/`

| 文件 | 状态 | 职责 |
|------|------|------|
| `server.py` | ✅ | 路由 `/control` `/video` `/audio` `/agent`；sessions；heartbeat 超时 |
| `protocol.py` | ✅ | `make_expression/motion/play_*`, `parse_message` |
| `stream_handler.py` | 🟡 | 流处理扩展点 |

#### `server.py` 处理器

| 函数 | 路径 | 行为 |
|------|------|------|
| `handle_control` | /control | hello 注册 session；welcome；heartbeat |
| `handle_video` | /video | 解析 8B 头；写 `runtime/latest.jpg` |
| `handle_audio` | /audio | 收 PCM，更新 `runtime/latest_audio.pcm` / audio stats；ASR demo 由 `audio_diagnostics.py`、`audio_segments.py`、`asr_runtime.py`、`continuous_asr_demo.py` 串接 |
| `handle_agent` | /agent | `agent.command` → 转发机器人 |
| `send_to_robot` | — | 按 device_id 下发 JSON |

启动：`python -m base_station.ws_server.server`

### Dashboard — `base_station/dashboard/`

| 路径 | 状态 | 说明 |
|------|------|------|
| `dashboard_server.py` | P | 7-inch Dock dashboard stdlib HTTP server；`/dashboard`、`/api/dashboard/state`、`/api/dashboard/today` |
| `static/dashboard.html/css/js` | P | 1024x600 kiosk UI；右侧显示系统健康、`Robot -> Base -> Agent -> Action` 链路、最近 3 条触发 |
| `data/triggers.json` | mock | pipeline/trigger mock；无真实 event store 时不得报错 |
| `data/today.json` | mock | 左侧今日日程/待办/闹钟 mock |

启动：`python -m base_station.dashboard.dashboard_server`
入口：`http://127.0.0.1:8088/dashboard`
测试：`python -m unittest tests.unit.test_dashboard_server`

### Perception — `base_station/perception/`

| 文件 | 状态 | 说明 |
|------|------|------|
| `face_emotion_pipeline.py` | 🟡 | 情绪流水线入口 |
| `openvino_face_emotion_model.py` | 🟡 | OpenVINO 人脸情绪 |
| `opencv_camera.py` | ✅ | OpenCV 相机源 |
| `fake_camera.py` / `fake_face_emotion.py` | 🧪 | mock |
| `asr.py` / `vad.py` | 🟡 | ASR/VAD 接口 |
| `audio_diagnostics.py` | ✅ | `/audio` WAV/PCM diagnostics, RMS/peak/DC/clipping checks before ASR tuning |
| `audio_segments.py` | ✅ | Fixed-window WAV speech trimming helper for `asr_runtime --trim-speech` |
| `qwen_vl_*` / `openvino_qwen_*` | 🟡 | VLM 路径 staged |
| `openface_ov_runtime/` | 🟡 | bundled vendored OpenFace/OpenVINO runtime；import path fragile，普通整理不要移动 |
| `tts.py` | 🟡 | TTS 占位 |

### Monitor — `base_station/monitor/`

| 文件 | 状态 | 说明 |
|------|------|------|
| `emotion_runtime.py` | ✅ | 情绪运行时 |
| `emotion_event_loop.py` | ✅ | 事件循环 |
| `emotion_db.py` | ✅ | SQLite 情绪记录 |
| `asr_runtime.py` | 🟡 | ASR 运行时；支持 audio-file path、SenseVoice backend、`--trim-speech` |
| `continuous_asr_demo.py` | 🟡 | Rolling `runtime/latest_audio.pcm` fixed-window utterance demo; not the final autonomous ASR loop |
| `emotion_context_builder.py` | ✅ | 上下文构建 |
| `screen_watcher.py` | ⚪ | deprecated；屏幕监控已退出 MVP |

---

## Agent — `agent/`

### Core

| 文件 | 状态 | 关键类/函数 |
|------|------|-------------|
| `core/brain.py` | ✅ | `XiaoAnBrain` — 事件路由 |
| `core/gateway.py` | ✅ | `RobotGateway` — WS `/agent` 客户端 |
| `core/action_executor.py` | ✅ | 动作执行编排 |
| `core/openclaw_adapter.py` | 🟡 | OpenClaw 适配 |
| `core/http_openclaw_adapter.py` | 🟡 | HTTP 版 |
| `core/local_tools.py` | ✅ | 本地工具；notes/tasks/reminders/summaries 为兼容层 |
| `core/memory.py` / `context_builder.py` | 🟡 | Local Event Store / 兼容上下文 |

### Skills

| 文件 | 状态 | 说明 |
|------|------|------|
| `skills/robot_motion.py` | ✅ | 发 expression/motion/tts |
| `skills/emotion_monitor.py` | ✅ | 情绪监控 skill |
| `skills/companion_request.py` | ✅ | 主动关怀 |
| `skills/*` (calendar, habit, etc.) | 🟡 | 扩展 skill |

---

## Shared — `shared/protocol/`

| 文件 | 对齐 |
|------|------|
| `message_types.py` | C++ `protocol.h` |
| `actions.py` | Expression, MotionAction |
| `errors.py` | ErrorCode |
| `schema.json` | JSON Schema |

**改协议必须同步：** `docs/protocol/protocol.md` + `protocol.h` + `protocol.py` + 示例 JSON。

---

## Tools — `tools/`

> 完整清单见 [10_repo_map.md](./10_repo_map.md) §Tools。改 CLI 时同步本表一行。

| 脚本 | 用途 | 状态 |
|------|------|------|
| `send_robot_command.py` | CLI → `/agent` → 机器人 expression/motion/local audio | ✅ |
| `run_integration_loop.py` | 联调 loop 编排 | 🟡 |
| `run_ws_video_runtime.py` | WS `/video` 运行时探测 | 🟡 |
| `send_test_video_frame.py` | 注入测试 JPEG 帧 | 🧪 |
| `check_runtime_env.py` | Python/模型/runtime 环境检查 | ✅ |
| `generate_agent_registry.py` | 刷新 `_generated/file_inventory.md` | ✅ |
| `setup_models.py` | 模型下载/放置引导 | 🟡 |
| `probe_openface_routeA_live.py` | OpenFace Route A 实机探测 | 🟡 |
| `probe_cv_gate.py` | CV gate 探测 | 🧪 |
| `probe_camera.py` | 相机源探测 | 🧪 |
| `simulate_emotion_stream.py` | 模拟情绪事件流 | 🧪 |
| `inject_emotion.py` | 注入情绪到 runtime | 🧪 |
| `test_agent_brain.py` | Agent brain 冒烟 | 🧪 |
| `test_emotion_trigger.py` | 情绪触发测试 | 🧪 |
| `test_emotion_policy.py` | 情绪策略单测入口 | 🧪 |
| `test_openclaw_tool_calls.py` | OpenClaw tool call 测试 | 🧪 |
| `query_emotion_summary.py` | 查情绪 DB 摘要 | 🟡 |
| `query_work_activity_summary.py` | 工作活动摘要 | 🟡 |
| `run_reminder_scheduler.py` | 提醒调度 | 🟡 |
| `send_frontend_message.py` | 向前端发消息 | 🧪 |
| `summarize_route_a_trace.py` | Route A trace 摘要 | 🟡 |
| `serial_camera_viewer.py` / `.ps1` | 串口相机查看 | 🧪 |
