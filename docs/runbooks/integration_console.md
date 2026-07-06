# DK-2500 Integration Console Runbook

本 runbook 用于硬件联调阶段打开一个本地页面检查机器人、基站、感知、音频、视频、ASR、OpenClaw/Agent、场景脚本和日志导出。

## 1. 启动顺序

从仓库根目录启动：

```powershell
python -m base_station.ws_server.server
python -m base_station.integration_console.console_server --host 0.0.0.0 --port 8090 --ws-url ws://127.0.0.1:8765/agent --runtime-dir runtime
```

浏览器打开：

```text
http://<DK2500-IP>:8090/console
```

注意：浏览器不要访问 `http://0.0.0.0:8090/console`。`0.0.0.0` 只表示监听所有网卡，访问时用 `127.0.0.1`、`localhost` 或 DK-2500 的局域网 IP。

## 2. 机器人接入前检查

1. 打开 `/console`。
2. 顶部 `Console` 应为 online。
3. `Robot` 应显示 offline，这是未接机器人时的正常状态。
4. `OpenClaw` 如果没有启动 `xiaoan-runtime` gateway，会显示 offline。
5. `Camera` 在没有 `/video` 帧时显示 none。
6. `Audio` 在没有 `/audio` PCM 时显示 none。
7. 点击“导出日志”，应生成 `runtime/integration_console/export_*.json`。

## 3. 机器人接入后 smoke test

机器人 firmware 连接基站后，`base_station.ws_server.server` 会写：

```text
runtime/ws_state.json
```

控制台检查：

1. `Robot` 变为 online。
2. `selected_device_id` 有值，默认通常是 `xiaoan_robot_01`。
3. heartbeat age 小于 30 秒。
4. 先发 `idle` 表情，再发 `happy` 表情。
5. 只在确认周围安全后点击 `出 Dock safe` 或 `回 Dock safe`。
6. 观察 `Ack`、`motion.completed` 和机器人串口日志是否匹配。

## 4. 相机检查

1. 切到“相机 / 视觉”。
2. 预览图应显示 `runtime/latest.jpg`。
3. age 应持续刷新；超过 3 秒会出现黄色警告。
4. 如果没有图像，确认机器人 `/video` 通道已连接，且 `base_station.ws_server.server` 有 video frame 日志。
5. 可运行 `vision-preflight`，它是软件检查，不等于真实硬件视觉闭环验证。

### 4.1 Route A 视觉链路页面

启动 `/video` 视觉运行时：

```powershell
python tools/ops/run_ws_video_runtime.py --host 0.0.0.0 --port 8765 --no-agent --model-backend openface_ov --vlm-backend openvino_qwen_vl --vlm-model-path base_station/models/Qwen2.5-VL-3B-OV-int4 --visual-trace-fps 1
```

相机页面应分别显示：

- 最新 OpenFace 分析快照、人脸框、98 点、眼睛和嘴部轮廓。
- `frame_id`、EAR、MAR、emotion、fatigue 和 observation quality。
- Gate 的 Force、High fatigue、Negative 和 Negative window 状态。
- Gate 正式 `reason`，以及 VLM 的 request、trigger frame、耗时和结果。
- VLM 运行期间保留的触发帧；它可能与持续更新的当前 OpenFace 帧不同。

`LIVE` 表示状态文件在 3 秒内更新；超过 3 秒显示 `STALE`。`STALE` 不等于历史结果错误，只表示视觉 runtime 当前没有继续发布。

### 4.2 不连接机器人的模拟 `/video` 验证

终端一启动模型无关 runtime：

```powershell
python tools/ops/run_ws_video_runtime.py --host 127.0.0.1 --port 8765 --no-agent --model-backend mock --vlm-backend fake --force-vlm --visual-trace-fps 1
```

终端二发送三帧：

```powershell
python tools/probes/send_test_video_frame.py --url ws://127.0.0.1:8765/video --frames 3 --fps 1 --width 320 --height 240
```

该验证覆盖 JPEG 包、`/video`、解码队列、CV sample、Gate、fake VLM、快照发布和控制台 API。默认生成图没有真实人脸，因此不会验证 OpenFace landmarks。需要本地人脸图时，将图片放在仓库外，例如 `C:\tmp\visual-trace-face.jpg`，然后运行：

```powershell
python tools/probes/send_test_video_frame.py --url ws://127.0.0.1:8765/video --frames 3 --fps 1 --image-path C:\tmp\visual-trace-face.jpg
```

### 4.3 真实机器人 `/video` 最终验收

当前网络不能连接机器人时，保留本节为待执行人工门槛，不得用模拟包标记真实硬件通过。

1. 将 DK-2500 或开发电脑和机器人连接到同一个非隔离局域网。手机热点或访客 Wi-Fi 必须关闭 client/AP isolation。
2. 在基站 PowerShell 运行 `ipconfig`，找到机器人可访问网卡的 IPv4，例如 `192.168.137.1`。
3. 将机器人固件的 Base Station host 配置为该 IPv4，控制端口使用 `8765`。机器人最终连接的是 `ws://<base-ip>:8765/control`、`/video` 和需要的其他通道。
4. Windows 防火墙允许当前 Python 解释器或入站 TCP `8765`。只允许当前局域网配置文件，不要暴露到公网。
5. 先启动本节 4.1 的 `run_ws_video_runtime.py`，再启动机器人。
6. 观察服务日志中 `/control` 的 `device.hello` 和 `/video` frame；检查 `runtime/ws_state.json` 的机器人 ID 和 heartbeat。
7. 启动控制台：

