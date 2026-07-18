# Work Mode Real Demo Flow

这份流程用于现场演示“总工作模式”作为真实桌面助手的能力。它不是 fast demo，也不是
链路一/链路三的单次测试；演示期间只让 `工作状态` 常驻运行，用麦克风开关分轮次录
完整语音。

## Demo Goal

演示要证明：

- 小安能用基站麦克风听完整一句话，中间短暂停顿不截断。
- 高确定性的本地功能能快速响应：机器人问候、状态、动作、表情、呼吸、待办、提醒、
  日程新增。
- 需要理解、查询、联网、笔记、规划和详细关怀的请求会交给 OpenClaw
  `xiaoan-runtime`。
- 链路二使用真实摄像头画面做面部状态观察，VLM gate 不强制常开。
- dashboard 能持续显示 ASR、回复、待办、日程、提醒和机器人动作状态。
- 每一轮结束后仲裁器回到可触发状态，下一轮能继续响应。

## Operator Rules

- 演示全程不要点链路一、链路三的“运行一次”。
- 演示全程不要打开 fast demo。
- `工作状态` 保持开启；每一轮只操作 `麦克风送入识别`：
  1. 打开麦克风。
  2. 说完一句完整话。
  3. 关闭麦克风。
  4. 等 ASR、TTS、动作或 OpenClaw 回复完成。
- 运动类演示前确认机器人前方至少有 20 cm 安全空间。
- 摄像头演示只打开真实摄像头，不使用保存图片作为演示证据。
- 如果 `episode_state` 卡在 `running` 超过 10 秒，先停止工作状态，不继续硬演。

## Preflight

### 1. Start Base Station

从仓库根目录启动 WebSocket server：

```bash
python3 -m base_station.ws_server.server
```

另一个终端启动 Integration Console：

```bash
python3 -m base_station.integration_console.console_server \
  --host 0.0.0.0 \
  --port 8090 \
  --ws-url ws://127.0.0.1:8765/agent \
  --runtime-dir runtime \
  --openclaw-url ws://127.0.0.1:18789
```

浏览器打开：

```text
http://<DK2500-IP>:8090/console
```

现场当前基站 IP 如果仍是 `192.168.137.139`，就打开：

```text
http://192.168.137.139:8090/console
```

### 2. Confirm OpenClaw Runtime

OpenClaw Gateway 应监听：

```text
ws://127.0.0.1:18789
agent: xiaoan-runtime
```

可选 smoke：

```bash
XIAO_AN_OPENCLAW_BACKEND=gateway \
XIAO_AN_OPENCLAW_GATEWAY_URL=ws://127.0.0.1:18789 \
XIAO_AN_OPENCLAW_AGENT=xiaoan-runtime \
.venv/bin/python tools/send_frontend_message.py "你好小安" --verbose
```

通过标准：返回 `handled=true`，有非空 `reply_text`，没有无关运动。

### 3. Confirm Robot And Camera

控制台顶部应看到：

- `Console` online。
- `Robot` online，heartbeat age 小于 30 秒。
- `OpenClaw` online 或至少 gateway check 成功。
- 摄像头演示前，camera preview 的 age 持续刷新，不是旧图。
- `工作状态` 初始为关闭，链路一/链路三/fast demo 都不在运行。

### 4. Start Work Mode

在控制台：

1. 关闭链路一、链路三、fast demo 的所有开关。
2. 打开 `工作状态`。
3. 勾选 `麦克风送入识别` 时只用于当前一句话。
4. 需要视觉段落时再勾选摄像头。

第一个证据：状态里 `work_voice` 运行，链路一/链路三不是 running。

## Demo Script

下面每一条都按同一个节奏操作：

```text
打开麦克风 -> 说触发句 -> 关闭麦克风 -> 等 dashboard 和机器人完成
```

### Segment A: Wake And Baseline

目标：证明总工作模式常驻、ASR 完整、TTS 能播、不会误进 OpenClaw。

