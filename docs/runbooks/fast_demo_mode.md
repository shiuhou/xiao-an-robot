# Fast Demo Mode / 快速演示模式

快速演示模式用于联调控制台现场演示。它不跳过 ASR 或视觉模型推理，只在“智能大脑回复”这一步改成本地确定性决策，避免现场等待 OpenClaw 判断导致演示节奏过长或不稳定。

## 入口

启动联调控制台后打开 `快速演示` 页面：

```bash
python -m base_station.integration_console.console_server --host 0.0.0.0 --port 8090
```

页面有三个独立链路开关：

- `FAST LINK 1`：麦克风 -> VAD/ASR -> 本地智能大脑回复 -> 表情/TTS 计划；reminder 会写入本地调度队列，到点后触发表情、出 Dock 和 TTS。
- `FAST LINK 2`：ws_video -> emotion_runtime -> OpenFace/Gate/VLM 视觉状态 -> 本地智能大脑回复。
- `FAST LINK 3`：麦克风 -> VAD/ASR -> 本地智能大脑回复 -> 秒级机器人响应计划。

页面还有两个总开关：

- `发送到机器人`：关闭时只展示回复和计划，不向机器人发命令。
- `允许运动`：关闭时可发送表情/TTS，但跳过运动步骤。

普通 `链路一/二/三` 页面不受影响，仍然走原 OpenClaw 路径。

## 安全边界

快速演示模式不会修改 Runtime OpenClaw 权限，也不会绕过机器人已有 WebSocket command path。

控制台内置自定义运动仍然走 `/api/robot/motion` 的安全限幅。快速演示语音链路中的自动运动计划使用固定保守参数：

- 出 Dock：`move_out_of_dock`，`speed=0.56`，`distance_cm=8.0`，`timeout_ms=1200`
- 回 Dock：`move_back_to_dock`，`speed=0.54`，`timeout_ms=1200`
- 停止：`stop`，`timeout_ms=800`

现场演示建议默认关闭 `允许运动`，确认桌面空间安全后再打开。

## 决策逻辑

### FAST LINK 1：记录/提醒类语音

ASR 完成后，本地决策模块读取 transcript 并做关键词意图判断：

- 包含“提醒、待会、等会、明天、几点、分钟后、小时后、闹钟、到点” -> `capture_reminder`
- 包含“会议、开会、讨论、meeting、复盘、周会” -> `capture_meeting`
- 包含“任务、待办、todo、安排、处理” -> `capture_task`
- 包含“想法、点子、灵感、idea、方案、笔记、记一下、记录、保存、备忘、写下来” -> `capture_note`
- 其他非空文本 -> `capture_note`
- 空文本 -> `no_speech`

普通记录类机器人计划以表情和 TTS 为主。`capture_reminder` 会额外写入 `runtime/integration_console/fast_demo/reminders.json`；控制台页面每秒轮询 `/api/state` 时检查是否到点。到点后会生成 `reminder_due` 决策：`speaking` 表情、`move_out_of_dock speed=0.56 distance_cm=8.0 timeout_ms=1200`、TTS 提醒。到点动作仍受创建 reminder 时的 `发送到机器人` 和 `允许运动` 开关控制。

时间解析支持：

- 相对时间：`10秒后`、`三分钟后`、`2小时后`、`半小时后`
- 绝对时间：`今天3点`、`下午三点半`、`明天9点20分`
- 没听出明确时间时默认 `1分钟后`，用于现场兜底演示。

示例话术：

- 提醒：“我记好啦。到点我会带着小提醒出来找你。”
- 待办：“待办我收下啦。你先不用一直挂在脑子里，我会帮你盯住它。”
- 笔记/想法：“这条笔记我记下啦，之后可以慢慢把它长成方案。”
- 到点提醒：“到点啦，我出来提醒你：该处理刚才那件事啦。”

### FAST LINK 2：视觉关怀

视觉 runtime 使用：

