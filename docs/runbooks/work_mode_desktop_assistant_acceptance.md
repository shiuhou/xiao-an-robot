# Work Mode Desktop Assistant Acceptance

这套验收用于判断“总工作模式”是否已经能当真实桌面助手试用。目标不是只看
dashboard 有字，而是确认麦克风、ASR、路由、TTS、机器人动作、摄像头和失败恢复都
能闭环。

机器可读用例放在：

```bash
tests/fixtures/work_mode_desktop_acceptance_cases.json
```

自动路由回归测试：

```bash
python3 -m unittest tests.unit.test_work_mode_desktop_acceptance_cases -v
```

## 通过标准

一次完整验收通过需要同时满足：

- `工作状态` 开启后，`work_voice` 常驻运行，链路一/三普通开关不同时运行。
- 麦克风从开启到关闭形成一个完整 ASR segment，中间短暂停顿不截断。
- 本地确定性任务走 `local_fast_path.*`，不误进 OpenClaw。
- 天气、笔记、复杂规划走 `link_1_openclaw`，不被本地规则误吃。
- 每条 handled 回复都有 dashboard `tts_text`，机器人侧有 `audio.play_tts` 或明确失败原因。
- 机器人动作只走白名单动作，运动测试前桌面空间安全。
- 摄像头使用真实 `link2_visual_trace` 帧；VLM gate 不应被人工强制常开。
- 每轮结束后仲裁器回到 `idle` 或短暂 `cooldown`，下一轮能继续触发。

## 启动

从仓库根目录启动联调控制台：

```bash
python3 -m base_station.integration_console.console_server --host 0.0.0.0 --port 8090
```

打开页面后：

1. 关闭链路一、链路三、fast demo 的所有单次/演示开关。
2. 打开 `工作状态`。
3. 勾选 `麦克风送入识别`。
4. 需要视觉验收时再勾选摄像头。
5. 运动类验收前确认机器人前方空间安全。

## 验收矩阵

| ID | 触发句 | 预期路线 | 通过证据 |
| --- | --- | --- | --- |
| WM-A01 | 小安小安你能听到我吗 | `local_fast_path.link3.greeting` | ASR 有完整文本；`tts_text` 非空；机器人说话 |
| WM-A02 | 查询机器人状态 | `local_fast_path.link3.robot_status` | 不进入 OpenClaw；回复包含本地机器人通道状态 |
| WM-L1-01 | 小安，帮我加个待办，测试桌面助手验收 | `local_fast_path.link1.task_add` | `TASKS.md` 出现新待办；机器人确认 |
| WM-L1-02 | 看一下待办 | `local_fast_path.link1.task_query` | 回复列出刚才的待办 |
| WM-L1-03 | 完成待办测试桌面助手验收 | `local_fast_path.link1.task_complete` | `TASKS.md` 对应项变成 `[x]` |
| WM-L1-04 | 今天晚上十一点新增日程，检查桌面助手验收 | `local_fast_path.link1.schedule_add` | `SCHEDULE.md` 写入日程 |
| WM-L1-05 | 查询今日日程 | `link_1_openclaw` | OpenClaw 使用 `SCHEDULE.md` 上下文回复刚才的日程 |
| WM-L1-06 | 十分钟后提醒我喝水 | `local_fast_path.link1.reminder_add` | `SCHEDULE.md` 和 `local_reminders.json` 都有记录 |
| WM-L1-07 | 查询提醒 | `local_fast_path.link1.reminder_query` | 回复包含喝水提醒 |
| WM-L1-08 | 取消喝水提醒 | `local_fast_path.link1.reminder_cancel` | `local_reminders.json` 对应项为 cancelled |
| WM-L3-01 | 停止 | `local_fast_path.link3.stop_motion` | 机器人收到 stop，随后 TTS 确认 |
| WM-L3-02 | 出来 | `local_fast_path.link3.move_out` | 机器人小幅出 Dock，随后 TTS 确认 |
| WM-L3-03 | 回到充电座 | `local_fast_path.link3.return_to_dock` | 机器人回 Dock，随后 TTS 确认 |
| WM-L3-04 | 转左边 | `local_fast_path.link3.turn_left` | 机器人左转，随后 TTS 确认 |
| WM-L3-05 | 转右边 | `local_fast_path.link3.turn_right` | 机器人右转，随后 TTS 确认 |
| WM-L3-06 | 开心一点 | `local_fast_path.link3.set_expression` | 表情变 happy，随后 TTS 确认 |
| WM-L3-07 | 带我呼吸 | `local_fast_path.link3.breathing_guide` | 机器人说完整呼吸引导 |
| WM-O01 | 帮我查一下北京天气 | `link_1_openclaw` | OpenClaw event 增加；本地 workspace 不写天气任务 |
| WM-O02 | 帮我记录一条笔记：桌面助手正在验收 | `link_1_openclaw` | 笔记/记忆由 OpenClaw/runtime tool 处理 |
| WM-O03 | 帮我把今天的工作安排整理成三步计划 | `link_1_openclaw` | 复杂规划由 OpenClaw 回复 |
| WM-M01 | 打开麦克风，说完这一整句以后再关闭麦克风 | local mic segment | `duration_ms` 覆盖完整开关窗口；`completed_mic_segment=true` |
| WM-V01 | 打开摄像头，对准人脸，保持正常表情十秒 | link2 visual idle | camera card OK；OpenFace fresh；不应强行关怀 |
| WM-V02 | 打开摄像头，做疲惫或难过表情，不要强制触发 VLM | link2 visual gate controlled | 真实摄像头帧更新；VLM 只在 gate 判断后触发 |

## 现场记录

每条人工验收至少记录这些信息：

```text
ID:
开始时间:
ASR 文本:
route:
reason:
tts_text:
executed_actions:
episode_state after 3s:
机器人实际表现:
是否通过:
备注:
```

## 停止条件

出现以下情况时先停总工作模式，不继续往下验收：

- `episode_state` 超过 10 秒卡在 `running`。
- ASR 文本为空，但音频文件明显有声音。
- 本地确定性用例进入 OpenClaw。
- TTS 有 `tts_text` 但机器人没有播放，也没有 `audio.playback_done` 或失败原因。
- 摄像头画面不更新，或视觉状态仍使用旧图片。
- 任意运动动作方向、距离或速度不符合预期。

## 结论口径

- 全部自动路由测试通过，但人工硬件未跑：只能称为“路由回归通过”。
- 麦克风、TTS、链路一/三全部通过，视觉未通过：可以称为“语音桌面助手可试用”。
- 麦克风、TTS、链路一/二/三、OpenClaw、失败恢复全部通过：才称为“总工作模式桌面助手 beta 可用”。