| Step | 触发句 | 预期路线 | 观众能看到什么 |
| --- | --- | --- | --- |
| A1 | 小安小安你能听到我吗 | `local_fast_path.link3.greeting` | ASR 显示完整句子；机器人 TTS 回应“我在...” |
| A2 | 小安你醒着吗 | `local_fast_path.link3.greeting` | 证明不是整句模板匹配，口语说法也能触发 |
| A3 | 查询机器人状态 | `local_fast_path.link3.robot_status` | dashboard 显示本地机器人通道状态；OpenClaw event 不增加 |

讲解口径：

```text
这几句都不需要大模型。它们是本地高置信快路径，所以响应会比较快；
OpenClaw 留给需要理解、查询和生成的请求。
```

### Segment B: Local Robot Control

目标：覆盖链路三本地机器人动作、表情和安全动作顺序。

| Step | 触发句 | 预期路线 | 观众能看到什么 |
| --- | --- | --- | --- |
| B1 | 开心一点 | `local_fast_path.link3.set_expression` | 屏幕表情变 happy，随后 TTS 确认 |
| B2 | 陪我放松一下 | `local_fast_path.link3.breathing_guide` | 机器人说一段呼吸引导 |
| B3 | 靠近我 | `local_fast_path.link3.move_out` | 机器人小幅离开 Dock，随后 TTS 确认 |
| B4 | 往左转一点 | `local_fast_path.link3.turn_left` | 机器人左转 |
| B5 | 往右转一点 | `local_fast_path.link3.turn_right` | 机器人右转 |
| B6 | 回去待命 | `local_fast_path.link3.return_to_dock` | 机器人回 Dock |
| B7 | 停一下 | `local_fast_path.link3.stop_motion` | 如果机器人仍在动，应立即 stop |

安全提示：

- B3-B6 可以只挑 2-3 条演示；桌面空间不够时只演示表情、呼吸和 stop。
- 如果任何运动 ack 失败，直接跳过后续运动，不现场调参数。

### Segment C: Local Task Capture

目标：证明工作类本地快路径能写 runtime workspace，并同步到 dashboard。

建议使用统一 demo 前缀，方便演示后清理：

```text
真实Demo
```

| Step | 触发句 | 预期路线 | 通过证据 |
| --- | --- | --- | --- |
| C1 | 小安，帮我加个待办，真实Demo检查机器人状态 | `local_fast_path.link1.task_add` | `TASKS.md` 新增待办；dashboard 待办出现 |
| C2 | 我的任务 | `local_fast_path.link1.task_query` | TTS 列出刚才的待办 |
| C3 | 标记完成真实Demo检查机器人状态 | `local_fast_path.link1.task_complete` | `TASKS.md` 对应项变成 `[x]` |
| C4 | 记个任务真实Demo整理演示材料 | `local_fast_path.link1.task_add` | 证明“记个任务”也可触发 |
| C5 | 移除待办真实Demo整理演示材料 | `local_fast_path.link1.task_cancel` | 待办被标记完成并写 cancelled 来源 |

现场检查文件：

```bash
sed -n '1,120p' ~/.openclaw/workspace-xiaoan-runtime/TASKS.md
```

### Segment D: Schedule And Agenda

目标：区分“新增日程本地写入”和“查询日程交给 OpenClaw 读 `SCHEDULE.md`”。

| Step | 触发句 | 预期路线 | 通过证据 |
| --- | --- | --- | --- |
| D1 | 把晚上十一点真实Demo写作业加入日程 | `local_fast_path.link1.schedule_add` | `SCHEDULE.md` 写入日程；dashboard 日程出现 |
| D2 | 小安帮我查一下今天的日程 | `link_1_openclaw` | OpenClaw 根据 `SCHEDULE.md` 上下文回答，不说“没有上下文” |
| D3 | 把明天下午三点真实Demo复盘加到日程 | `local_fast_path.link1.schedule_add` | 证明“加到日程”口语说法可触发 |

讲解口径：

```text
写入这种确定性捕获，小安本地立刻做；查询和总结交给 xiaoan-runtime，
它会拿到 SCHEDULE.md / dashboard 的日程上下文再自然回答。
```

