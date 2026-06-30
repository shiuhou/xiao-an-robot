# Mergetesting 注册表 — `robot/mergetesting/`

> **DK-2500 联调专用固件。** 独立 PlatformIO 工程，不替换 `robot/firmware/src/main.cpp`。

## Env 矩阵

| env | DISPLAY | CAMERA | MIC | 用途 | H |
|-----|---------|--------|-----|------|---|
| `mergetesting` | ST7735 | 开 | 关 | 默认合并 baseline | — |
| `mergetesting_display_only` | ST7735 | 关 | 关 | Phase 1-2 `/control` | ✅ 2026-06-26 |
| `mergetesting_display_only_ota` | ST7735 | 关 | 关 | Phase 1-2 OTA upload | ✅ 2026-06-26 |
| `mergetesting_face240_only` | ST7789 九表情 | 关 | 关 | 2.4" 表情 + `/control`; boot default `face=1` happy | ✅ 2026-06-30 |
| `mergetesting_face240_only_ota` | ST7789 九表情 | 关 | 关 | face240 OTA upload | ✅ 2026-06-26 |
| **`mergetesting_care_demo_face240`** | ST7789 九表情 | **关** | **关** | **OpenClaw Step 33 实机 care demo**（control+face240+motor+speaker，无 `/video`/`/audio`） | ✅ H 2026-06-27 |
| `mergetesting_care_demo_face240_ota` | ST7789 | 关 | 关 | 上述 care demo OTA | ✅ P |
| `mergetesting_cam_only` | 关 | 开 | 关 | **Phase 3 传画** QVGA | ✅ 2026-06-26 |
| `mergetesting_cam_only_ota` | 关 | 开 | 关 | camera OTA + `/video` 落图 | ✅ 2026-06-26 |
| `mergetesting_mic_only` | 关 | 关 | 开 | PCM → `/audio` | ✅ 2026-06-26 |
| `mergetesting_mic_only_ota` | 关 | 关 | 开 | mic OTA + PCM stream | ✅ 2026-06-26 |
| `mergetesting_motor_only` | 关 | 关 | 关 | motion 隔离 | ✅ 2026-06-26 |
| `mergetesting_motor_only_ota` | 关 | 关 | 关 | motor OTA | ✅ P |
| `mergetesting_speaker_only` | 关 | 关 | 关 | speaker 隔离；COM19 安全本地音效已确认，spoken PCM TTS 仍为诊断路径 | ✅ 2026-06-29 |
| `mergetesting_speaker_only_ota` | 关 | 关 | 关 | speaker OTA；host `192.168.137.1`，最新 robot IP `192.168.137.200` | ✅ 2026-06-29 |
| `mergetesting_speaker_phrase_only_ota` | 关 | 关 | 关 | 内置句子 PCM 诊断；默认 GPIO35/36/37 first PCM write 后 WDT；当前 Octal PSRAM 板不要用这组 speaker pin | ⚠️ 2026-06-29 |
| `mergetesting_speaker_altpins_only` | 关 | 关 | 关 | speaker-only A/B 诊断；MAX98357A 临时 BCLK/LRC/DIN=GPIO39/40/41；串口本地音效无 WDT | ✅ H/P 2026-06-29 |
| `mergetesting_speaker_altpins_only_ota` | 关 | 关 | 关 | GPIO39/40/41 speaker-only OTA target；外部 5V/no-USB 下 WebSocket 本地音效用户确认有声；已用于恢复安全固件 | ✅ H/P 2026-06-29 |
| `mergetesting_speaker_altpins_phrase_only` | 关 | 关 | 关 | altpins + 内置句子 PCM；正确接线后 `tts serial` 完成 PCM 写入并释放 I2S，无 WDT；repo gain 已调到 16，待可发声时复测 | ✅ H/P 2026-06-29 |
| `mergetesting_speaker_altpins_phrase_only_ota` | 关 | 关 | 关 | GPIO39/40/41 altpins + 内置句子 PCM OTA target；外部 5V/no-USB 下 `audio.play_tts` 已听到 `I can speak now.`，`audio.playback_done` 正常；repo gain 已调到 16 但未上板复测 | ✅ H/P 2026-06-29 |
| `mergetesting_speaker_drain_only_ota` | 关 | 关 | 关 | speaker PCM drain-only 诊断，跳过 I2S 播放 | ✅ P/H 2026-06-28 |
| `mergetesting_audio_shared_i2s_diag` | 关 | 关 | 关 | 独立 USB Serial 半双工音频共存诊断；BCLK=39、WS=40、Mic SD=41、Speaker DIN=47；RX=I2S0、TX=I2S1；COM22 日志走 UART0 Serial0 RX=44 TX=43；SPEAK 先写 1 kHz probe tone，再写 embedded phrase gain=20；不跑主 app/WiFi/WS，不用 GPIO35/36/37 | ✅ P / H partial: COM19/native-USB 曾能出句子；COM22 app/I2S/probe 日志正常：probe `bytes_written=18688`、phrase `bytes_written=97520`、`playback_done ok`、无 WDT/reset；若仍无声，硬件音频输出侧待查 2026-06-29 |
| `mergetesting_full_face240` | ST7789 | 开 | 开 | face240 + 全子系统合并 | ✅ H 2026-06-27 |
| `mergetesting_full_face240_ota` | ST7789 | 开 | 开 | 上述合并 OTA | ✅ P/H smoke；当前 full H 用 USB |
| `mergetesting_base64_video` | 开 | 开 | 关 | video base64 fallback | — |
| `mergetesting_control_base` | 关 | 关 | 关 | control+OTA 基座（无 display/cam/mic） | ✅ P |
| `mergetesting_control_ping` | 关 | 关 | 关 | 最小 `/control` ping（无 motor/speaker） | ✅ P |
| `mergetesting_control_ping_ota` | 关 | 关 | 关 | control ping OTA | ✅ P |
| `mergetesting_control_only` | 关 | 关 | 关 | motor+speaker+control（无 display/cam/mic） | ✅ P |
| `mergetesting_control_only_ota` | 关 | 关 | 关 | control-only OTA | ✅ P |

