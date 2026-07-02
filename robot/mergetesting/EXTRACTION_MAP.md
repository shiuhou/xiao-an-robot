# Firmware → Mergetesting 代码提取对照表

本目录从 `robot/firmware/src/` 提取**已 bring-up 可用**的模块，用于明日 DK-2500 联调。

## 已提取并接入主循环

| Mergetesting 模块 | 来源文件 | 状态 | 说明 |
|-------------------|----------|------|------|
| `motor_ctrl.cpp/h` | `motor_ctrl.cpp/h` | ✅ 完整 | DRV8833 引脚/ PWM / execute；联调增加 1.5s 短脉冲 |
| `cam_stream.cpp/h` | `cam_stream.cpp/h` + `motor_cam_wifi_manual_main.cpp` 引脚 | ✅ 完整 | OV2640 QVGA JPEG，1fps → `/video` |
| `display.cpp/h` (ST7735) | `display.cpp/h` | ✅ 完整 | 128×160 矢量表情 + 状态栏 |
| `face240_display.cpp/h` | `robot_face_9expr_merged_optimized.cpp` | ✅ 完整 | 2.4" ST7789 九表情动画，协议名映射 |
| `speaker.cpp/h` | `speaker_amp_test.cpp` | ✅ 完整 | MAX98357A I2S，`care_01` 等音调 |
| `mic_stream.cpp/h` | `voice_recognition_test.cpp` | ✅ 完整 | INMP441 I2S → `/audio` PCM chunk |
| `ws_client.cpp/h` | `ws_client.cpp/h` + 联调扩展 | ✅ 增强 | 三通道 + command.ack + video meta |
| `protocol.h` | `protocol.h` + `docs/protocol/protocol.md` | ✅ 扩展 | flat/envelope 双格式 |
| `main.cpp` | `main.cpp` | ✅ 集成 | WiFi/WS/命令/串口本地测试 |

## 仅 bring-up、未并入主循环（参考 env）

| 源文件 | PlatformIO env | 用途 |
|--------|----------------|------|
| `motor_manual_main.cpp` | `motor_manual` | 串口 WASD |
| `motor_wifi_manual_main.cpp` | `motor_wifi_manual` | AP 网页控车 |
| `motor_cam_wifi_manual_main.cpp` | `motor_cam_wifi_manual` | AP + MJPEG + 电机 |
| `face240_roboeyes_test.cpp` | `face240` | 原始 SPI 表情（已被 merged 版取代） |
| `face240_wire_test.cpp` | `face240_wiretest` | 接线/颜色 |
| `tft_test.cpp` | `display_test` | 128×160 基础 TFT |
| `tft_espi_probe.cpp` | `tftprobe_*` | ST7789 驱动探测 |
| `voice_recognition_test.cpp` | `voice_recognition_test` | 麦克风 RMS（逻辑已进 mic_stream） |
| `speaker_amp_test.cpp` | `speaker_amp_test` | 喇叭音调（逻辑已进 speaker） |
| `camtesting_program.cpp` | `camtesting` | 相机 AP 流 |
| `serial_qr_servo_main.cpp` | `serialqrservo` | 串口 JPEG + PC QR |
| `keep_face_center_test.cpp` | `keepfacecenter` | 人脸居中 + 电机 |

## 仍为 stub（仓库内无可用实现）

| 模块 | 源文件 | Mergetesting 处理 |
|------|--------|-------------------|
| `servo_ctrl` | `servo_ctrl.cpp/h` | 未提取；`nod_head`/`wiggle_ears` 用电机短脉冲代替 |

## 引脚冲突（测试 env 选择）

| 组合 | 冲突 GPIO | 推荐 env |
|------|-----------|----------|
| TFT + OV2640 | 整合线束：TFT 14/21/42/43/44/48 + Camera FPC | 默认可同接；旧 9/10/11/12 线束勿与相机并用 |
| 2.4 face240 + OV2640 | 同上 | `mergetesting_face240_only` 与 `mergetesting_cam_only` 分开 |

## 串口本地测试（无需基站）

连接 monitor 后输入：

```
expr caring
motion move_out_of_dock
sound care_01
mock:帮我定一个二十分鐘的鬧鐘
```

## 构建命令

```powershell
cd robot\mergetesting
pio run -e mergetesting_display_only    # Phase 1-2：小屏 + 电机 + 喇叭 + WS
pio run -e mergetesting_face240_only    # Phase 2：2.4 寸九表情
pio run -e mergetesting_cam_only        # Phase 3：相机 1fps
pio run -e mergetesting_mic_only        # 麦克风 PCM → /audio
pio run -e mergetesting_base64_video    # 视频 base64 fallback
```