```bash
python -m base_station.monitor.emotion_runtime \
  --source ws_video_observer \
  --enable-vlm-gate \
  --model-backend openface_ov \
  --vlm-backend openvino_qwen_vl \
  --no-agent
```

它照常写入 `runtime/integration_console/fast_demo/visual/latest_state.json`。本地决策读取该状态文件，并融合以下信息：

- `gate.result.should_trigger`
- `cv_sample.emotion_tag`
- `cv_sample.confidence`
- `cv_sample.fatigue_score`
- `cv_sample.observation_quality`
- `vlm.result.expression_label` / `vlm.result.emotion_tag`
- `vlm.fusion.decision`

触发关怀的条件：

- Gate 已触发；
- 或疲劳分数 >= `0.72`；
- 或 OpenFace/CV 判断为 tired/sad/anxious/stressed 等负向状态且置信度 >= `0.60`；
- 或 VLM 标签/融合结果包含 tired/fatigue/sad/stress/困/累/疲惫/难过。

视觉质量低或没检测到人脸时不做关怀动作，只给出轻提示。示例话术：

- 关怀：“我看到你有点累啦。先眨眨眼，肩膀放下来，我陪你休息一分钟。”
- 正常：“我看你状态还挺稳的。小安在线巡逻中，有需要我就马上冒出来。”
- 看不清：“我这边还没看清你。你可以稍微靠近一点点，等我看清了再乖乖判断。”

当前页面展示视觉决策和机器人计划；视觉链路本身不把判断交给 OpenClaw。为避免持续运行时重复播放 TTS 或重复运动，视觉链路不会自动循环执行机器人动作。需要现场执行时，点击 `执行当前视觉计划`，该按钮会走控制台现有机器人命令路径，并受 `发送到机器人`、`允许运动` 两个开关控制。

### FAST LINK 3：陪伴/运动类语音

ASR 完成后，本地决策模块读取 transcript：

- 包含“停、停止、别动、不要动、stop” -> `stop_motion`
- 包含“回去、回 dock、回家、回窝、回充电、return” -> `return_to_dock`
- 包含“累、困、压力、难受、焦虑、陪我、休息、出来、过来” -> `companion_care`
- 包含“小安、你好、在吗、hello、嗨” -> `greeting`
- 其他非空文本 -> `gentle_ack`

动作设计：

- `stop_motion`：`idle` 表情 + `stop` 动作 + “好，我停下啦。你一句话，我就乖乖刹住。”
- `return_to_dock`：`idle` 表情 + 回 Dock 动作 + “收到，我准备回去啦。走之前也会轻轻跟你说一声。”
- `companion_care`：`caring` 表情 + 出 Dock 8cm + “我来啦。你先别硬撑，肩膀松一点，我陪你待一会儿。”
- `greeting`：`happy` 表情 + “我在呀。你一叫我，我的小灯就亮起来了。”
- `gentle_ack`：`thinking` 表情 + “我听到啦。你慢慢说，我就在旁边陪着。”

## 对外展示口径

快速演示页面统一使用“智能大脑回复”。不要在页面卡片里写“来源：本地快速演示决策”。内部事件和 JSON 文件可以保留 `decision_source=local_demo_brain`，用于开发调试。

## 运行文件

快速模式使用单独的运行产物目录：

- `runtime/integration_console/fast1/latest_voice.json`
- `runtime/integration_console/fast3/latest_voice.json`
- `runtime/integration_console/fast_demo/reminders.json`
- `runtime/integration_console/fast_demo/visual/latest_state.json`
- `runtime/integration_console/process_logs/fast1.log`
- `runtime/integration_console/process_logs/fast2.log`
- `runtime/integration_console/process_logs/fast3.log`

## 已知限制

`FAST LINK 2` 默认只持续更新当前视觉决策，不自动循环执行动作。这样能避免同一视觉状态在持续运行中反复触发。现场需要动作时，用 `执行当前视觉计划` 手动触发一次。
