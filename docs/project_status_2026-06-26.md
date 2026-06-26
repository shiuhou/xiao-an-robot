# Project Status 2026-06-26

This snapshot records the mergetesting `/control` Phase 1-2 hardening work.
The later hardware-loop section records the real-board evidence gathered during
the same bring-up session.

## Scope

- Firmware area: `robot/mergetesting` only.
- Base-station area: `base_station/ws_server` and local command tooling.
- Excluded for this milestone: `/video`, `/audio` PCM, TTS HTTP, OpenVINO, and OpenClaw.

## Phase 1-2 Control Loop

Current target envs:

| Env | Purpose | Status |
| --- | --- | --- |
| `mergetesting_display_only` | USB-uploadable `/control`, display, motor, speaker smoke firmware | P: build verified 2026-06-26 after Phase 1-2 hardening |
| `mergetesting_display_only_ota` | OTA upload target for the same Phase 1-2 firmware | P: build verified 2026-06-26; H not claimed |
| `mergetesting_face240_only` | 2.4 inch face display `/control` command path | P: build verified 2026-06-26 after Phase 1-2 hardening |
| `mergetesting_cam_only` | QVGA camera-only `/video` target | P: build verified 2026-06-26; H should be checked before combined firmware |
| `mergetesting_cam_only_ota` | Camera-only OTA `/video` regression target | P: build verified 2026-06-26; 2026-06-25 camera H preserved |
| `mergetesting_mic_only` | INMP441 `/audio` target | P: build verified 2026-06-26; H not claimed |
| `mergetesting` | Combined display + camera + motor + speaker baseline | P: build verified 2026-06-26; use after split env H passes |

Expected `/control` runtime behavior:

- ESP32 connects WiFi and opens `ws://<base_station>:8765/control`.
- On each control connection, ESP32 sends `device.hello`.
- Base station replies `system.welcome`.
- ESP32 applies welcome config and sends `device.status`.
- ESP32 sends periodic `device.heartbeat`.
- Control disconnects use capped exponential reconnect backoff up to 30 seconds.
- Reconnect success sends a fresh `device.hello`.
- Bad JSON is logged and ignored.
- Unknown control types are logged and ignored on firmware.

Phase 2 command examples:

```powershell
python tools\send_robot_command.py expression caring
python tools\send_robot_command.py motion move_out_of_dock
python tools\send_robot_command.py local care_01
```

Expression robot-facing message:

```json
{
  "type": "display.expression",
  "payload": {
    "expression": "caring",
    "duration_ms": 3000,
    "loop": false
  }
}
```

Motion behavior:

- `motion.execute` supports `move_out_of_dock`, `move_back_to_dock`, `turn`, and `stop`.
- Movement is open-loop and deadline-driven in `MotionService::loop()`, not blocking the main Arduino loop.
- `command.ack` includes `action_id` when the command has one.
- Completion uses the same `action_id` in `motion.completed`.
- A new motion command or `stop` interrupts the active action and emits `motion.completed` with `result: "interrupted"`.
- Unknown motion actions report error ack/error report instead of fake success.

Local sound behavior:

- `audio.play_local` supports `care_01`, `alarm_01`, and `wake_01`.
- Unsupported local sounds return an error path; the robot no longer plays a fallback tone and calls it success.

## Safe Upload Flow

USB upload:

```powershell
cd robot\mergetesting
pio run -e mergetesting_display_only
pio run -e mergetesting_display_only -t upload --upload-port COMxx
pio device monitor -b 115200
```

OTA upload when an OTA-enabled firmware is already running:

```powershell
cd robot\mergetesting
pio run -e mergetesting_display_only_ota
pio run -e mergetesting_display_only_ota -t upload --upload-port <board-ip>
```

Do not use `ota_bootstrap_wifi` to upload this functional firmware. That env
only refreshes the bootstrap bridge.

## Verification Targets

