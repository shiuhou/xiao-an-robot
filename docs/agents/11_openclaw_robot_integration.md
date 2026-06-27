# OpenClaw ↔ Mergetesting 实机联调说明

> 对照队友分支 `integration/openclaw-mergetesting-fusion`（zzy182）与本地 `mergetestint_robot`。
> 最后更新：2026-06-27

## 结论（先看这个）

**是的，协议层一致。** OpenClaw `xiaoan.robot.care` 最终发到 ESP32 `/control` 的消息类型，与你用 `tools/send_robot_command.py` 手动测成功的类型相同：

| 步骤 | OpenClaw care 动作 | `/control` 消息 type | 你 split-env 已验证 |
|------|-------------------|----------------------|---------------------|
| 1 | `xiaoan.robot.expression` → caring | `display.expression` | ✅ T11 face240 / display |
| 2 | `xiaoan.robot.move_out` | `motion.execute` action=`move_out_of_dock` | ✅ T12 motor |
| 3 | `xiaoan.robot.say` | `audio.play_tts`（固件 mock tone） | ✅ T13 speaker（TTS mock） |

**唯一差异：** 你单独测 local 音效时用 `audio.play_local` + `care_01`；OpenClaw care demo 默认走 **`audio.play_tts`**（带 `text_preview`），mergetesting 固件在 `command_router.cpp` 里用 `speaker_play_tts_mock()` 播放，不是 `care_01` 本地 wav。

## 消息路径对比

### 你手动测试（已 H）

```text
tools/send_robot_command.py
  → ws://127.0.0.1:8765/agent  (type: agent.command)
  → base_station build_robot_message()
  → ws://127.0.0.1:8765/control  (display.expression / motion.execute / audio.*)
  → mergetesting CommandRouter
```

### 队友 Step 33 mock 测试

```text
emotion_runtime (fake_camera, tired)
  → EmotionMonitorSkill → OpenClaw Gateway (ws://127.0.0.1:18789)
  → xiaoan-runtime 决策 → xiaoan.robot.care
  → ActionExecutor → RobotMotionSkill.care_for_user()
  → RobotGateway → 同上 /agent → /control
  → mock_robot（只 print，不执行硬件）
```

### 实机 emotion care（把 mock 换成 ESP32）

```text
（OpenClaw + emotion_runtime 同上）
  → RobotGateway → /agent → /control
  → 真实 ESP32 mergetesting（mergetesting_display_only 或 full_face240）
  → 屏幕 caring 表情 + 电机短距前移 + 喇叭 mock TTS 音
```

**Terminal 2 不要跑 `mock_robot.py`，改为烧录并上电 ESP32。**

## 实机跑 Step 33 Tired Demo（Windows）

前提：OpenClaw Gateway + `xiaoan-runtime` 已按队友文档运行。

```powershell
# T1 基站
python -m base_station.ws_server.server

# T2 实机：烧 mergetesting_display_only（或 face240 / full 合并 env）
cd robot\mergetesting
pio run -e mergetesting_display_only -t upload
# 确认 serial：WiFi OK、/control connected、device.hello

# T3 tired 干预（PowerShell 环境变量写法）
$env:XIAO_AN_OPENCLAW_BACKEND="gateway"
$env:XIAO_AN_OPENCLAW_GATEWAY_URL="ws://127.0.0.1:18789"
$env:XIAO_AN_OPENCLAW_AGENT="xiaoan-runtime"
$env:XIAO_AN_OPENCLAW_GATEWAY_TIMEOUT_SEC="90"
python -m base_station.monitor.emotion_runtime `
  --source fake_camera --model-backend mock --enable-vlm-gate --vlm-backend qwen_vl `
  --pattern tired --count 3 --interval 0 `
  --db-path agent/data/step33_demo.db --verbose
```

## 实机预期行为（care_for_user 三连）

1. **表情**：2.4" 或 128×160 屏切到 **caring**（env 需开 display/face240）
2. **电机**：**move_out_of_dock** 短脉冲（fusion 分支 clamp：speed≤0.2，distance≤2cm，timeout≤500ms）
3. **发声**：**audio.play_tts** → 固件 `speaker_play_tts_mock(text_preview)`，不是 care_01 文件

若 OpenClaw 回复文本较长，TTS mock 会随 `text_preview` 播放；与 `local care_01` 音色可能不同。

## 与队友文档的关系

| 文档 | 分支 | 用途 |
|------|------|------|
| `docs/active_emotion_care_demo.md` | fusion | Step 33 软件 mock 全流程 |
| `docs/openclaw_ownership_boundary.md` | fusion | OpenClaw vs 本仓库职责 |
| `docs/dk2500_software_runtime_smoke.md` | fusion | 无硬件 smoke |
| 本文 | mergetestint_robot | **mock → 实机** 衔接 |

## Pull / Merge 建议

```powershell
git fetch origin
git checkout mergetestint_robot
git merge origin/integration/openclaw-mergetesting-fusion
# 实测：自动 merge 无冲突（2026-06-27）
python -m unittest discover -s tests -p "test_*.py"
```

合并后优先读队友新增文档 + 跑 Step 33 mock，再把 Terminal 2 换成 ESP32 重复 tired demo。

## 下一步联合门控

- [ ] merge fusion 分支到 mergetestint_robot
- [ ] Step 33 mock 在你机器上 PASS
- [ ] Step 33 **实机** tired demo（display + motor + TTS mock）
- [ ] Step 38 真实摄像头 + 实机（见 fusion `docs/real_camera_emotion_smoke.md`）
- [ ] `mergetesting_full_face240` 合并 env 实机 H（T17）
