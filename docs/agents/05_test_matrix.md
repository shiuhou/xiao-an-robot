# 测试矩阵

> 状态：**P**=通过(本机编译/单测) **H**=硬件实机 **—**=未跑 **F**=失败

## Python 单元 / 集成

```powershell
python -m unittest discover -s tests -p "test_*.py"
python tools/check_runtime_env.py
```

| 区域 | 代表测试文件 | 覆盖 | 状态 |
|------|-------------|------|------|
| WS /control | `tests/integration/test_ws_control_channel.py` | hello, welcome, 命令 | P |
| WS 转发 | `tests/integration/test_ws_command_forwarding.py` | agent → robot | P |
| Agent Gateway | `tests/integration/test_agent_gateway.py` | RobotGateway | P |
| Robot Motion Skill | `tests/integration/test_robot_motion_skill.py` | 命令构建 | P |
| Emotion 流水线 | `tests/integration/test_emotion_runtime.py` 等 | mock 源 | P |
| Protocol schema | `tests/unit/test_protocol_schema.py` | schema 一致 | P |
| Mergetesting layering | `tests/unit/test_mergetesting_layering.py` | thin `main.cpp`, service files, busy heartbeat, non-blocking motion, split envs, OTA | P |
| WS video source | `tests/unit/test_ws_video_source.py`, `test_ws_server_video_source.py` | QVGA JPEG, frame_meta, binary send | P |
| WS audio channel | `tests/unit/test_ws_audio_channel.py` | INMP441 pins, chunk_meta, PCM persistence, latest-window RMS/peak/DC/clipping stats | P |
| Audio diagnostics | `tests/unit/test_audio_diagnostics.py` | raw `pcm_s16le` stats and WAV export for mic bring-up | P |
| Audio speech trimming | `tests/unit/test_audio_segments.py`, `tests/unit/test_asr_runtime.py` | fixed-window WAV energy trim before ASR; `--trim-speech` metadata | P |
| Continuous ASR demo | `tests/unit/test_continuous_asr_demo.py` | rolling PCM tail energy, utterance start/end detector, fixed-window ASR demo helper | P |
| Dock dashboard | `tests/unit/test_dashboard_server.py` | `/api/dashboard/state` pipeline/triggers contract, mock fallback, static 1024x600 right-panel constraints | P |
| OpenVINO/Qwen | `tests/unit/test_openvino_*` | 模型 wrapper | 🧪 P |
| Mock robot | `tests/mocks/mock_robot.py` | 无 ESP32 测 control | 手动 |

## 固件编译（勿并行同 workspace 多 env）

`robot/firmware` checks are for robot-body feature bring-up only. DK-2500/base-station integration checks are under `robot/mergetesting`.

| env | 命令 | 编译 | 硬件 H |
|-----|------|------|--------|
| `esp32-s3-devkitc-1` | `pio run -e esp32-s3-devkitc-1` | P | — |
| `ota_bootstrap` | `pio run -e ota_bootstrap` | P | H optional: USB first flash |
| `ota_bootstrap_wifi` | `pio run -e ota_bootstrap_wifi` | P | H optional: OTA upload after WiFi ready |
| `motor_cam_wifi_manual` | `pio run -e motor_cam_wifi_manual` | P | H 可选 |
| `face240_wiretest` | `pio run -e face240_wiretest` | P | H |
| `face240_9expr_merged` | `pio run -e face240_9expr_merged` | P | H |
| `voice_recognition_test` | `pio run -e voice_recognition_test` | P | H |
| `speaker_amp_test` | `pio run -e speaker_amp_test` | P | H |
| `esp32-s3-integrated_legacy` | `pio run -e esp32-s3-integrated_legacy` | P: 2026-06-29 after move to `src/archive/` | — legacy snapshot only; do not burn for DK-2500 integration |

## Mergetesting

Use these envs for `/control`, `/video`, and `/audio` integration with `base_station`.