```powershell
python -m unittest tests.integration.test_ws_control_channel tests.integration.test_ws_command_forwarding tests.unit.test_ws_server_sessions tests.unit.test_mergetesting_layering tests.unit.test_send_robot_command
python -m unittest discover -s tests -p "test_*.py"
python tools/check_runtime_env.py
cd robot\mergetesting
pio run -e mergetesting_display_only
pio run -e mergetesting_display_only_ota
pio run -e mergetesting_face240_only
pio run -e mergetesting_cam_only_ota
```

Recorded local results on 2026-06-26:

- `python -m unittest discover -s tests -p "test_*.py"`: `Ran 772 tests`, `OK`.
- `python tools/check_runtime_env.py`: exit code 0, `overall_status: warning` because OpenVINO/FunASR/ONNXRuntime and staged model folders are absent.
- `pio run -e mergetesting_display_only`: SUCCESS.
- `pio run -e mergetesting_face240_only`: SUCCESS; existing TFT_eSPI `TOUCH_CS` warning only.
- `pio run -e mergetesting_display_only_ota`: SUCCESS.
- `pio run -e mergetesting_cam_only_ota`: SUCCESS.
- `git diff --check`: exit code 0; CRLF warnings only.

Hardware H remains pending until a real board completes the full Phase 1-2
sequence with serial/server logs.

## Fresh Integration Results - 2026-06-26 04:26 +08:00

Long-running agent loop files are now present:

- `tools/run_integration_loop.py`: loads the queue, selects one ready task per cycle, honors active waiting tasks, and writes JSON state.
- `docs/agents/08_priority_queue.yaml`: declares one-task-per-cycle policy, highest-priority ready selection, max 2 fix attempts, and tasks `T00` through `T16`.
- `docs/agents/08_priority_queue_results.json`: records this handoff result set.

Fresh commands run in this pass:

| Check | Result |
| --- | --- |
| `python -m unittest tests.unit.test_run_integration_loop` | PASS, 4 tests |
| `python -m unittest discover -s tests -p "test_*.py"` | PASS, 773 tests |
| `pio run -e mergetesting_display_only` | SUCCESS, RAM 14.6%, Flash 27.5% |
| `pio run -e mergetesting_face240_only` | SUCCESS, RAM 61.4%, Flash 27.4% |
| `pio run -e mergetesting_cam_only` | SUCCESS, RAM 15.6%, Flash 28.1% |
| `pio run -e mergetesting_mic_only` | SUCCESS, RAM 15.0%, Flash 27.6% |
| `pio run -e mergetesting` | SUCCESS, RAM 15.9%, Flash 29.4%; TFT_eSPI warns `TOUCH_CS` is undefined, expected for no-touch setup |

Full `mergetesting` is compile-safe. For first hardware H on 2026-06-27, keep
the split-env order because it isolates `/control`, face240, `/video`, and
`/audio` failures. Burn full `mergetesting` only after the split envs produce
serial and base-station proof.

## 2026-06-27 Morning Checklist

1. Prepare local config.
   - In `robot/mergetesting`, copy `src\config.local.example.h` to `src\config.local.h` if missing.
   - Set `MERGETEST_WIFI_SSID`, `MERGETEST_WIFI_PASSWORD`, `MERGETEST_BASE_STATION_IP`, and `MERGETEST_BASE_STATION_PORT`.
   - Confirm `src\config.local.h` is ignored and not committed.
   - First triage if WiFi fails: wrong SSID/password, base station on a different LAN, or firewall blocking TCP 8765.

2. Start base station.
   - Command from repo root: `python -m base_station.ws_server.server`.
   - Success: server listens on port 8765, then logs `Robot connected`, `device.hello`, and heartbeat after ESP32 connects.
   - First triage if no robot session: confirm `MERGETEST_BASE_STATION_IP`, Windows firewall, and that ESP32 and DK-2500 are on the same network.

3. Flash Phase 1-2 `/control` first.
   - Commands:
     ```powershell
     cd robot\mergetesting
     pio run -e mergetesting_display_only
     pio run -e mergetesting_display_only -t upload --upload-port COMxx
     pio device monitor -b 115200
     ```
   - Serial success: `[WiFi] Connected IP=...`, `[WS] Control connected`, `Sent device.hello`, and periodic `Heartbeat`.
   - Base-station success: `Robot connected`, `device.hello`, `command.ack` for commands.

