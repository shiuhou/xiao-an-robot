# Mergetesting → main firmware migration

`robot/mergetesting/` is a **DK-2500 integration fork**. Goal: fold validated modules into `robot/firmware/src/main.cpp` and retire duplicate sources.

## Status (2026-06-23)

| Module | Mergetesting | Main firmware | Action |
|--------|--------------|---------------|--------|
| `motor_ctrl` | ✅ | ✅ | Sync pulse timing from mergetesting |
| `ws_client` | ✅ 3-channel | ✅ `esp32-s3-integrated` | Use integrated env for DK-2500 |
| `cam_stream` | ✅ WS JPEG | ✅ integrated | `captureLoop(ws)` when video connected |
| `mic_stream` | ✅ PCM chunks | ✅ integrated | `streamLoop(ws)` when audio connected |
| `speaker` | ✅ | ✅ `peripherals/speaker` | Used by integrated + speaker_amp_test |
| `face240_display` | ✅ | ✅ `peripherals/face240_display` | Used by integrated_main |
| `display` (ST7735) | ✅ | ✅ | Main `/control` env only |

**Step 5:** `esp32-s3-integrated` replaces mergetesting for new DK-2500 burns. Keep `robot/mergetesting/` until hardware demo sign-off.

## Target layout

```text
robot/firmware/src/
├── main.cpp
├── peripherals/          # migrated from mergetesting
│   ├── speaker.cpp/h
│   ├── face240_display.cpp/h
│   └── ws_streams.cpp/h   # video + audio push helpers
└── feature_flags.h        # ENABLE_WS_VIDEO, ENABLE_WS_AUDIO
```

## Migration order

1. Copy `speaker.cpp/h` → `src/peripherals/`, compile under `speaker_amp_test` first.
2. Enable `ENABLE_WS_AUDIO` in a new env `esp32-s3-integrated` (extends main filter + mic/speaker).
3. Port `cam_stream` WS push from mergetesting `main.cpp` loop.
4. Port `face240_display` for `display.expression` on 2.4" ST7789.
5. When `esp32-s3-integrated` passes DK-2500 demo, mark `robot/mergetesting/` as archive.

## Verification

```powershell
cd robot\firmware
pio run -e esp32-s3-devkitc-1
cd ..\..
python tests/mocks/mock_robot.py   # /control
# After integrated env exists:
pio run -e esp32-s3-integrated
```

See also: `robot/mergetesting/EXTRACTION_MAP.md`, `docs/agents/03_mergetesting_registry.md`.
