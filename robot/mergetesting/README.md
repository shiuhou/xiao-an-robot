# Robot Merge Testing — DK-2500/base-station integration firmware

> **Boundary:** New DK-2500/base-station burns belong in this directory. `robot/firmware` is for robot-body bring-up and reusable modules; when integration needs a proven robot feature, copy/sync the minimal module from `robot/firmware` into `robot/mergetesting`.

独立 PlatformIO 工程，目标：**一条可观察、可回放、可验证的端到端闭环**。

```
ESP32-S3 → WebSocket(/control,/video,/audio) → DK-2500 → JSON 指令 → 表情/电机/喇叭
```

## 快速开始

1. 复制本地配置模板并填写 WiFi / M600 IP（`config.local.h` 已被 `.gitignore` 忽略）：

```powershell
copy src\config.local.example.h src\config.local.h
```

然后编辑 `src/config.local.h`：
   - `MERGETEST_WIFI_SSID` / `MERGETEST_WIFI_PASSWORD`
   - `MERGETEST_BASE_STATION_IP`（M600 / 基站局域网 IP）
2. 构建并烧录：

```powershell
cd robot\mergetesting
pio run -e mergetesting
pio run -e mergetesting -t upload
pio device monitor -b 115200
```

3. 基站侧启动 WebSocket 服务后，串口应看到：
   - `Control connected`
   - `Sent device.hello`
   - 每 2s `Heartbeat`

## 模块结构

完整 **firmware → mergetesting 提取对照** 见 [EXTRACTION_MAP.md](./EXTRACTION_MAP.md)。

```
src/
├── main.cpp              # thin Arduino entrypoint
├── app/                  # MergetestingApp runtime wiring
├── services/             # state/status/non-blocking motion/command routing
├── config.h              # WiFi、device_id、硬件开关
├── hardware_pins.h       # 电机/TFT/麦克风/喇叭引脚
├── protocol.h            # 消息 type 常量
├── ws_client.cpp/h       # /control + /video + /audio
├── display.cpp/h         # 门面：ST7735 或 face240
├── face240_display.cpp/h # 2.4" 九表情（来自 robot_face_9expr_merged_optimized）
├── motor_ctrl.cpp/h      # DRV8833（来自 firmware motor_ctrl）
├── speaker.cpp/h         # MAX98357A（来自 speaker_amp_test）
├── mic_stream.cpp/h      # INMP441 PCM（来自 voice_recognition_test）
├── camera_ov2640_config.h # OV2640 引脚 + 曝光（来自 motor_cam_wifi_manual）
├── cam_stream.cpp/h      # OV2640 JPEG → /video 1fps
└── debug_log.h
```

## PlatformIO 环境

| Env | 用途 |
|-----|------|
| `mergetesting_display_only` | Phase 1–2：128×160 + 电机 + 喇叭 + WS `/control` |
| `mergetesting_display_only_ota` | Phase 1-2 OTA upload target for `/control`; hardware H pending |
| `mergetesting_face240_only` | Phase 2：2.4" 九表情动画屏 |
| `mergetesting_cam_only` | Phase 3：相机 QVGA 1fps → `/video`，motor/speaker/mic 关闭 |
| `mergetesting_cam_only_ota` | `mergetesting_cam_only` 的 OTA upload target；2026-06-25 已完成无线烧录和落图验证 |
| `mergetesting_mic_only` | 麦克风 PCM → `/audio` |
| `mergetesting_base64_video` | 视频 base64 fallback |

## 硬件引脚（整合线束）

TFT 与 OV2640 默认使用 **整合引脚**（见 `hardware_pins.h` / `hardware/wiring/esp32_pinout.md`）：

- Motor：left GPIO1/GPIO2, right GPIO3/GPIO48
- TFT：GPIO14/21/42/43/44, BL tied to 3V3 (`TFT_BL=-1`)
- Camera：GOOUUU FPC 固定 DVP 引脚

同一条整合线束可同时接相机与 2.4" 屏。`mergetesting_face240_only` 已启用 ST7789 + 整合 SPI 引脚。

## 四阶段验收

### Phase 1 — 连接

- 上电 → WiFi → `ws://<基站IP>:8765/control`
- 发 `device.hello` + 2s `device.heartbeat`
- 断线后 capped exponential reconnect；重连成功后重新发送 `device.hello`
- 基站日志：`Robot connected` / `device.hello` / heartbeat

Safe Phase 1-2 upload flow:

```powershell
cd robot\mergetesting
pio run -e mergetesting_display_only
pio run -e mergetesting_display_only -t upload --upload-port COMxx
pio device monitor -b 115200
```

If an OTA-enabled firmware is already running on the board:

```powershell
pio run -e mergetesting_display_only_ota -t upload --upload-port <board-ip-or-hostname>
```

Do not use `ota_bootstrap_wifi` for mergetesting functional firmware; it only refreshes the bootstrap image.

### Phase 2 — 基站控车

```powershell
python tools/send_robot_command.py expression caring
python tools/send_robot_command.py expression caring --duration-ms 3000
python tools/send_robot_command.py motion move_out_of_dock
python tools/send_robot_command.py local care_01
python tools/send_robot_command.py --device-id xiaoan_robot_01 expression happy
```

每条命令机器人回 `command.ack`。motion ack/completed 带同一个 `action_id`；新 motion 或 `motion stop` 会打断当前动作并回 `motion.completed` / `result: interrupted`。未知 expression、未知 motion action、未知 local sound 只回 error/日志，不崩溃、不假成功。

### Phase 3 — 视频 1fps

烧录 **`mergetesting_cam_only`**（相机与屏幕引脚冲突，勿用默认 `mergetesting` 同时开相机+TFT）：

```powershell
cd robot\mergetesting
pio run -e mergetesting_cam_only -t upload
pio device monitor -b 115200
```

若已经有 OTA-enabled camera firmware 在板上运行，可尝试：

```powershell
pio run -e mergetesting_cam_only_ota -t upload --upload-port <board-ip-or-hostname>
```

注意：OTA 只能上传当前 env 对应的 firmware。不要用 `ota_bootstrap_wifi` 上传 mergetesting 功能固件。

- 当前 camera-only smoke target 默认 **320×240 QVGA**、`MERGETEST_VIDEO_INTERVAL_MS=1000`（1 fps）
- `mergetesting_cam_only` / `mergetesting_cam_only_ota` 会关闭 motor、speaker、mic，减少相机 init 阶段 watchdog 风险
- `/control` 先发 `video.frame_meta`
- `/video` 发 8 字节头 + JPEG binary
- binary 失败时自动 fallback 到 `video.frame` base64

### Phase 4 — Mock ASR

串口输入：

```
mock:帮我定一个二十分鐘的鬧鐘
```

机器人发 `asr.transcript.mock` 到 `/control`。

## 串口本地测试（无基站）

```
expr caring
motion move_out_of_dock
sound care_01
mock:帮我定一个二十分鐘的鬧鐘
```

## 发给基站同学

详见 [CAPABILITIES.md](./CAPABILITIES.md)。

## 与主固件关系

- 本目录为 **联调专用**，不修改 `robot/firmware/src/main.cpp`
- 协议对齐 `docs/protocol.md`，并扩展 `command.ack`、`video.frame_meta`、`asr.transcript.mock`
- 入站 JSON 同时支持 **envelope**（`payload` 子对象）与 **flat**（字段在根）