4. Verify `/control` functions on `mergetesting_display_only`.
   - Expression: `python tools\send_robot_command.py expression caring`.
     Success: base station returns `command.ack`; serial shows control dispatch; display changes to caring.
     First triage: check robot session/device_id `xiaoan_robot_01` and command envelope.
   - Motion: `python tools\send_robot_command.py motion move_out_of_dock`.
     Success: `command.ack` and `motion.completed` carry the same `action_id`; motor serial logs the action.
     First triage: DRV8833 wiring left GPIO1/GPIO2, right GPIO3/GPIO48, motor power, common ground, and direction macros.
   - Sound: `python tools\send_robot_command.py local care_01`.
     Success: `command.ack`; serial logs `[Speaker] play_local care_01`; MAX98357A outputs tone.
     First triage: MAX98357A BCLK=35, LRC=36, DIN=37, power, speaker wiring, and `MERGETEST_ENABLE_SPEAKER`.

5. Verify face240 separately.
   - Burn `pio run -e mergetesting_face240_only -t upload --upload-port COMxx`.
   - Success: face boots, expression command changes the 2.4 inch face, no watchdog reset.
   - First triage: TFT SCK=14, MOSI=21, CS=42, DC=43, RST=44, BL tied to 3V3; avoid legacy GPIO9-12 bench wiring.

6. Verify camera separately.
   - Burn `pio run -e mergetesting_cam_only -t upload --upload-port COMxx`.
   - Success: serial logs `Camera ready QVGA320`, `/control` emits `video.frame_meta`, `/video` sends JPEG, and `runtime/latest.jpg` updates on the base station.
   - First triage: OV2640 FPC orientation, camera power, PSRAM availability, and stay on QVGA camera-only if resets occur.

7. Verify mic separately.
   - Burn `pio run -e mergetesting_mic_only -t upload --upload-port COMxx`.
   - Success: serial logs `[Mic] INMP441 ready`; base station logs `/audio` connected and receives `audio.chunk_meta` plus PCM chunks while heartbeat continues.
   - First triage: INMP441 BCLK=39, WS=40, DIN=41, mic power/ground, and pin conflict with speaker wiring.

8. Only after split H passes, try combined `mergetesting`.
   - Build already passes. Upload combined firmware only after display/control, camera, and mic each have isolated H proof.
   - First triage if combined resets: return to split envs and isolate camera init, display init, then speaker/motor one at a time.

## Pre-Hardware Verification Refresh - 2026-06-26 04:52 +08:00

Dedicated bring-up report: `docs/agents/09_hardware_bringup_checklist.md`.

Fresh checks run for the 2026-06-27 morning hardware pass:

| Check | Result |
| --- | --- |
| `python -m unittest tests.unit.test_send_robot_command tests.integration.test_ws_control_channel tests.integration.test_ws_command_forwarding tests.unit.test_ws_server_sessions` | PASS, 19 tests |
| `python -m unittest tests.unit.test_mergetesting_layering` | PASS, 17 tests |
| `python -m unittest tests.unit.test_ws_video_source tests.unit.test_ws_server_video_source` | PASS, 11 tests |
| `python -m unittest tests.unit.test_ws_audio_channel` | PASS, 2 tests |
| `pio run -e mergetesting_display_only` | SUCCESS, RAM 14.6%, Flash 27.5% |
| `pio run -e mergetesting_face240_only` | SUCCESS, RAM 61.4%, Flash 27.4% |
| `pio run -e mergetesting_cam_only` | SUCCESS, RAM 15.6%, Flash 28.1% |
| `pio run -e mergetesting_mic_only` | SUCCESS, RAM 15.0%, Flash 27.6% |
| `pio run -e mergetesting` | SUCCESS, RAM 15.9%, Flash 29.4% |
| `python -m unittest discover -s tests -p "test_*.py"` | PASS, 776 tests |