现场检查文件：

```bash
sed -n '1,160p' ~/.openclaw/workspace-xiaoan-runtime/SCHEDULE.md
```

### Segment E: Reminder Loop

目标：覆盖提醒新增、查询、取消、到点触发。

| Step | 触发句 | 预期路线 | 通过证据 |
| --- | --- | --- | --- |
| E1 | 十分钟后提醒我真实Demo喝水 | `local_fast_path.link1.reminder_add` | `SCHEDULE.md` 和 `state/local_reminders.json` 都有记录 |
| E2 | 看一下提醒 | `local_fast_path.link1.reminder_query` | TTS 列出待触发提醒 |
| E3 | 设个闹钟一分钟后真实Demo站起来活动一下 | `local_fast_path.link1.reminder_add` | 证明“设个闹钟”也能触发 |
| E4 | 等一分钟 | reminder due | 到点后机器人提示；dashboard 更新提醒状态 |
| E5 | 取消提醒真实Demo喝水 | `local_fast_path.link1.reminder_cancel` | `local_reminders.json` 对应项变成 `cancelled` |

现场检查：

```bash
cat ~/.openclaw/workspace-xiaoan-runtime/state/local_reminders.json
```

### Segment F: OpenClaw-Owned Intelligence

目标：证明本地不会误吃复杂请求，OpenClaw 负责自然语言理解、联网/工具、笔记和规划。

| Step | 触发句 | 预期路线 | 通过证据 |
| --- | --- | --- | --- |
| F1 | 帮我查一下今天北京天气 | `link_1_openclaw` | OpenClaw event 增加；本地 workspace 不写天气待办 |
| F2 | 帮我记录一条笔记：真实Demo桌面助手正在演示 | `link_1_openclaw` | 笔记由 OpenClaw/runtime tool 处理 |
| F3 | 帮我把今天剩下的安排整理成三步计划 | `link_1_openclaw` | OpenClaw 给出自然语言计划 |
| F4 | 我刚才让你记了什么 | `link_1_openclaw` | OpenClaw 尝试从 runtime 记忆/上下文回答 |

讲解口径：

```text
总工作模式不是所有东西都本地关键词解决。本地只处理高确定性、无网络、低风险动作；
需要理解和上下文的部分交给 OpenClaw。
```

### Segment G: Companion Care

目标：证明“我有点累”不是只机械回复，而是本地先做立即关怀，再由 OpenClaw 继续详细关怀。

| Step | 触发句 | 预期路线 | 观众能看到什么 |
| --- | --- | --- | --- |
| G1 | 小安我有点累 | `link_3_companion_fast_path` + `companion.request` | 小安先 caring 表情、短 TTS、靠近一点；随后 OpenClaw 追加更细的关怀语音 |
| G2 | 我心情不好，陪陪我 | `link_3_companion_fast_path` + `companion.request` | 同上，证明不同说法也能触发 |

通过标准：

- 本地预响应不只是 dashboard 文本，机器人实际说话。
- OpenClaw 后续回复不应只说“本地关怀已经完成”。
- 后续 OpenClaw 只做 speech follow-up，不重复运动。

### Segment H: Real Camera / Link 2

目标：证明链路二使用真实摄像头，不是保存图片；VLM gate 不强制触发。

操作：

1. 在总工作模式里打开摄像头。
2. 对准人脸，保持普通表情 10 秒。
3. 观察 camera preview age 持续刷新。
4. 观察 OpenFace / emotion / gate 状态刷新。
5. 不勾选强制 VLM，不使用保存图片。

| Step | 动作 | 预期 |
| --- | --- | --- |
| H1 | 普通表情看着摄像头 10 秒 | 视觉状态刷新；不应无故触发关怀 |
| H2 | 做疲惫/难过表情 10 秒 | Gate 根据疲惫/负向窗口决定是否触发；VLM 只在 gate 允许时运行 |
| H3 | 问“小安你看到我现在状态了吗” | 可走 OpenClaw，结合最新情绪上下文自然回答 |

