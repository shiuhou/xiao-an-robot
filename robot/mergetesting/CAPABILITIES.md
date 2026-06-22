# Robot capabilities v0.1 — 联调对接表

> 烧录 `robot/mergetesting` 固件后，请把本表发给 DK-2500 同学。

## 身份

| 项 | 值 |
|----|-----|
| device_id | `xiaoan_robot_01` |
| role | `robot` |
| firmware | `robot-fw-0.1` |
| WiFi 模式 | STA（连局域网，非 SoftAP） |
| 基站地址 | `ws://<DK2500_IP>:8765` |

**烧录前在 `src/config.h` 填写实际 WiFi SSID/密码与基站 IP。**

## WebSocket 通道

| 通道 | 路径 | 方向 | 说明 |
|------|------|------|------|
| 控制 | `/control` | 双向 JSON | hello、heartbeat、命令、ack |
| 视频 | `/video` | 机器人→基站 | 8B 头 + JPEG binary |
| 音频 | `/audio` | 机器人→基站 | 预留 PCM（联调第一天可不接） |

## /control — 机器人 → 基站

| type | 说明 |
|------|------|
| `device.hello` | 上线，`payload.device_id` / `capabilities[]` / `firmware` |
| `device.heartbeat` | 每 **2s**，含 `uptime_ms`、`battery`、`dock`、`busy` |
| `device.status` | 表情/动作/相机状态变更时 |
| `command.ack` | **每条下行命令**执行后回执 |
| `motion.completed` | 动作结束 |
| `error.report` | 失败时，`where` + `message` |
| `video.frame_meta` | 每帧 JPEG 前发 metadata |
| `video.frame` | base64 fallback（`format: jpeg_base64`） |
| `asr.transcript.mock` | 串口 `mock:文本` 触发，无真 ASR 时用 |

## /control — 基站 → 机器人

| type | 字段 | 机器人行为 |
|------|------|------------|
| `display.expression` | `expression` | TFT 切换表情 |
| `motion.execute` | `action` 或 `motion` | 电机执行（无距离则前进 ~1.5s） |
| `audio.play_local` | `sound` | 本地 I2S 音调 |
| `audio.play_tts` | `text` / `text_preview` / `audio_url` | 暂用 mock 音调（不拉 URL） |
| `system.welcome` | `config.*` | 可调 heartbeat 间隔 |
| `system.shutdown` | — | ESP 重启 |

### command.ack 格式

成功：

```json
{
  "type": "command.ack",
  "payload": {
    "device_id": "xiaoan_robot_01",
    "command_type": "motion.execute",
    "status": "ok"
  }
}
```

失败：

```json
{
  "type": "error.report",
  "payload": {
    "where": "motion.execute",
    "message": "motor busy or previous motion running"
  }
}
```

## /video — 二进制帧

每帧：

```
+--------+--------+----------------+
| 4B len | 4B ts  | JPEG raw bytes |  (len/ts = uint32 BE)
+--------+--------+----------------+
```

- 分辨率：**320×240** (QVGA)
- 频率：**1 fps**（联调）
- 每帧前 `/control` 会发 `video.frame_meta`

## /audio — 预留

- 格式：`pcm_s16le`, 16kHz, mono
- 联调第一天：**可不接**
- Fallback：串口 mock → `asr.transcript.mock` on `/control`

## 支持的 expression

`neutral`（=idle）、`caring`、`happy`、`tired`、`listening`（映射 thinking）、`sad`、`thinking`、`speaking`、`surprised`、`sleeping`、`error`（映射 surprised）

## 支持的 motion

`move_out_of_dock`、`move_back_to_dock`、`turn`、`stop`、`nod_head` / `wiggle_ears`（无舵机时用短脉冲代替）

## 支持的 audio.play_local

| sound | 用途 |
|-------|------|
| `care_01` | 关怀提示音 |
| `alarm_01` | 闹钟/提醒 |
| `wake_01` | 唤醒确认 |
| `wakeup_chime` / `error_beep` / `success_ding` | 协议别名，映射到上述音 |

## 测试命令（基站侧）

```powershell
# 启动基站
python -m base_station.ws_server.server

# Agent 转发（默认连第一个在线机器人）
python tools/send_robot_command.py expression --expression caring
python tools/send_robot_command.py motion --action move_out_of_dock
python tools/send_robot_command.py tts --text "你已经工作很久了，休息一下吧。"
python tools/send_robot_command.py --device-id xiaoan_robot_01 expression --expression happy
```

## 成功标准（建议）

1. **Phase 1**：连续 5 分钟 heartbeat，掉线自动重连
2. **Phase 2**：每条命令有 `command.ack`
3. **Phase 3**：基站收到 JPEG 并保存 `latest.jpg`
4. **Phase 4**：mock 文本进入 OpenClaw 决策链