Additional static coverage now locks the camera smoke path to QVGA/JPEG,
`video.frame_meta`, `/video` binary header/body send, and base64 fallback. It
also locks the mic path to INMP441 BCLK=39 WS=40 DIN=41, no mic read before
`/audio` connects, `audio.chunk_meta`, and PCM binary send.

The full `mergetesting` env is buildable. Keep the first real board pass split
by env anyway: `display_only` -> `cam_only` -> `mic_only` -> `face240_only`.
This isolates wiring and power faults that a combined firmware can hide.

## Hardware Agent Loop Result - 2026-06-26 Evening

This section records the real ESP32-S3 bring-up loop that followed the morning
preflight. The user powered the ESP32, enabled the phone hotspot/test WiFi,
connected USB on `COM19` when recovery was needed, then switched to external
power for motion and OTA testing.

### What Was Supposed To Be Completed

The intended loop was to finish the queued hardware tasks from `T07` onward:

| Task | Intended result |
| --- | --- |
| `T07` local config | `robot/mergetesting/src/config.local.h` exists, contains WiFi/base-station settings, and stays out of Git |
| `T08` base station | `python -m base_station.ws_server.server` listens on TCP 8765 |
| `T09` upload | Prefer OTA after one USB recovery/bootstrap if OTA is unavailable |
| `T10` `/control` | Robot connects, sends hello/status/heartbeat, and accepts commands |
| `T11` expression | `display.expression` gets robot ack; physical expression needs user confirmation |
| `T12` motion | `motion.execute` and `motion.completed` share `action_id`; stop interrupts safely |
| `T13` local sound | MAX98357A local `care_01` path plays sound |
| `T14` face240 | 2.4 inch face expression path works without watchdog reset |
| `T15` camera | OV2640 `/video` stream updates `runtime/latest.jpg` as valid JPEG |
| `T16` mic | INMP441 `/audio` stream emits PCM chunks without starving `/control` |
| full `mergetesting` | Only burn after split envs pass, so combined failures are not hidden |

### Completed Work

| Area | Status | Evidence |
| --- | --- | --- |
| Local config | `PASS/P` | `robot/mergetesting/src/config.local.h` exists and `git check-ignore -v robot/mergetesting/src/config.local.h` matches `.gitignore` |
| Base station | `PASS/H` | `python -m base_station.ws_server.server` ran as the active server; log file `runtime/logs/ws_server_20260626-154855.err.log`; TCP 8765 had established ESP32 connections |
| OTA route | `PASS/H` | USB recovery on `COM19` was used when needed; later OTA uploads to split envs completed with espota `Result: OK`, including camera-only and mic-only |
| `/control` smoke | `PASS/H` | Server log showed repeated `Robot connected: xiaoan_robot_01`; `python tools/send_robot_command.py --device-id xiaoan_robot_01 expression idle` returned `agent.ack ok` while mic streaming was active |
| Expression command path | `PASS/P` | Software path and robot ack passed; no final physical face/display observation was recorded in this loop, so no hardware H is claimed |
| Motion command path | `PASS/H` | Root cause fixed after hardware retest: invalid LEDC channels made motor PWM setup return `0 Hz`. After changing motor PWM channels to 4-7 and USB-uploading `mergetesting_motor_only`, raw pin tests confirmed GPIO1=left forward, GPIO2=left backward, GPIO3=right forward, GPIO48=right backward. Formal `move_out_of_dock`, `stop`, and `move_back_to_dock` commands returned ack/completed and the user confirmed physical direction/stop were correct |
| MAX98357A isolated hardware | `PASS/H` | `robot/firmware` `speaker_amp_test` was USB-flashed; user reported the speaker output was present and stable |
| MAX98357A mergetesting integration | `PASS/H` | After the lazy-I2S fix, `mergetesting_speaker_only` accepted USB and OTA burns; `/control -> audio.play_local` and mock `audio.play_tts` returned robot/server ack, heartbeats continued, and the user confirmed audible speaker output |
| OV2640 `/video` | `PASS/H` | `mergetesting_cam_only_ota` OTA succeeded; server logged `/control`, `/video`, `camera=cam_ok`, and continuous `Video meta: frame_id=N 320x240`; `runtime/latest.jpg` updated and had valid JPEG SOI/EOI bytes |
| INMP441 `/audio` | `PASS/H` | `mergetesting_mic_only_ota` OTA succeeded; server logged continuous `Audio meta: chunk_id=... format=pcm_s16le sample_rate=16000 channels=1`; `runtime/audio_stats.json` showed PCM chunks/bytes; `runtime/latest_audio.pcm` was 160000 bytes with RMS about 2464 and peak about 6466 |
| Control while audio streams | `PASS/H` | During `/audio`, `expression idle` still returned `agent.ack ok`; control channel was not starved by PCM streaming |
| face240 | `PASS/P` | Build had passed earlier, but this physical face240 loop was not completed or observed |
| full `mergetesting` | `NOT RUN` | Correctly deferred because split envs are not all H yet; speaker integration and face240 remain unresolved |