```powershell
python -m base_station.integration_console.console_server --host 0.0.0.0 --port 8090 --ws-url ws://127.0.0.1:8765/agent --runtime-dir runtime
```

8. 浏览器访问 `http://<base-ip>:8090/console`，进入“相机”。确认 freshness 为 `LIVE`，`frame_id` 持续变化，landmarks 与脸部对齐。
9. 正常状态下 Gate 应为 `NORMAL`。出现真实规则触发后，核对 Gate reason、VLM request ID、trigger frame ID、VLM 完成状态和 fusion。
10. 验收证据应明确记录：机器人 IP、基站 IP、运行命令、三个 frame ID、一次 Gate 结果和一次 VLM 结果。

连接失败时按顺序检查：机器人串口目标 IP、双方子网、Wi-Fi client isolation、Windows 防火墙、TCP 8765 是否监听、`device.hello`、`/video` 日志和 `runtime/ws_state.json`。不要先修改 OpenFace 或 VLM 参数，因为网络层尚未证明可用。

## 5. 音频检查

1. 切到“音频 / ASR”。
2. 查看 `latest_audio.pcm` 大小和更新时间。
3. 查看 `audio_stats.json` 中 RMS、peak、DC、clipping。
4. robot `/audio` 当前主要用于 diagnostics/fallback；主语音链路仍是 DK-2500/base-station microphone。
5. 如果 `audio_stats` 不存在，先确认机器人 `/audio` 固件 env 和 WebSocket `/audio` 已连接。

## 6. OpenClaw 检查

默认检查：

```text
ws://127.0.0.1:18789
```

如需覆盖：

```powershell
python -m base_station.integration_console.console_server --openclaw-url ws://127.0.0.1:18789
```

`decision-only` 工具只验证 OpenClaw 决策路径，不发机器人动作。`send to robot` 开关默认关闭，避免把 Agent 决策误转成硬件动作。

## 7. 场景脚本

| 场景 | 行为 |
| --- | --- |
| `direct-smoke` | `idle` expression -> `happy` expression -> `success_ding` |
| `care-loop-safe` | `caring` expression -> safe `move_out_of_dock` -> 等 `motion.completed` 或 timeout -> `care_01` -> `idle` |
| `return-dock` | safe `move_back_to_dock` -> `idle` |
| `stop-all` | `motion.stop`，不需要确认 |
| `camera-check` | 只检查 `latest.jpg` 是否更新，不发动作 |
| `audio-check` | 只检查 `audio_stats/latest_audio`，不发动作 |

所有场景逐步执行，每步写入：

```text
runtime/integration_console/events.jsonl
```

## 8. 日志导出路径

联调操作日志：

```text
runtime/integration_console/events.jsonl
```

导出文件：

```text
runtime/integration_console/export_<timestamp>.json
```

`runtime/` 已在 `.gitignore`，这些文件不应提交。

## 8.1 Visual Trace 精确清理

先停止 `run_ws_video_runtime.py` 和 Integration Console，避免文件仍被写入。只检查：

```powershell
Get-ChildItem -Force runtime/integration_console/visual
```

只删除本功能拥有的文件：

```text
latest_annotated.jpg
latest_state.json
vlm_trigger.jpg
vlm_state.json
latest_annotated.jpg.tmp
latest_state.json.tmp
vlm_trigger.jpg.tmp
vlm_state.json.tmp
```

目录清空后才删除 `runtime/integration_console/visual/`。不得删除 `runtime/integration_console/events.jsonl`、export 文件、`runtime/latest.jpg`、音频文件、数据库或其他 runtime 子目录。最后运行：

```powershell
git status --short
```

确认没有临时图片、JSON、trace、数据库或一次性脚本进入工作区。

## 9. 常见问题

### robot offline

- 确认机器人烧录的是 `robot/mergetesting` 的联调 firmware。
- 确认基站先运行 `python -m base_station.ws_server.server`。
- 确认机器人和 DK-2500 在同一局域网。
- 看 `runtime/ws_state.json` 是否存在、heartbeat 是否超过 30 秒。

### latest.jpg 不更新

- 确认机器人 `/video` 已连接。
- 确认当前 firmware env 启用了 camera。
- 确认 `runtime/latest.jpg` 的 mtime 是否变化。
- 区分 WebSocket `/video` 和旧的 ESP32 AP HTTP MJPEG，它们不是同一路。

### audio_stats 不存在

- 确认机器人 `/audio` 通道连接。
- 确认 `runtime/latest_audio.pcm` 是否有数据。
- 先用 `/audio` 作为诊断链路，不要把它当作唯一主语音输入。

### OpenClaw gateway offline

- 确认 OpenClaw `xiaoan-runtime` gateway 在 `127.0.0.1:18789` 监听。
- 如果端口不同，用 `--openclaw-url` 覆盖。
- `decision-only` 失败不代表机器人 `/control` 失败。

### speaker not ready

- 本地音效 `care_01`、`success_ding` 是优先 smoke。
- TTS 是实验功能，不要紧接 local sound。
- 控制台后端有 cooldown，但真实硬件仍需看 `audio.playback_done` 和串口日志。

### motion 没有 completed

- 立即点击 `STOP ALL / 急停`。
- 看 `runtime/ws_state.json` 的 `last_motion_completed`。
- 看机器人串口是否有 motion ack/completed。
- 降低动作距离和超时，确认电池和地面条件。

### browser 无法访问 0.0.0.0 监听服务

`0.0.0.0` 是监听地址，不是浏览器目标地址。浏览器访问：

```text
http://127.0.0.1:8090/console
http://<DK2500-IP>:8090/console
```
