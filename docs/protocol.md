# WebSocket 通信协议 v0.1

> **状态**：草案，待团队确认后冻结
> **维护者**：张子尧（统筹）
> **最后更新**：2026-04-27

---

## 0. 文档目的

本文件定义 **机器人端（ESP32-S3）** 与 **基站端（Intel DK-2500）** 之间通过 WebSocket 传递的所有消息格式。

**这是项目的"契约"**，任何修改必须三人达成共识并更新版本号。三个开发者基于此独立开发各自模块，无需互相等待。

---

## 1. 总体架构

```
┌─────────────────┐                          ┌──────────────────┐
│  ESP32-S3       │  ── audio/video stream ──▶  Intel DK-2500   │
│  (机器人本体)    │                          │  (边缘基站)       │
│                 │  ◀── control commands  ── │                  │
└─────────────────┘                          └──────────────────┘
        │                                              │
   传感器数据采集                                      AI 推理
   动作执行                                            决策
   表情显示                                            LLM 调用
```

### 1.1 物理连接

- **传输层**：WiFi 2.4GHz，同一局域网
- **协议**：WebSocket over TCP
- **基站地址**：`ws://192.168.x.x:8765`（基站 IP 由 mDNS 广播或写入 ESP32 配置）
- **机器人作为 Client**，基站作为 Server

### 1.2 通道划分

为避免大数据流（视频）阻塞控制指令，使用 **三个独立 WebSocket 连接**：

| 通道 | 端点路径 | 方向 | 数据类型 | 频率 |
|------|---------|------|----------|------|
| 控制通道 | `/control` | 双向 | JSON 文本 | 事件触发 |
| 音频通道 | `/audio` | 机器人 → 基站 | 二进制 PCM | 持续推流 |
| 视频通道 | `/video` | 机器人 → 基站 | 二进制 JPEG 帧 | 5 秒 / 帧 |

**为什么不合并到一个连接**：视频帧大（每帧 ~30KB），如果和控制指令混在一起，TFT 表情切换的指令会被卡住几百毫秒。三连接分开后，控制指令永远是低延迟。

---

## 2. 通用消息格式（控制通道）

所有 `/control` 通道的消息都是 UTF-8 编码的 JSON，结构如下：