### Commands Actually Used During The Loop

Representative commands and outcomes:

```powershell
git status --short --branch
python -m unittest discover -s tests -p "test_*.py"
python tools/check_runtime_env.py
cd robot\mergetesting
pio run -e mergetesting_display_only_ota
pio run -e mergetesting_cam_only_ota
pio run -e mergetesting_mic_only
pio run -e mergetesting_mic_only_ota
pio run -e mergetesting_mic_only_ota -t upload --upload-port xiao-an-esp32.local
python -m base_station.ws_server.server
python tools\send_robot_command.py --device-id xiaoan_robot_01 expression idle
python tools\send_robot_command.py --device-id xiaoan_robot_01 motion move_out_of_dock --speed 0.15 --distance-cm 1 --timeout-ms 250
python tools\send_robot_command.py --device-id xiaoan_robot_01 motion stop
python tools\send_robot_command.py --device-id xiaoan_robot_01 motion move_back_to_dock --speed 0.15 --timeout-ms 250
Get-Item runtime\latest.jpg
Get-Content runtime\audio_stats.json
```

Notable result details:

- Full Python preflight passed earlier in the session: `python -m unittest discover -s tests -p "test_*.py"` ran `776` tests and passed.
- `python tools/check_runtime_env.py` exited successfully but reported warnings for missing optional OpenVINO/FunASR/ONNX/model runtime assets.
- `mergetesting_cam_only_ota` OTA succeeded and produced real `/video` evidence.
- `mergetesting_mic_only_ota` first failed because local host port `59755` was already bound/established to `127.0.0.1:7890`; retrying OTA succeeded. This was a host-side espota listen-port collision, not an ESP32 firmware failure.
- `runtime/latest_audio.pcm` read inspection briefly caused a server warning: `Permission denied: 'runtime\\latest_audio.pcm'`. That was caused by the local inspection holding the file while the server tried to rewrite it; audio streaming itself continued.

### Code And Config Changes Made For The Loop

These changes were made to keep the loop bounded and diagnosable:

- `tools/send_robot_command.py`: motion commands now accept `--speed`, `--distance-cm`, and `--timeout-ms`, allowing safe low-speed bench motion tests.
- `tests/unit/test_send_robot_command.py`: added coverage for the new motion safety parameters.
- `robot/mergetesting/platformio.ini`: added or refined split envs:
  - `mergetesting_control_base`
  - `mergetesting_control_ping`
  - `mergetesting_control_ping_ota`
  - `mergetesting_motor_only`
  - `mergetesting_motor_only_ota`
  - `mergetesting_speaker_only`
  - `mergetesting_speaker_only_ota`
  - `mergetesting_mic_only_ota`
