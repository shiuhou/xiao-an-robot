# 固件源码注册表 — `robot/firmware/src/`

> Boundary: `robot/firmware` is for robot-body feature bring-up and reusable modules. DK-2500/base-station integration firmware lives in `robot/mergetesting`; integration code may copy/sync proven firmware modules, but should not make `robot/firmware` the default demo path.

> 每个文件：**角色 | PlatformIO env | 实现状态 | 关键符号 | 最后验证**

## 集成模块（`esp32-s3-devkitc-1` 包含）

| 文件 | 角色 | 状态 | 关键 API / 逻辑 |
|------|------|------|-----------------|
| `main.cpp` | 主入口：WiFi → WS → 命令分发 | ✅ control | `onControlMessage()`, `connectWiFi()`, `setup/loop` |
| `ws_client.cpp/h` | `/control` WS 客户端 | ✅ | `begin()`, `sendHello/Heartbeat/Status`, 指数退避重连 |
| `protocol.h` | 消息 type 常量 | ✅ | `MsgType`, `Expression`, `MotionAction`, `buildMsg()` |
| `motor_ctrl.cpp/h` | DRV8833 差速 | ✅ | `execute()`, `moveForward()`, `turn()`, GPIO1/2/3/48 |
| `display.cpp/h` | 128×160 ST7735 矢量表情 | ✅ | `display_emotion()`, 9 种协议表情 |
| `cam_stream.cpp/h` | OV2640 初始化 + 定时抓帧日志 | 🟡 | `begin()`, `captureLoop()` — **无 WS 推流** |
| `mic_stream.cpp/h` | 麦克风 WS 推流 | ⬜ | 全 TODO |
| `servo_ctrl.cpp/h` | 舵机点头/摆耳 | ⬜ | 全 TODO；main 里 nod 走 servo stub |
| `board_pins.h` | 集成 harness 引脚常量 | ✅ | 与 `hardware/wiring/esp32_pinout.md` 同步 |
| `feature_flags.h` | 编译期功能开关 stub | 🟡 | `ENABLE_WS_VIDEO`, `ENABLE_WS_AUDIO`, `ENABLE_ARDUINO_OTA` |
| `ota_update.cpp/h` | ArduinoOTA wrapper | ✅ | `ota_begin()`, `ota_loop()`, `ota_set_on_start()` |

### `peripherals/`（face240 / speaker 模块，供独立 env 与 mergetesting 同步）

| 文件 | 角色 | 状态 | 说明 |
|------|------|------|------|
| `peripherals/face240_display.cpp/h` | ST7789 九表情 | ✅ | `face240_*` API；mergetesting 有副本 |
| `peripherals/speaker.cpp/h` | MAX98357A I2S | ✅ | 本地音效；mergetesting 有副本 |
| `peripherals/README.md` | 模块说明 | ✅ | 引脚与 env 对照 |

### `main.cpp` 命令分发（约 L100–174）

| 收到 type | 处理 | 状态 |
|-----------|------|------|
| `system.welcome` | 日志 + `sendCurrentStatus()` | ✅ |
| `display.expression` | `display_emotion()` | ✅ |
| `motion.execute` | motor/servo 分流 + `motion.completed` | ✅ 电机；⬜ 舵机 |
| `audio.play_tts` / `audio.play_local` | `error.report` AUDIO_UNSUPPORTED | ⬜ |
| `config.update` | TODO NVS | ⬜ |
| `system.shutdown` | `ESP.restart()` | ✅ |

### `ws_client.cpp` 出站消息

| 函数 | type | 间隔/触发 |
|------|------|-----------|
| `sendHello()` | `device.hello` | 连接时 |
| `sendHeartbeat()` | `device.heartbeat` | 10s |
| `sendStatus()` | `device.status` | 事件 |
| `sendMotionCompleted()` | `motion.completed` | 动作后 |
| `sendError()` | `error.report` | 错误 |

---

## 独立测试入口（`*_main.cpp` / `*_test.cpp`）