通过证据：

- preview 是实时画面，age 小于 3 秒。
- visual trace frame id 递增。
- VLM trigger frame 与 gate reason 可解释。
- 没有 `force_vlm=true` 之类人工强制演示痕迹。

### Segment I: Recovery And Re-Trigger

目标：证明每轮结束后能恢复待触发，不会一直 cooldown 或 running。

| Step | 触发句 | 预期 |
| --- | --- | --- |
| I1 | 小安小安你能听到我吗 | 正常 TTS |
| I2 | 等 3 秒后再说：看一下待办 | 能再次触发，不被上一轮 cooldown 卡住 |
| I3 | 打开麦克风，说一句很长的话，中间停顿两秒，再继续说完 | ASR 保留完整开关窗口文本 |
| I4 | 关闭工作状态，再重新打开工作状态 | `work_voice` 重启；下一句还能识别 |

停止条件：

- ASR 文本为空但录音明显有声音。
- `episode_state` 超过 10 秒不是 `idle` 或合理短暂 `cooldown`。
- link1/link3 单次进程被误启动。
- TTS 文本有了但机器人没有播放，且无失败原因。

## Suggested One-Pass Demo Order

如果现场时间只有 8-12 分钟，按这个顺序走：

1. A1 `小安小安你能听到我吗`
2. B1 `开心一点`
3. B3 `靠近我`
4. B6 `回去待命`
5. C1 `小安，帮我加个待办，真实Demo检查机器人状态`
6. C2 `我的任务`
7. D1 `把晚上十一点真实Demo写作业加入日程`
8. D2 `小安帮我查一下今天的日程`
9. E3 `设个闹钟一分钟后真实Demo站起来活动一下`
10. F2 `帮我记录一条笔记：真实Demo桌面助手正在演示`
11. G1 `小安我有点累`
12. H1/H2 真实摄像头状态观察
13. 等一分钟，展示提醒到点
14. I2 再说一句 `看一下待办`，证明恢复可触发

## Evidence To Save

演示结束后导出或记录：

```text
runtime/integration_console/export_*.json
runtime/integration_console/process_logs/work_voice.log
runtime/integration_console/visual/latest_state.json
~/.openclaw/workspace-xiaoan-runtime/state/dashboard.json
~/.openclaw/workspace-xiaoan-runtime/TASKS.md
~/.openclaw/workspace-xiaoan-runtime/SCHEDULE.md
~/.openclaw/workspace-xiaoan-runtime/state/local_reminders.json
```

建议手工记录：

```text
demo date:
robot firmware env:
robot IP:
base station IP:
OpenClaw gateway:
camera live:
ASR backend:
TTS playback:
failed steps:
```

## Cleanup

演示用语都带 `真实Demo` 前缀，结束后可以在 runtime workspace 中搜索并清理：

```bash
rg -n "真实Demo" ~/.openclaw/workspace-xiaoan-runtime
```

不要在现场直接删除整个 `SCHEDULE.md`、`TASKS.md` 或 `state/` 目录；只清理演示条目。

## Presenter Notes

可以这样介绍架构：

```text
小安现在跑的是总工作模式。基站上的语音 runtime 常驻，麦克风开关决定每一轮完整录音窗口。
ASR 出文本后，本地先判断是不是高确定性的机器人动作、待办、提醒或日程新增；
命中就本地立即处理。查日程、天气、笔记、规划和更细的关怀交给 OpenClaw xiaoan-runtime。
视觉部分用真实摄像头持续更新，不强制 VLM；只有 gate 认为需要时才触发更重的视觉理解。
```

如果某一步失败，可以这样降级：

- OpenClaw offline：只演示 A/B/C/E 的本地快路径，明确说“OpenClaw 智能段今天不验收”。
- 摄像头 offline：跳过 H，只演示语音桌面助手。
- 机器人运动不安全：关闭运动，只演示表情、TTS、待办、日程、提醒和 OpenClaw。
- TTS 不稳定：保留 dashboard `tts_text` 和机器人 ack/失败原因，不把它说成通过。