- `robot/mergetesting/src/ws_client.cpp`: `/video` and `/audio` connection/loop work is now guarded by feature macros, so split envs do not open unused media channels.
- `robot/mergetesting/src/app/mergetesting_app.cpp`: loop now yields with a small delay to reduce starvation risk.
- `robot/mergetesting/src/speaker.cpp`: I2S writes now use a finite timeout and return failure when writes do not complete; speaker I2S is lazy-initialized on playback and released after playback so the WebSocket/OTA loop is not held in a long-lived TX state.
- `robot/mergetesting/src/app/mergetesting_app.cpp`: speaker init is no longer run during setup; `/control` audio commands open the speaker path only when needed.
- `robot/mergetesting/platformio.ini`: `mergetesting_speaker_only_ota` now passes `--host_ip=192.168.137.1` so ESP32 can connect back to the Windows hotspot host during OTA.
- `robot/mergetesting/src/motor_ctrl.cpp`: motor LEDC channels changed to valid ESP32-S3 Arduino channels 4-7 after serial showed `LEDC setup failed` and `freq=0 Hz` with the previous channel assignment.
- `tests/unit/test_mergetesting_layering.py`: added static coverage for split envs, OTA envs, optional media channels, speaker timeout/yield behavior, and mic-only OTA.

No protocol change was made. The existing message types remained `display.expression`,
`motion.execute`, `audio.play_local`, `video.frame_meta`, and `audio.chunk_meta`.

### Problems Found And How They Were Handled

1. OTA availability was not reliable at the beginning.
   - Symptom: OTA target was unavailable or the board was on a crashing image.
   - Handling: user connected USB on `COM19`; stable split firmware was burned over USB; then OTA was re-tested.
   - Result: later OTA uploads worked and were used for camera-only and mic-only verification.

2. External motor power and USB safety had to be separated.
   - Symptom: user correctly raised concern about testing motors while USB was connected and without external motor power.
   - Handling: motor tests were kept at low speed/short timeout and run only after the user confirmed the robot was externally powered and lifted.
   - Result: initial command-level motion passed but the wheels did not move, which led to a deeper raw-pin investigation.

3. Motor PWM did not actually output before the LEDC channel fix.
   - Symptom: server returned `command.ack` and `motion.completed`, but the user observed no physical motion.
   - Evidence: USB serial during `motor raw 255 0 0 0 1500` showed `[Motor] ERROR: LEDC setup failed` and `freq=0 Hz`.
   - Root cause: the motor PWM channel assignment used invalid LEDC channels for this ESP32-S3 Arduino core.
   - Fix: changed motor LEDC channels to 4, 5, 6, and 7 in `robot/mergetesting/src/motor_ctrl.cpp`; updated `tests/unit/test_mergetesting_layering.py`.
   - Verification: `python -m unittest tests.unit.test_mergetesting_layering` passed; `pio run -e mergetesting_motor_only` passed; USB upload to `COM19` passed; raw tests confirmed left/right forward/backward GPIO behavior; formal motion commands passed and the user confirmed physical direction and stop were correct.

4. `mergetesting_speaker_only` reset with watchdog, then was fixed.
   - Symptom: the robot could reach WiFi, OTA ready, I2S ready, and setup complete, then repeatedly reset with `rst:0x8 (TG1WDT_SYS_RST)` before a stable `/control` hello.
   - Evidence: USB serial on `COM19` repeatedly showed `Speaker I2S ready`, `Setup complete`, then TG1 watchdog reset. `addr2line` mapped the saved PC to the ESP panic handler, confirming a reset path rather than a server-only issue.
   - Root cause found in the integration pattern: the working `speaker_amp_test` initializes I2S and immediately plays tones, while mergetesting initialized I2S TX during setup and then left it open while the WebSocket/OTA loop idled.
   - Fix: removed setup-time `speaker_init()`, lazy-initialized I2S only inside `audio.play_local` / mock `audio.play_tts`, kept finite I2S write timeouts/yields, and uninstalled the I2S driver after each playback.
   - Verification: `python -m unittest ...test_speaker_i2s_is_lazy_and_released_between_playbacks` passed; `pio run -e mergetesting_speaker_only -t upload --upload-port COM19` passed; serial-held-open tests showed `care_01`, `wake_01`, `alarm_01`, and mock TTS all produced `command.ack ... -> ok` with heartbeats continuing afterward.