```powershell
cd robot\mergetesting
pio run -e mergetesting_display_only
pio run -e mergetesting_display_only_ota
pio run -e mergetesting_face240_only
pio run -e mergetesting_cam_only
pio run -e mergetesting_cam_only_ota
pio run -e mergetesting_mic_only
pio run -e mergetesting_mic_only_shift16
pio run -e mergetesting_mic_only_shift16_asr
pio run -e mergetesting_mic_only_shift18_asr
pio run -e mergetesting_mic_only_right_shift16
pio run -e mergetesting_mic_only_ota
pio run -e mergetesting
```

| env | 编译 | 联调 H |
|-----|------|--------|
| `mergetesting_display_only` | P: 2026-06-26 Phase 1-2 hardening | H: `/control` hello/heartbeat/commands, 2026-06-26 |
| `mergetesting_display_only_ota` | P: 2026-06-26 | H: espota upload path verified during split-env loop, 2026-06-26 |
| `mergetesting_face240_only` | P: 2026-06-30 boot frame static test | H: expression caring/idle, no watchdog reset, 2026-06-26; USB upload on COM19 and reboot log `face=1` happy, 2026-06-30 |
| `mergetesting_cam_only` | P: 2026-06-26 app/services split | H: QVGA JPEG + `video.frame_meta`, 2026-06-26 |
| `mergetesting_cam_only_ota` | P: 2026-06-26 | H: espota upload, `/video`, `runtime/latest.jpg` valid JPEG, 2026-06-26 |
| `mergetesting_mic_only` | P: 2026-06-26 | H: PCM `/audio`, heartbeat not starved, 2026-06-26 |
| `mergetesting_mic_only_shift16` | P/H: COM22 upload 2026-06-29 | H: current mic diagnostic baseline; left channel with `MERGETEST_MIC_SHIFT_BITS=16` produced intelligible-range stats versus noisy `>>14`: RMS `-37.51 dBFS`, peak `-23.00 dBFS`, DC offset `0.79%` |
| `mergetesting_mic_only_shift16_asr` | P/H: COM19 upload 2026-06-30 | H: 20 ms continuous `/audio` stream works, but close repeated speech clipped at peak `0.0 dBFS` with about `3.5%` clipping; not the current ASR demo gain |
| `mergetesting_mic_only_shift18_asr` | P/H: COM19 upload 2026-06-30 | H: current fixed-window ASR calibration env; 20 ms continuous `/audio`, peak about `-12 dBFS`, clipping `0%`; use with base-station `--trim-speech` before SenseVoice |
| `mergetesting_mic_only_right_shift16` | P/H: COM22 upload 2026-06-29 | H: right channel check produced all-zero PCM with INMP441 L/R tied to GND, confirming left channel is the active channel |
| `mergetesting_mic_only_ota` | P: 2026-06-26 | H: espota upload + PCM stream, 2026-06-26 |
| `mergetesting_motor_only` | P: 2026-06-26 | H: LEDC fix, motion ack/completed + physical direction, 2026-06-26 |
| `mergetesting_speaker_only` | P: 2026-06-29 build/tests pass | H/P: COM19 upload restored safe firmware; serial `sound wakeup_chime` logged `play_local done ... ok=true`, user confirmed sound |
| `mergetesting_speaker_only_ota` | P: 2026-06-29 build ok | H/P: OTA upload works via hotspot host `192.168.137.1`; latest observed robot IP `192.168.137.200`; safe firmware restored after phrase diagnostic |
| `mergetesting_speaker_phrase_only_ota` | P: 2026-06-29 build ok diagnostic env | H/P: default GPIO35/36/37 embedded PCM first write caused WDT; do not use this pin map on the current Octal PSRAM module |
| `mergetesting_speaker_altpins_only` | P: 2026-06-29 build ok diagnostic env | H/P: COM19 upload ok; temporary MAX98357A BCLK/LRC/DIN=39/40/41; serial `sound wakeup_chime` completed without WDT |
| `mergetesting_speaker_altpins_only_ota` | P: 2026-06-29 build ok diagnostic env | H/P: OTA upload to `192.168.137.200` ok; external 5V/no-USB WebSocket `audio.play_local wakeup_chime` heard by user; safe firmware restored |
| `mergetesting_speaker_altpins_phrase_only` | P: 2026-06-29 build ok diagnostic env; repo gain now 16 | H/P: COM19 upload ok; corrected-wiring serial `tts serial` completed embedded sentence PCM and released I2S without WDT |
| `mergetesting_speaker_altpins_phrase_only_ota` | P: 2026-06-29 build ok diagnostic env; repo gain now 16 | H/P: OTA upload to `192.168.137.200` ok; WebSocket `audio.play_tts` at gain 12 was audible as `I can speak now.` and emitted `audio.playback_done status=ok bytes_written=97520 duration_ms=1557`; gain 16 not audibly retested yet |
| `mergetesting_speaker_drain_only_ota` | P: 2026-06-28 build ok diagnostic env | H/P: accepts TTS PCM without I2S playback and avoids reset; isolates remaining fault to PCM-to-I2S playback |
| `mergetesting_audio_shared_i2s_diag` | P: 2026-06-29 build ok after fix; standalone half-duplex diag; BCLK=39 WS=40 MIC_SD=41 SPK_DIN=47; RX uses I2S0, TX uses I2S1; COM22 logs use UART0 Serial0 RX=44 TX=43; embedded phrase gain now 20; SPEAK mode emits a 1 kHz `OUTPUT_PROBE_AMPLITUDE=30000` tone before the phrase; camera/TFT/motor/WiFi/WebSocket disabled | H partial: old I2S0-TX build wrote `97520` bytes but sounded like low-frequency noise; I2S1-TX fixed audible sentence on earlier COM19/native-USB setup. COM22/CH340 app logs now visible and show `output_probe_tone done bytes_written=18688`, `gain=20`, `bytes_written=97520`, `playback_done ok`, repeated `listen_ok=true speak_ok=true`, and no WDT/reset, but user reports no sound on COM22 wiring. Firmware/app execution is no longer the leading suspect; next check MAX98357A module/output stage, speaker +/- output path, 5V/SD/GAIN state, mic quiet/clap contrast, and 3-minute stability |
| `mergetesting_face240_only_ota` | P: 2026-06-26 | H: espota upload + expression path, 2026-06-26 |
| `mergetesting_care_demo_face240` | P: 2026-06-27 Step 33 care demo | H: face240+motor+speaker+/control preflight, no cam/mic, 2026-06-27 |
| `mergetesting_care_demo_face240_ota` | P: 2026-06-27 | P: build/upload path verified; current T18 H used USB |
| `mergetesting_full_face240` | P: 2026-06-26 combined face240 + all subs | H: USB upload at 460800 + `/control` full-speed 5s motor + `/video` + `/audio`, 2026-06-27 |
| `mergetesting_full_face240_ota` | P: 2026-06-26 | H/P: OTA smoke passed earlier; current full H used USB after OTA/COM instability |
| `mergetesting` | P: 2026-06-26 combined baseline | —: burn after split env H (split envs now all H) |