| 文件 | env | 状态 | 用途 |
|------|-----|------|------|
| `motor_manual_main.cpp` | `motor_manual` | ✅ | 串口 WASD |
| `motor_bench_once_main.cpp` | `motor_bench_once` | ✅ | 一次性方向测试 |
| `motor_wifi_manual_main.cpp` | `motor_wifi_manual` | ✅ | AP 网页控电机 |
| `motor_cam_wifi_manual_main.cpp` | `motor_cam_wifi_manual` | ✅ | AP + MJPEG + 电机 + QR overlay |
| `ota_bootstrap_main.cpp` | `ota_bootstrap` / `ota_bootstrap_wifi` | ✅ | WiFi STA + ArduinoOTA recovery bridge |
| `camtesting_program.cpp` | `camtesting` | ✅ | 相机 AP 流 |
| `camera_motor_centering_demo_main.cpp` | `keepfacecenter` | 🟡 | 人脸居中 + 电机脉冲 |
| `serial_qr_servo_main.cpp` | `serialqrservo` | 🟡 | 串口 JPEG + PC QR |
| `serial_red_tracker_main.cpp` | `serialredtracker` | 🧪 | 串口红目标 |
| `red_circle_tracker_main.cpp` | `redtracker` | 🧪 | 设备端红圆跟踪 |
| `display128_tft_smoke_main.cpp` | `display_test` | ✅ | 128×160 基础 |
| `face240_roboeyes_demo_main.cpp` | `face240_roboeyes`（`face240` 为其 alias） | ✅ | 2.4 寸 RoboEyes 风格 |
| `robot_face_9expr_merged_optimized.cpp` | `face240_9expr_merged` | ✅ | **九表情 merged**（产品路径） |
| `face240_wire_check_main.cpp` | `face240_wiretest` / `face240_integrated` | ✅ | 接线/颜色 |
| `tft_espi_probe.cpp` | `tftprobe_hybrid_rawinit` | ✅ | ST7789 hybrid 探测 |
| `inmp441_rms_check_main.cpp` | `voice_recognition_test` | ✅ | INMP441 I2S RMS |
| `max98357a_tone_check_main.cpp` | `speaker_amp_test` | ✅ | MAX98357A 音调 |
| `archive/integrated_main.cpp` | `esp32-s3-integrated_legacy` | 🧪 | 位于 `src/archive/`；历史 firmware-side DK-2500 snapshot；新烧录走 `robot/mergetesting` |

### 已归档 / 实验目录（不参与主 env 编译）

| 路径 | 说明 |
|------|------|
| `archive/face240_espi_test.cpp` | TFT_eSPI 实验（2026-06-23 归档） |
| `src/archive/integrated_main.cpp` | 历史 firmware-side DK-2500 integration snapshot；仅 legacy env 编译 |
| `experiments/face240_raw_design_test.cpp` | dirty-rect 实验；`test_face240_raw_dirty_rect.py` |
| ~~`monthly_salary_meow_frames.h`~~ | 已删除（2026-06-23） |
| ~~`robot_face_9expressions_no_shell.cpp`~~ | 已删除，由 merged 版取代 |

---

## PlatformIO env 完整列表

见 `robot/firmware/platformio.ini` 中 `[env:*]`。
验证命令见 [05_test_matrix](./05_test_matrix.md)。
`platformio.ini` 是实际 build 入口真相；删文件或改状态前先查 `build_src_filter`。

---

## 与 mergetesting 的关系

| firmware 源 | mergetesting 对应 |
|-------------|-------------------|
| `motor_ctrl.cpp` | 复制 + 联调脉冲 |
| `display.cpp` | ST7735 分支 |
| `robot_face_9expr_merged_optimized.cpp` | `face240_display.cpp` |
| `inmp441_rms_check_main.cpp` | `mic_stream.cpp` |
| `max98357a_tone_check_main.cpp` | `speaker.cpp` |
| `cam_stream.cpp` | + WS 推流 |
| `ws_client.cpp` | 三通道增强版 |

方向是 **firmware -> mergetesting**：先在 `robot/firmware` 验证单项机器人功能，再把最小可用模块复制/同步到 `robot/mergetesting` 做 `/control` `/video` `/audio` 联调。不要把 mergetesting 的联调 loop 回迁成新的 firmware 默认入口。见 `robot/firmware/MIGRATION_FROM_MERGETESTING.md`。
