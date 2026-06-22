# 测试矩阵

> 状态：**P**=通过(本机编译/单测) **H**=硬件实机 **—**=未跑 **F**=失败

## Python 单元 / 集成

```powershell
python -m unittest discover -s tests -p "test_*.py"
python tools/check_runtime_env.py
```

| 区域 | 代表测试文件 | 覆盖 | 状态 |
|------|-------------|------|------|
| WS /control | `tests/integration/test_ws_control_channel.py` | hello, welcome, 命令 | P |
| WS 转发 | `tests/integration/test_ws_command_forwarding.py` | agent → robot | P |
| Agent Gateway | `tests/integration/test_agent_gateway.py` | RobotGateway | P |
| Robot Motion Skill | `tests/integration/test_robot_motion_skill.py` | 命令构建 | P |
| Emotion 流水线 | `tests/integration/test_emotion_runtime.py` 等 | mock 源 | P |
| Protocol schema | `tests/unit/test_protocol_schema.py` | schema 一致 | P |
| OpenVINO/Qwen | `tests/unit/test_openvino_*` | 模型 wrapper | 🧪 P |
| Mock robot | `tests/mocks/mock_robot.py` | 无 ESP32 测 control | 手动 |

## 固件编译（勿并行同 workspace 多 env）

| env | 命令 | 编译 | 硬件 H |
|-----|------|------|--------|
| `esp32-s3-devkitc-1` | `pio run -e esp32-s3-devkitc-1` | P | — |
| `motor_cam_wifi_manual` | `pio run -e motor_cam_wifi_manual` | P | H 可选 |
| `face240_wiretest` | `pio run -e face240_wiretest` | P | H |
| `face240_9expr_merged` | `pio run -e face240_9expr_merged` | P | H |
| `voice_recognition_test` | `pio run -e voice_recognition_test` | P | H |
| `speaker_amp_test` | `pio run -e speaker_amp_test` | P | H |

## Mergetesting

```powershell
cd robot\mergetesting
pio run -e mergetesting_display_only
pio run -e mergetesting_face240_only
pio run -e mergetesting_cam_only
pio run -e mergetesting_mic_only
```

| env | 编译 2026-06-22 | 联调 H |
|-----|-----------------|--------|
| `mergetesting_display_only` | P | — |
| `mergetesting_face240_only` | P | — |
| `mergetesting_cam_only` | P | — |
| `mergetesting_mic_only` | — | — |

## 固件工具脚本

| 脚本 | 命令 |
|------|------|
| face240 dirty-rect 结构检查 | `python robot/firmware/tools/test_face240_raw_dirty_rect.py` |
| face240 roboeyes framebuffer | `python robot/firmware/tools/test_face240_roboeyes_framebuffer.py` |
| 浏览器表情预览 | 打开 `robot/firmware/tools/face240_preview.html` |

## 端到端联调验收（人工）

| Phase | 验收项 | 通过标准 |
|-------|--------|----------|
| 1 | `/control` | 5min heartbeat；重连 |
| 2 | 命令 | 每条 `command.ack`；表情/电机/音 |
| 3 | `/video` | `runtime/latest.jpg` 更新 |
| 4 | 关怀闭环 | fatigue → OpenClaw → 三命令 |

**Agent 更新规则：** 跑过测试后在本表改 P/H/F 并注明日期。
