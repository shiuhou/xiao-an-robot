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
| `handle_audio` | /audio | 收 PCM（TODO 接 VAD/ASR） |
| `handle_agent` | /agent | `agent.command` → 转发机器人 |
| `send_to_robot` | — | 按 device_id 下发 JSON |

启动：`python -m base_station.ws_server.server`

### Perception — `base_station/perception/`

| 文件 | 状态 | 说明 |
|------|------|------|
| `face_emotion_pipeline.py` | 🟡 | 情绪流水线入口 |
| `openvino_face_emotion_model.py` | 🟡 | OpenVINO 人脸情绪 |
| `opencv_camera.py` | ✅ | OpenCV 相机源 |
| `fake_camera.py` / `fake_face_emotion.py` | 🧪 | mock |
| `asr.py` / `vad.py` | 🟡 | ASR/VAD 接口 |
| `qwen_vl_*` / `openvino_qwen_*` | 🟡 | VLM 路径 staged |
| `tts.py` | 🟡 | TTS 占位 |

### Monitor — `base_station/monitor/`

| 文件 | 状态 | 说明 |
|------|------|------|
| `emotion_runtime.py` | ✅ | 情绪运行时 |
| `emotion_event_loop.py` | ✅ | 事件循环 |
| `emotion_db.py` | ✅ | SQLite 情绪记录 |
| `asr_runtime.py` | 🟡 | ASR 运行时 |
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

**改协议必须同步：** `docs/protocol.md` + `protocol.h` + `protocol.py` + 示例 JSON。

---

## Tools — `tools/`

| 脚本 | 用途 |
|------|------|
| `send_robot_command.py` | CLI → `/agent` → 机器人 |
| `check_runtime_env.py` | 环境检查 |
| `generate_agent_registry.py` | 刷新 agent 文档清单 |