5. OTA had two separate failure modes.
   - Firmware failure mode: crashing speaker firmware only exposed a short OTA window, making OTA appear intermittent.
   - Host-network failure mode: PlatformIO defaulted espota to `host_ip=0.0.0.0`; on the Windows hotspot network the ESP32 did not reliably connect back to the host upload port.
   - Evidence: `pio run -e mergetesting_speaker_only_ota -t upload --upload-port 192.168.137.114` failed while debug showed `host_ip: 0.0.0.0`; direct `espota.py -I 192.168.137.1` succeeded; after adding `upload_flags = --host_ip=192.168.137.1`, PlatformIO OTA also succeeded.
   - Current rule: when using the Windows hotspot/base station at `192.168.137.1`, prefer OTA upload with explicit ESP IP plus host IP. `.local` mDNS may still fail on Windows, so use the ESP IP from serial/server logs when needed.

6. `mergetesting_mic_only_ota` first upload failed due host port collision.
   - Symptom: espota `Listen Failed` on local port `59755`.
   - Evidence: local Windows networking showed the port already bound/established to `127.0.0.1:7890`.
   - Handling: retry OTA rather than changing firmware.
   - Result: second upload succeeded and mic-only H passed.

7. Runtime audio file inspection raced the server writer.
   - Symptom: server logged one permission warning writing `runtime/latest_audio.pcm`.
   - Cause: local PowerShell byte inspection opened the file while the server was updating it.
   - Result: harmless for firmware; audio stats and subsequent chunk logs continued.

### Current Progress

| Feature | Current progress |
| --- | --- |
| Config/server/control foundation | Complete for this loop |
| OTA recovery path | Complete enough for split env iteration |
| Expression / face240 split path | Complete, H after user-observed display confirmation |
| Motion path | Complete, H after LEDC channel fix and physical confirmation |
| Speaker isolated hardware | Complete, H |
| Speaker mergetesting integration | Complete, H |
| Camera `/video` | Complete, H |
| Mic `/audio` | Complete, H |
| face240 physical path | Complete, H after syncing the updated `face240_roboeyes_test.cpp` visual design into `robot/mergetesting/src/face240_display.cpp`; user confirmed the displayed expression/layout was correct |
| full face240 combined firmware | PASS/P smoke: `mergetesting_full_face240_ota` builds/uploads by OTA; `/video` and `/audio` stream; `/control -> display.expression` and `/control -> audio.play_local` return firmware `command.ack` |

### Unfinished Work

- Split env hardware verification (T07–T16) is complete; machine-readable queue synced in `docs/agents/08_priority_queue_results.json`.
- Full `mergetesting` / `mergetesting_full_face240` combined firmware: software-smoke verified (build + OTA + `/control` ack + `/video` + `/audio`); final H for all subsystems together still pending (full-run speaker audible confirmation and full motor re-test in combined env).
- Phase 4 proactive care demo (video → OpenVINO → OpenClaw → three commands) not started.

### Late Full Face240 Smoke Update

- Synced the user's updated `robot/firmware/src/face240_roboeyes_test.cpp` visual implementation into `robot/mergetesting/src/face240_display.cpp` while preserving the mergetesting control wrapper (`face240_init`, `face240_emotion`, `face240_tick`, protocol mapping, and BL guard).
- Added `mergetesting_full_face240` and `mergetesting_full_face240_ota` envs for an explicit full integration target with face240, camera, motor, speaker, and mic enabled.
- Fixed full speaker command starvation/reset risk by making `speaker_play_local()` start a FreeRTOS playback task instead of blocking the `/control` loop, adding a short 100 ms playback delay so command ack can leave first, and reducing chime amplitude to lower full-load current spikes.
- Verification commands run:
  - `python -m unittest tests.unit.test_mergetesting_layering tests.unit.test_send_robot_command` -> 36 tests OK.
  - `pio run -e mergetesting_face240_only` -> SUCCESS.
  - `pio run -e mergetesting_face240_only_ota -t upload --upload-port 192.168.137.114` -> SUCCESS.
  - `pio run -e mergetesting_full_face240` -> SUCCESS.
  - `pio run -e mergetesting_full_face240_ota -t upload --upload-port 192.168.137.114` -> SUCCESS, espota `Result: OK`.
  - `python tools\send_robot_command.py expression caring` on full -> server logged `Command ack: type=display.expression status=ok`.
  - `python tools\send_robot_command.py local care_01` on full -> server logged `Command ack: type=audio.play_local status=ok`; latest human audible confirmation still pending.
  - Full `/audio` and `/video` evidence: server logged continuing `Audio meta: ... pcm_s16le` and `Video meta: ... 320x240`; `runtime/latest.jpg` and `runtime/latest_audio.pcm` updated.

