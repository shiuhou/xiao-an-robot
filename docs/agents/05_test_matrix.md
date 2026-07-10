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
| Emotion 流水线 | `tests/integration/test_emotion_runtime.py` 等 | mock 源；2026-07-06 `tests.unit.test_emotion_runtime` 新增正式 `ws_video` source、visual trace observer、ws_server 注入/清理接线单测 | P: ws_video targeted PASS；本机完整 `tests.unit.test_emotion_runtime` 仍有既有 OpenVINO 缺依赖/模型断言噪声 |
| Protocol schema | `tests/unit/test_protocol_schema.py` | schema 一致 | P |
| Mergetesting layering | `tests/unit/test_mergetesting_layering.py` | thin `main.cpp`, service files, busy heartbeat, non-blocking motion, split envs, OTA | P |
| WS video source | `tests/unit/test_ws_video_source.py`, `test_ws_server_video_source.py` | QVGA JPEG, frame_meta, binary send | P |
| WS audio channel | `tests/unit/test_ws_audio_channel.py` | INMP441 pins, chunk_meta, PCM persistence, latest-window RMS/peak/DC/clipping stats | P |
| Audio diagnostics | `tests/unit/test_audio_diagnostics.py` | raw `pcm_s16le` stats and WAV export for mic bring-up | P |
| Audio speech trimming | `tests/unit/test_audio_segments.py`, `tests/unit/test_asr_runtime.py` | fixed-window WAV energy trim before ASR; `--trim-speech` metadata | P |
| Fixed-window ASR demo | `tests/unit/test_fixed_window_asr_demo.py` | rolling PCM tail energy, utterance start/end detector, fixed-window ASR demo helper | P |
| Base-station mic demo | `tools/demo/demo1_usb_mic_to_agent_screen.py`, `tests/unit/test_demo1_usb_mic_to_agent_screen.py` | DK-2500 USB mic -> fixed-format ASR WAV (`16 kHz / mono / pcm_s16le`) + input peak/clipping diagnostics -> ASR transcript -> fixed `demo1.openclaw_context.v1` context -> filtered Demo 1 OpenClaw tool manifest -> OpenClaw Gateway `xiaoan-runtime` -> strict validated tool_calls -> ActionExecutor -> `/agent`; mock fallback writes `source=mock` | P/H partial: 2026-07-05 `.venv/bin/python -m unittest tests.unit.test_asr tests.unit.test_asr_runtime tests.unit.test_audio_segments tests.unit.test_demo1_usb_mic_to_agent_screen` PASS 80 tests after local SenseVoice loader fix. Replay of `runtime/demo1_audio/demo1_usb_mic_20260705_172922.asr.wav` returned “小安我有点累了”; interrupted live run completed real mic -> OpenClaw -> real robot with move-out/turn/expression/TTS acks and `audio.playback_done ok`. Later mock-text full path `tools/demo/run_demo1_mic_to_robot.sh --once --no-screen --mock-text "小安我有点累了，出来陪我一下"` completed OpenClaw `xiaoan.robot.care`, move-out, turn, caring expression, and TTS `audio.playback_done ok bytes=159744 duration_ms=5519`; user heard speech but volume is still too small. Remaining H issue: mic gain and speaker loudness calibration are close but not final. |
| Assistant capture demo | `tools/demo/demo_assistant_capture.py`, `tests/unit/test_demo_assistant_capture.py` | DK-2500/base mic or mock text -> `assistant_capture_context.v1` -> OpenClaw-owned capture result -> dashboard and optional robot feedback; rejects reply-text-only, empty mock text, and local SQLite compatibility tools as product success | P: 2026-07-03 `.venv/bin/python -m unittest tests.unit.test_demo_assistant_capture tests.unit.test_dashboard_server tests.unit.test_prepare_visual_chain_preflight`; CLI smoke context-only writes `ignored`; OpenClaw offline smoke exits 1 with `status=failed` |
| Dock dashboard | `tests/unit/test_dashboard_server.py` | `/api/dashboard/state` pipeline/triggers/assistant_capture contract, mock fallback, static 1024x600 glance layout constraints | P: 2026-07-03 `.venv/bin/python -m unittest tests.unit.test_dashboard_server`; assistant capture result is exposed to glance UI |
| Integration Console | `tests/unit/test_integration_console_server.py`, `tests/unit/test_ws_state_snapshot.py` | `/api/health`, `/api/state` without runtime files, `/api/latest-image` missing-file behavior, robot command payload construction, scenario step ordering, tool whitelist rejection, `ws_state.json` reader and atomic writer；2026-07-06 visual state source改为正式 `emotion_runtime --source ws_video` 旁路文件 | P: 2026-07-06 `python -m unittest tests.unit.test_ws_video_source tests.unit.test_ws_server_video_source tests.unit.test_visual_trace tests.unit.test_integration_console_server tests.unit.test_run_ws_video_runtime` -> OK 29 tests |
| Visual-chain preflight | `tests/unit/test_prepare_visual_chain_preflight.py` | camera-free static image decode, mock image runtime command, OpenFace/Qwen readiness reporting, Git LFS pointer detection, JSON-safe timeout reports, bad manifest failure reports, repo-root relative model paths | P: 2026-07-03 `.venv/bin/python -m unittest tests.unit.test_demo_assistant_capture tests.unit.test_dashboard_server tests.unit.test_prepare_visual_chain_preflight`; manual preflight passes image decode + mock runtime + OpenFace real runtime; still fails expected Qwen readiness because partial download is missing 3 large `.bin` files |
| OpenClaw P0 preflight runner | `tests/unit/test_openclaw_preflight_p0_runner.py`; manual `python tools\run_openclaw_preflight_p0.py --device-id xiaoan_robot_01` | robot online, streamed TTS x3, local wake sound, thinking/speaking face, stop command through `/agent` with robot-side event evidence | P/H: 2026-07-08 DIN41 buffered PCM, `XIAOAN_TTS_TARGET_PEAK=500`; Windows SAPI used `XIAOAN_TTS_VOICE='Microsoft Hanhan Desktop'`, Linux edge-tts uses `XIAOAN_EDGE_TTS_VOICE` |
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
| `mergetesting_full_face240_spoken_tts` | P: 2026-07-04 env set to embedded phrase gain 32; full face240 + camera + robot mic fallback + motor + speaker | H: speaker path validated on DIN41 standalone MAX98357A board; full robot `/control` loop pending WiFi/base-station run |
| `mergetesting_full_face240_spoken_tts_ota` | P: 2026-07-04 env inherits embedded phrase gain 32 | H: pending OTA retest |
| `mergetesting_care_demo_face240_spoken_tts` | P: 2026-07-04 env set to embedded phrase gain 32; care demo + embedded spoken TTS phrase, speaker DIN=47 | H: speaker path validated on DIN41 standalone MAX98357A board; DIN47 robot harness pending |
| `mergetesting_care_demo_face240_spoken_tts_din41` | P: 2026-07-04 build target updated to embedded phrase gain 32; temporary care-demo fallback for MAX98357A DIN=41, robot mic disabled | H: COM23 standalone speaker path heard `I can speak now`; tone probe loud; gain 32 chosen over gain 64 for stability; streamed PCM TTS over `/agent -> /control` passed at low volume with `你好` (`40052` bytes, `2297` ms), `你好，我是小安。` (`83068` bytes, `3741` ms), and an arbitrary OpenClaw sentence (`148038` bytes, `5491` ms). 2026-07-04 Linux `/dev/ttyACM0` USB upload PASS for base-station-mic demo config; serial boot shows WiFi `PnX` connected, robot IP `192.168.31.176`, `/control` target `192.168.31.252:8765`, face240/motor/speaker enabled, robot mic/video disabled. |
| `mergetesting_care_demo_face240_spoken_tts_din41_ota_usb` | P/H: 2026-07-09 build/upload PASS after adding temporary buffered receive heap/PSRAM diagnostics; still enables ArduinoOTA for the DIN41 spoken TTS demo path. 2026-07-08 marker-only rebuild PASS after adding explicit `buffered pcm playback start` / `buffered pcm task done` logs. | H: 2026-07-05 USB upload PASS on `/dev/ttyACM0`; serial boot showed WiFi `PnX`, robot IP `192.168.31.176`, `OTA Ready hostname=xiao-an-esp32 auth=disabled`, face240/motor/speaker enabled, robot mic/video disabled. 2026-07-08 replaced speaker with `4 ohm 3 W, 500-5000 Hz`; current accepted spoken TTS baseline is DIN41 full PCM buffered playback, `XIAOAN_TTS_TARGET_PEAK=500`, `MERGETEST_SPEAKER_STREAM_GAIN=32`, and OS-specific TTS backend voice selection. 2026-07-09 direct `/agent` length sweep on `/dev/ttyACM0` succeeded for `你好` / `你好，我是小安。` / long Chinese sentence: buffered bytes 38400/66816/158976, `failed=0`, `audio.playback_done ok bytes_written=65992/122828/307148`; no reset or断链 reproduced. |
| `mergetesting_care_demo_face240_spoken_tts_din41_ota` | P/H: 2026-07-08 wireless `espota` upload PASS to `192.168.31.175` from host `192.168.31.253` | H: PlatformIO OTA child env built; direct `espota.py` upload reported `Result: OK` and `Success`. Robot reconnected with reset reason `software`; console-path TTS returned robot-side `audio.playback_done ok bytes_written=184468 duration_ms=2917`. Serial marker capture remains pending because no local serial device was visible. |
| `mergetesting_care_demo_face240_spoken_tts_din41_gain16_ota` | P/H partial: 2026-07-11 build SUCCESS; OTA upload to `192.168.137.116` from host `192.168.137.139` SUCCESS (`Result: OK`) | H partial/F medium: short `/agent` TTS `十六倍增益测试。你好。` returned `audio.playback_done ok bytes_written=203268 duration_ms=3204`; 22-char clarity sentence returned `command.ack accepted` then robot software reset/reconnect before playback_done. Do not treat gain16 as the stable spoken-TTS baseline yet. |
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
| 3b | `/audio` fallback | robot `audio.chunk_meta` + PCM；heartbeat 不被饿死；作为诊断/备选链路 | H: 2026-06-26 |
| 4 | 基站 mic 关怀闭环 | DK-2500 mic -> ASR -> OpenClaw Gateway / `xiaoan-runtime` -> ActionExecutor -> `/agent` -> `/control` -> ack/completed | P/H partial: 2026-07-05 real/mocked phrase paths reached OpenClaw and produced `xiaoan.robot.care`; server captured move-out/turn/expression/TTS acks and playback done. Python target tests PASS 66 tests after gateway TTS ack timeout fix. Full H still needs one clean现场复测 after lowering TTS peak and making move-out explicit `0.56 / 2000ms`. |

**Agent 更新规则：** 跑过测试后在本表改 P/H/F 并注明日期。