```json
{
  "type": "消息类型",
  "ts": 1714190400000,
  "seq": 12345,
  "payload": { ... }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | string | ✅ | 消息类型，见第 3-4 节 |
| `ts` | int64 | ✅ | 发送时刻的 Unix 毫秒时间戳 |
| `seq` | int32 | ✅ | 自增序号，发送方各自维护，从 1 开始 |
| `payload` | object | ✅ | 消息内容，结构因 type 而异 |

**为什么需要 seq**：方便排查"指令丢了 / 顺序乱了"的问题。出 bug 时第一件事就是看日志里的 seq 是不是连续的。

---

## 3. 机器人 → 基站消息

### 3.1 `device.hello` —— 上线握手

机器人启动后第一件事，向基站报到。

```json
{
  "type": "device.hello",
  "ts": 1714190400000,
  "seq": 1,
  "payload": {
    "device_id": "xiaoan-robot-01",
    "fw_version": "0.1.0",
    "battery": 87,
    "ip": "192.168.1.123"
  }
}
```

基站收到后必须回 `system.welcome`（见 4.1）。

### 3.2 `device.heartbeat` —— 心跳

每 10 秒发一次，让基站知道机器人还活着。

```json
{
  "type": "device.heartbeat",
  "ts": 1714190410000,
  "seq": 2,
  "payload": {
    "battery": 87,
    "uptime_sec": 120,
    "wifi_rssi": -52
  }
}
```

如果基站连续 30 秒没收到心跳，认为机器人掉线，停止下发指令。

### 3.3 `sensor.button` —— 物理按键事件

机器人头顶或身体上的物理按键（如有）。

```json
{
  "type": "sensor.button",
  "ts": 1714190420000,
  "seq": 3,
  "payload": {
    "button": "head",
    "action": "click"
  }
}
```

| 字段 | 取值 |
|------|------|
| `button` | `"head"` / `"chest"` / `"back"` |
| `action` | `"click"` / `"long_press"` / `"double_click"` |

### 3.4 `sensor.dock_status` —— 充电桩状态

机器人在 dock 上 / 离开 dock 时上报。

```json
{
  "type": "sensor.dock_status",
  "ts": 1714190430000,
  "seq": 4,
  "payload": {
    "docked": true,
    "charging": true
  }
}
```

### 3.5 `motion.completed` —— 动作执行完成回报

机器人执行完一个动作后回报状态。**这个非常重要**——基站需要知道动作完成了才能下发下一个动作，否则会指令打架。

```json
{
  "type": "motion.completed",
  "ts": 1714190435000,
  "seq": 5,
  "payload": {
    "action_id": "act_abc123",
    "result": "success",
    "final_state": {
      "position": "out_of_dock",
      "facing_user": true
    }
  }
}
```

| 字段 | 取值 |
|------|------|
| `action_id` | 对应基站下发指令时的 `action_id`（见 4.3） |
| `result` | `"success"` / `"failed"` / `"interrupted"` |
| `final_state.position` | `"in_dock"` / `"out_of_dock"` / `"moving"` |

### 3.6 `error.report` —— 错误上报

机器人本地出错时上报。

```json
{
  "type": "error.report",
  "ts": 1714190440000,
  "seq": 6,
  "payload": {
    "code": "MOTOR_STALL",
    "severity": "warning",
    "message": "Left motor stalled, retry suggested"
  }
}
```

| 字段 | 取值 |
|------|------|
| `severity` | `"info"` / `"warning"` / `"error"` / `"critical"` |
| `code` | 错误码，详见附录 A |

---

## 4. 基站 → 机器人消息

### 4.1 `system.welcome` —— 握手回应

```json
{
  "type": "system.welcome",
  "ts": 1714190400100,
  "seq": 1,
  "payload": {
    "session_id": "sess_xyz789",
    "server_time": 1714190400100,
    "config": {
      "video_fps": 0.2,
      "audio_sample_rate": 16000,
      "heartbeat_interval_sec": 10
    }
  }
}
```

机器人收到后用 `config` 字段调整自己的采集参数（视频帧率、音频采样率等）。**这是关键设计**：参数都从基站下发，避免机器人端写死。

### 4.2 `display.expression` —— 切换表情

```json
{
  "type": "display.expression",
  "ts": 1714190450000,
  "seq": 2,
  "payload": {
    "expression": "caring",
    "duration_ms": 3000,
    "loop": false
  }
}
```

| 字段 | 取值 |
|------|------|
| `expression` | `"happy"` / `"sad"` / `"caring"` / `"tired"` / `"thinking"` / `"speaking"` / `"idle"` / `"surprised"` / `"sleeping"` |
| `duration_ms` | 持续时间（毫秒），`0` 表示永久 |
| `loop` | 是否循环播放（适用于带动画的表情） |

机器人侧需要把这 9 种表情提前烧录到 flash，按 `expression` 字段查表播放。

### 4.3 `motion.execute` —— 执行动作

```json
{
  "type": "motion.execute",
  "ts": 1714190460000,
  "seq": 3,
  "payload": {
    "action_id": "act_abc123",
    "action": "move_out_of_dock",
    "params": {
      "speed": 0.5,
      "distance_cm": 8
    },
    "timeout_ms": 5000
  }
}
```

**支持的 action 列表（v0.1）**：

| action | 说明 | params |
|--------|------|--------|
| `move_out_of_dock` | 驶出充电桩 | `speed` (0.0-1.0), `distance_cm` |
| `move_back_to_dock` | 返回充电桩 | `speed` (0.0-1.0) |
| `turn` | 原地转向 | `angle_deg` (-180 到 180) |
| `nod_head` | 点头（舵机） | `times` (1-3) |
| `tilt_head` | 歪头 | `direction` (`"left"` / `"right"`), `angle_deg` |
| `wiggle_ears` | 摆耳朵 | `times` (1-5) |
| `stop` | 立即停止所有动作 | 无 |

**`action_id` 由基站生成（UUID 短码）**，机器人执行完后用同一个 `action_id` 回 `motion.completed`。

### 4.4 `audio.play_tts` —— 播放语音

```json
{
  "type": "audio.play_tts",
  "ts": 1714190470000,
  "seq": 4,
  "payload": {
    "audio_id": "tts_def456",
    "audio_url": "http://192.168.1.100:8080/tts/tts_def456.mp3",
    "duration_ms": 2400,
    "text_preview": "你已经工作两小时了,休息一下吧"
  }
}
```

**设计要点**：基站把 TTS 合成为 mp3 后,通过 HTTP 提供下载链接,机器人去拉取播放。**不直接通过 WebSocket 传音频**——音频文件几百 KB，走 WebSocket 会阻塞控制通道。

`text_preview` 仅用于日志和调试，机器人不需要显示。

### 4.5 `audio.play_local` —— 播放本地预存音效

```json
{
  "type": "audio.play_local",
  "ts": 1714190480000,
  "seq": 5,
  "payload": {
    "sound": "wakeup_chime",
    "volume": 0.7
  }
}
```

| sound | 用途 |
|-------|------|
| `wakeup_chime` | 唤醒确认音 |
| `error_beep` | 错误提示 |
| `success_ding` | 任务完成 |
| `low_battery` | 低电量提示 |

预存音效烧录在 ESP32 flash 上，比走网络快 100ms+，用于即时反馈。

### 4.6 `config.update` —— 动态修改配置

```json
{
  "type": "config.update",
  "ts": 1714190490000,
  "seq": 6,
  "payload": {
    "video_fps": 0.5,
    "audio_sample_rate": 16000
  }
}
```

调试时方便。例如想临时把视频帧率从 0.2 fps 提到 1 fps 看效果。

### 4.7 `system.shutdown` —— 关机/重启指令

```json
{
  "type": "system.shutdown",
  "ts": 1714190500000,
  "seq": 7,
  "payload": {
    "mode": "restart",
    "reason": "firmware_update"
  }
}
```

| mode | 说明 |
|------|------|
| `"restart"` | 软重启（ESP.restart()） |
| `"sleep"` | 进入低功耗模式 |
| `"poweroff"` | 关机（需要硬件支持） |

---

## 5. 二进制流协议

### 5.1 音频通道 `/audio`

机器人 → 基站，**单向**推流。

**格式**：原始 PCM，16kHz 采样率，16-bit 单声道，小端序

**分帧**：每 320 字节为一帧（即 10ms 音频），连续发送

**为什么不发 WAV/Opus**：ESP32-S3 算力有限，编码会占 CPU。基站端拿到 PCM 直接喂给 VAD 和 ASR 即可。

**起停控制**：

机器人持续推流（VAD 由基站做）。如果基站想暂停推流（比如机器人在睡眠状态），通过 `/control` 发：

```json
{
  "type": "audio.stream_control",
  "payload": { "enable": false }
}
```

### 5.2 视频通道 `/video`

机器人 → 基站，**单向**推流。

**格式**：JPEG 编码（OV2640 硬件 JPEG），640×480 分辨率

**帧率**：默认 0.2 fps（每 5 秒一帧），由 `system.welcome` 的 `config.video_fps` 控制

**消息格式**：每帧前加 8 字节头：

```
+--------+--------+----------------+
| 4B len | 4B ts  | JPEG raw bytes |
+--------+--------+----------------+
```

- `len`: JPEG 数据字节数（uint32 大端）
- `ts`: 帧采集时刻的 Unix 秒时间戳（uint32 大端）

**为什么不用 RTSP**：ESP32 的 RTSP 库稳定性参差不齐，0.2 fps 这种低帧率没必要走流媒体协议。直接 WebSocket 二进制最简单可靠。

---

## 6. 错误处理

### 6.1 连接断开

- 机器人侧：检测到 WebSocket 断开后，**指数退避重连**（1s, 2s, 4s, 8s, 16s, 30s 上限）
- 基站侧：30s 内未收到心跳判定为掉线，清理该机器人的会话状态
- 重连成功后，机器人**必须重新发 `device.hello`**

### 6.2 JSON 解析失败

- 收到无法解析的消息，**忽略**，不报错（避免无限错误循环）
- 在本地日志记录原始数据用于排查

### 6.3 未知 type

- 收到不认识的 `type`，**忽略并记录日志**
- 这样老版本固件遇到新版本协议时不会崩溃

### 6.4 动作冲突

如果基站连续下发多个 `motion.execute` 而前一个还在执行：
- 机器人 **取消前一个动作**，回 `motion.completed` 报 `result: "interrupted"`
- 立即开始执行新动作

例外：`stop` 动作总是立即执行，不需要等待。

---

## 7. 版本控制

### 7.1 协议版本号

`fw_version` 和 `system.welcome` 的 `protocol_version` 使用 SemVer：

- **major.minor.patch**
- major 变更：破坏性变更，双方必须同时升级
- minor 变更：新增字段或新增 type，向后兼容
- patch 变更：文档修订，无代码改动

### 7.2 当前版本

- 协议版本：**v0.1.0**（草案）
- 计划在第一次完整联调后冻结为 **v1.0.0**

### 7.3 变更流程

1. 任何字段或 type 变更必须先在飞书任务看板创建一条任务
2. 修改本文件并提 PR
3. 三人 review 通过后合并
4. 更新 `protocol.h`（C++）和 `protocol.py`（Python）的常量定义

---

## 8. 实现清单（开发分工）

### 机器人端（施宇灏）

- [ ] 实现 WebSocket Client（推荐 ArduinoWebsockets 库）
- [ ] 实现 JSON 序列化/反序列化（ArduinoJson 库）
- [ ] 实现指数退避重连
- [ ] 实现心跳定时器
- [ ] 实现 `protocol.h`，定义所有 type 常量
- [ ] 实现 9 种表情资源烧录
- [ ] 实现 4 种本地音效烧录
- [ ] 实现 7 种 motion action 的执行函数
- [ ] 实现音频 PCM 采集与推流
- [ ] 实现视频 JPEG 抓帧与推流

### 基站端（郑斯悦 + 张子尧）

- [ ] 实现 WebSocket Server（推荐 `websockets` Python 库）
- [ ] 实现三通道路由（`/control` `/audio` `/video`）
- [ ] 实现机器人会话管理（device_id → session 映射）
- [ ] 实现心跳超时检测
- [ ] 实现 `protocol.py`，定义所有消息 dataclass
- [ ] 实现 TTS 合成 + HTTP 文件服务
- [ ] 实现指令下发的统一接口（供 Agent 调用）

---

## 附录 A：错误码列表

| code | 严重等级 | 说明 |
|------|---------|------|
| `MOTOR_STALL` | warning | 电机堵转 |
| `MOTOR_LIMIT` | info | 触发限位开关 |
| `BATTERY_LOW` | warning | 电量低于 20% |
| `BATTERY_CRITICAL` | error | 电量低于 5% |
| `WIFI_WEAK` | warning | RSSI < -75 dBm |
| `CAM_INIT_FAIL` | error | 摄像头初始化失败 |
| `MIC_INIT_FAIL` | error | 麦克风初始化失败 |
| `OTA_FAIL` | error | 固件升级失败 |

---

## 附录 B：完整对话示例

> 场景：用户疲劳，机器人主动关怀

```
[T+0]    机器人 → 基站 (/audio):  推送音频流（持续）
[T+0]    机器人 → 基站 (/video):  推送视频帧（每 5s）
[T+30s]  基站 NPU 检测到 fatigue=0.85，超阈值
[T+30s]  基站 Agent 决定主动介入