### Next Steps

Split env H is complete. Next gate is combined firmware and Phase 4.

1. Burn and verify combined firmware (T17). Prefer `mergetesting_full_face240_ota` when the 2.4" face is connected:

```powershell
cd robot\mergetesting
pio run -e mergetesting_full_face240_ota -t upload --upload-port 192.168.137.114
python tools\send_robot_command.py --device-id xiaoan_robot_01 expression caring
python tools\send_robot_command.py --device-id xiaoan_robot_01 local care_01
python tools\send_robot_command.py --device-id xiaoan_robot_01 motion move_out_of_dock --speed 0.15 --distance-cm 1 --timeout-ms 250
```

Confirm audible speaker output and physical motion in the combined env. If the board resets, return to split envs.

2. Or burn legacy combined `mergetesting` (ST7735 display path):

```powershell
pio run -e mergetesting -t upload --upload-port COM19
```

3. Phase 4: wire real or mock emotion source to proactive care commands. See `docs/agents/06_integration_phases.md`.

## Split Env ALL_H Confirmation — 2026-06-26

User confirmed all mergetesting split env hardware verification is complete. Agent docs synced to match:

| Document | Update |
| --- | --- |
| `docs/agents/08_priority_queue_results.json` | T07–T16 marked PASS_H; `split_env_status: ALL_H`; next_order T17–T19 |
| `docs/agents/05_test_matrix.md` | All split env rows marked H with dates |
| `docs/agents/00_snapshot.md` | Progress table reflects split env ALL_H |
| `docs/agents/03_mergetesting_registry.md` | Env matrix H column + new split/full envs |

Split env evidence summary:

| Task | Env / path | Status |
| --- | --- | --- |
| T07 config | `config.local.h` | PASS_H |
| T08 base station | `ws_server` :8765 | PASS_H |
| T09–T10 control | `mergetesting_display_only` | PASS_H |
| T11 expression | `/control -> display.expression` | PASS_H |
| T12 motion | `mergetesting_motor_only` + LEDC 4–7 fix | PASS_H |
| T13 speaker | `mergetesting_speaker_only` lazy-I2S | PASS_H |
| T14 face240 | `mergetesting_face240_only` | PASS_H |
| T15 camera | `mergetesting_cam_only_ota` | PASS_H |
| T16 mic | `mergetesting_mic_only_ota` | PASS_H |

Remaining gate: combined `mergetesting` / `mergetesting_full_face240` hardware H, then Phase 4 end-to-end demo.

## Repository Cleanup — 2026-06-27

Integrator pass (Codex `01_session_protocol` §9). Details: `docs/agents/10_repo_map.md` §7.

| Action | Result |
| --- | --- |
| Delete `robot/firmware/.pio/`, `robot/mergetesting/.pio/` | Done — frees disk; rebuild with `pio run -e <env>` |
| Delete `robot/firmware/.cache/clangd/` | Done |
| Delete `runtime/` | Partial — WS server had log files locked; stop server then remove `runtime/` manually |
| Archive root `OPENFACE_XIAOAN_PROGRESS_HANDOFF.md` | Moved to `docs/archive/` |
| Archive `hardware_minimum_loop_route_2026-06-17.xml` | Moved to `docs/archive/` |
| `.gitignore` | Track `.agents/skills/**`; ignore `**/.cache/` |
| Registries | `02/03/04` expanded; `architecture.md` aligned with mergetesting video/audio |
| Auto inventory | `python tools/generate_agent_registry.py` — mergetesting now lists `app/` + `services/` |
