# Codex Prompt — 实机 Active Emotion Care Demo 前检查

> 复制下面「Prompt 正文」整段给 Codex。分支：`mergetestint_robot`（merge fusion 后）。

---

## Prompt 正文（复制从这里开始）

```
按 xiao-an-session 开工。协作档位 A（仅 Git）。

## 任务
在跑 OpenClaw Step 33 emotion care demo 之前，确认 mergetesting 实机 prerequisites 全部 PASS；
然后给出「用 ESP32 替换 mock_robot」的实机 tired demo 执行清单（不要跳过 preflight）。

## 必须先读
- docs/agents/README.md
- docs/agents/00_snapshot.md
- docs/agents/11_openclaw_robot_integration.md
- docs/active_emotion_care_demo.md（merge 后已在仓库根 docs/）
- docs/project_status_2026-06-26.md
- docs/agents/08_priority_queue_results.json
- docs/agents/09_hardware_bringup_checklist.md

## 背景（不要搞错）
- OpenClaw xiaoan.robot.care 三连：display.expression caring → motion.execute move_out_of_dock → audio.play_tts（不是 care_01）
- care_01 是 audio.play_local 本地音效 ID，用于单独测喇叭；Step 33 care demo 默认走 TTS mock
- mock_robot 只接 /control 打印命令；实机 demo 用 mergetesting ESP32 替代 mock_robot

## Phase A — 软件 preflight（必须先跑并报告 exit code）
1. git status（报告 dirty 文件，勿 revert 他人改动）
2. python -m unittest discover -s tests -p "test_*.py"
3. cd robot/mergetesting && pio run -e mergetesting_care_demo_face240
   （Step 33 实机 demo 专用 env；已 H 见 08_priority_queue T18）

## Phase B — 实机 split-env 快速复验（按 09_hardware_bringup_checklist）
在 config.local.h 已配置 WiFi/基站 IP 前提下，逐项确认或列出用户需手测项：

| 项 | 命令/动作 | 预期 |
|----|-----------|------|
| 基站 | python -m base_station.ws_server.server | :8765 监听 |
| 烧录 | pio run -e mergetesting_care_demo_face240 -t upload | 串口 WiFi OK；无 cam/mic |
| control | 串口见 device.hello + heartbeat | WS 连上 |
| 表情 | python tools/send_robot_command.py expression caring | command.ack display.expression ok；屏 caring |
| 电机 | python tools/send_robot_command.py motion move_out_of_dock | motion.completed + ack；短距前移 |
| 本地音 | python tools/send_robot_command.py local care_01 | ack ok；喇叭 audible（care_01 预置 chime） |
| TTS mock | python tools/send_robot_command.py tts "测试" | ack audio.play_tts ok；mock tone（care demo 用这个路径） |

## Phase C — OpenClaw 环境（实机 demo 前）
确认用户已启动（或给出启动命令）：
- OpenClaw Gateway ws://127.0.0.1:18789
- xiaoan-runtime agent 可用
- 不要用 mock_robot.py；ESP32 已连 /control

## Phase D — 实机 tired demo（preflight 全 PASS 后才给命令）
Terminal 1: python -m base_station.ws_server.server
Terminal 2: ESP32 mergetesting（已 upload，serial 确认 /control connected）
Terminal 3:
  设置 XIAO_AN_OPENCLAW_BACKEND=gateway 等（见 docs/active_emotion_care_demo.md）
  python -m base_station.monitor.emotion_runtime --source fake_camera --model-backend mock --pattern tired --count 3 ...

## 实机预期（care 触发时）
1. 屏幕：caring 表情
2. 电机：move_out_of_dock 约 10cm 短移（2026-06-27 实测校准：speed=0.56, timeout≈1000-1200ms；0.56 才能可靠走出 base）
3. 喇叭：audio.play_tts mock tone（OpenClaw 回复文本），不是 care_01
4. 第 2/3 帧 tired：cooldown skipped
5. DB 有 emotion.intervention + robot.care_action

## 收工
- 更新 00_snapshot 一行（若实机 H）
- 输出收工摘要：每项 preflight PASS/FAIL + 实机观察
- 若有阻塞标 🔴 和下一步

禁止：未跑 unittest 就建议 tired demo；未确认 /control 就烧 full 合并 env；动 shared/protocol 不通知。
```

---

## 简短说明（给人看）

| 概念 | 说明 |
|------|------|
| `care_01` | `audio.play_local` 的本地音效 ID；speaker 播预置 chime，你 T13 已 H |
| Step 33 care | 用 `audio.play_tts` + OpenClaw 回复文本，固件 `speaker_play_tts_mock()` |
| mock → 实机 | Terminal 2 从 mock_robot 换成已烧 ESP32 |