[T+30s]  基站 → 机器人 (/control):
         { "type": "display.expression",
           "payload": { "expression": "caring" } }

[T+30s]  基站 → 机器人 (/control):
         { "type": "motion.execute",
           "payload": { "action_id": "act_001",
                        "action": "move_out_of_dock",
                        "params": { "speed": 0.5, "distance_cm": 8 } } }

[T+33s]  机器人 → 基站 (/control):
         { "type": "motion.completed",
           "payload": { "action_id": "act_001",
                        "result": "success" } }

[T+33s]  基站 调用 LLM 生成关怀文本
[T+34s]  基站 调用 TTS 合成音频，存为 tts_001.mp3

[T+34s]  基站 → 机器人 (/control):
         { "type": "audio.play_tts",
           "payload": { "audio_id": "tts_001",
                        "audio_url": "http://...mp3",
                        "text_preview": "你已经工作两小时了,休息一下吧" } }

[T+34s]  机器人 HTTP GET 该 URL，本地播放
[T+37s]  播放完毕

[T+60s]  基站 → 机器人 (/control):
         { "type": "motion.execute",
           "payload": { "action": "move_back_to_dock" } }
```

---

## 附录 C：FAQ

**Q: 为什么不用 MQTT？**
A: MQTT 适合大量设备的 1-N 场景。我们这里是 1-1，WebSocket 更轻量直接。

**Q: 视频用 JPEG 而不是 H.264？**
A: 0.2 fps 不需要视频压缩。每帧独立 JPEG 反而方便 OpenVINO 直接读取。

**Q: 为什么音频用 PCM 不用 Opus？**
A: ESP32-S3 编码 Opus 会占用 60%+ CPU，留给摄像头和电机控制的算力不够。基站算力充裕，多接收点字节数无所谓。

**Q: 三个 WebSocket 连接太多了，能合并吗？**
A: 可以，但风险大。视频帧 30KB 一发，会让控制指令排队几百毫秒，影响表情和动作的实时性。三连接是工程权衡的最优解。

**Q: 协议变更怎么保持兼容？**
A: 永远不要"重新定义"已有字段的含义。要变就加新字段。删除字段必须升 major 版本号。