## 固件工具脚本

| 脚本 | 命令 |
|------|------|
| face240 dirty-rect 结构检查 | `python robot/firmware/tools/test_face240_raw_dirty_rect.py` |
| face240 roboeyes framebuffer | `python robot/firmware/tools/test_face240_roboeyes_framebuffer.py` |
| 浏览器表情预览 | 打开 `robot/firmware/tools/face240_preview.html` |

## 端到端联调验收（人工）

| Phase | 验收项 | 通过标准 | 状态 |
|-------|--------|----------|------|
| 1 | `/control` | 5min heartbeat；断线后 capped exponential reconnect；重连后重新 `device.hello` | H: 2026-06-26 |
| 2 | 命令 | 每条 `command.ack`；motion 带 action_id；stop 打断前一动作并回 `motion.completed: interrupted`；未知命令/JSON 不崩 | H: 2026-06-26 |
| 3 | `/video` | `runtime/latest.jpg` 更新 | H: 2026-06-26 |
| 3b | `/audio` | `audio.chunk_meta` + PCM；heartbeat 不被饿死 | H: 2026-06-26 |
| 4 | 关怀闭环 | fatigue → OpenClaw → 三命令 | — |

**Agent 更新规则：** 跑过测试后在本表改 P/H/F 并注明日期。
