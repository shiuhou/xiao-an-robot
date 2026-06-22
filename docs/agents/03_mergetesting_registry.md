# Mergetesting 注册表 — `robot/mergetesting/`

> **DK-2500 联调专用固件。** 独立 PlatformIO 工程，不替换 `robot/firmware/src/main.cpp`。

## Env 矩阵

| env | DISPLAY | CAMERA | MIC | 用途 |
|-----|---------|--------|-----|------|
| `mergetesting` | ST7735 | 开 | 关 | 默认（引脚冲突，慎用） |
| `mergetesting_display_only` | ST7735 | 关 | 关 | Phase 1–2 |
| `mergetesting_face240_only` | ST7789 九表情 | 关 | 关 | 大屏表情 demo |
| `mergetesting_cam_only` | 关 | 开 | 关 | **Phase 3 传画** |
| `mergetesting_mic_only` | ST7735 | 关 | 开 | PCM → `/audio` |
| `mergetesting_base64_video` | 开 | 开 | 关 | video base64 fallback |

编译验证（2026-06-22）：`display_only`, `face240_only`, `cam_only` → SUCCESS。

## 源文件注册表

| 文件 | 来源 | 状态 | 职责 |
|------|------|------|------|
| `main.cpp` | 新建 + firmware main 逻辑 | ✅ | WiFi/WS/命令/串口本地测试 |
| `config.h` | 新建 | ✅ | WiFi、device_id、硬件开关 |
| `hardware_pins.h` | 汇总 wiring | ✅ | 电机/TFT/I2S 引脚 |
| `protocol.h` | firmware + 扩展 | ✅ | + `command.ack`, `video.frame*` |
| `ws_client.cpp/h` | firmware 增强 | ✅ | `/control` `/video` `/audio` |
| `display.cpp/h` | firmware + face240 门面 | ✅ | `MERGETEST_DISPLAY_FACE240` 切换 |
| `face240_display.cpp/h` | `robot_face_9expr_merged_optimized.cpp` | ✅ | `face240_init/emotion/tick` |
| `motor_ctrl.cpp/h` | firmware | ✅ | + 无距离时 1.5s 脉冲 |
| `cam_stream.cpp/h` | firmware + WS | ✅ | 1fps → meta + binary/base64 |
| `camera_ov2640_config.h` | 引脚常量 | ✅ | GOOUUU S3-CAM v1.5 |
| `speaker.cpp/h` | `speaker_amp_test.cpp` | ✅ | care_01/alarm_01/wake_01 |
| `mic_stream.cpp/h` | `voice_recognition_test.cpp` | ✅ | PCM chunk → `/audio` |
| `debug_log.h` | 新建 | ✅ | LOGI/LOGE 宏 |

## `main.cpp` loop 顺序

1. `maintainWiFi()`
2. `wsClient.loop()` — heartbeat 2s
3. `display_tick()` — face240 动画帧
4. `pollSerialMockAsr()` — mock/expr/motion/sound
5. `mic.streamLoop()` — 若启用
6. `cam.captureLoop()` — 若 control 已连接

## 串口本地测试（无基站）

```
expr caring
motion move_out_of_dock
sound care_01
mock:帮我定闹钟
```

## 出站 WS 消息（机器人→基站）

| type | 通道 | 频率 |
|------|------|------|
| `device.hello` | control | 连接时 |
| `device.heartbeat` | control | 2s |
| `command.ack` | control | 每命令 |
| `video.frame_meta` | control | 每帧前 |
| JPEG binary | video | 1fps |
| `video.frame` (base64) | control | fallback |
| `audio.chunk_meta` + PCM | audio/mic | ~10Hz 块 |

## 文档

- 操作说明：`robot/mergetesting/README.md`
- 基站对接：`robot/mergetesting/CAPABILITIES.md`
- 提取对照：`robot/mergetesting/EXTRACTION_MAP.md`