编译验证：2026-06-26 全部 split env 编译 SUCCESS；实机 H 见 `docs/status/2026-06-26.md` 与 `docs/agents/08_priority_queue_results.json`（T07-T17 全部 PASS_H）。`mergetesting_full_face240` 已在 2026-06-27 通过 full env `/control` motor、face240、speaker、`/video`、`/audio` 硬件 smoke。

## 源文件注册表

| 文件 | 来源 | 状态 | 职责 |
|------|------|------|------|
| `main.cpp` | thin Arduino entrypoint | ✅ | 只转发 `setup()` / `loop()` 到 `MergetestingApp` |
| `app/mergetesting_app.cpp/h` | app layer | ✅ | WiFi/OTA/WS/camera/mic/serial mock runtime wiring |
| `services/robot_state.cpp/h` | service layer | ✅ | expression/motion/camera/busy/docked/transport state |
| `services/status_service.cpp/h` | service layer | ✅ | `device.status`, `command.ack`, `error.report`, `motion.completed` |
| `services/motion_service.cpp/h` | service layer | ✅ | non-blocking `motion.execute`, stop interrupt, action_id ack/completion |
| `services/command_router.cpp/h` | service layer | ✅ | `/control` command dispatch |
| `config.h` | 新建 | ✅ | WiFi、device_id、硬件开关 |
| `hardware_pins.h` | 汇总 wiring | ✅ | 电机/TFT/I2S 引脚 |
| `protocol.h` | firmware + 扩展 | ✅ | + `command.ack`, `video.frame*` |
| `ws_client.cpp/h` | firmware 增强 | ✅ | `/control` `/video` `/audio` |
| `display.cpp/h` | firmware + face240 门面 | ✅ | `MERGETEST_DISPLAY_FACE240` 切换 |
| `face240_display.cpp/h` | `robot_face_9expr_merged_optimized.cpp` | ✅ | `face240_init/emotion/tick` |
| `motor_ctrl.cpp/h` | firmware | ✅ | non-blocking motion；bench/manual 可用 timeout/duration 跑开环 |
| `cam_stream.cpp/h` | firmware + WS | ✅ | 1fps → meta + binary/base64 |
| `camera_ov2640_config.h` | 引脚常量 | ✅ | GOOUUU S3-CAM v1.5 |
| `speaker.cpp/h` | `speaker_amp_test.cpp` | ✅ | care_01/alarm_01/wake_01；diagnostic PCM TTS |
| `mic_stream.cpp/h` | `voice_recognition_test.cpp` | ✅ | PCM chunk → `/audio`; base station diagnostics convert `runtime/latest_audio.pcm` to WAV and report RMS/peak/DC/clipping |
| `debug_log.h` | 新建 | ✅ | LOGI/LOGE 宏 |

## `MergetestingApp` loop 顺序

1. `maintainWiFi()`
2. `wsClient.loop()` — heartbeat 2s
3. `_router.loop()` — deferred `/control` work such as pending PCM stream starts
4. `_motion.loop()` — non-blocking motion completion
5. `display_tick()` — face240 动画帧
6. `pollSerialMockAsr()` — mock/expr/motion/sound/tts
7. `mic.streamLoop()` — 若启用
8. `cam.captureLoop()` — 若 control 已连接

## 串口本地测试（无基站）

```
expr caring
motion move_out_of_dock
sound care_01
tts serial
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
