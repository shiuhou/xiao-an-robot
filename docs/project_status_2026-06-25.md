# Project Status 2026-06-25

This snapshot records the OTA bootstrap addition and the first successful wireless upload test. It does not replace the broader 2026-06-22 hardware status.

## Firmware OTA Bootstrap

| Env | Status | Purpose |
| --- | --- | --- |
| `ota_bootstrap` | Hardware-verified | First USB-flashed WiFi OTA bridge |
| `ota_bootstrap_wifi` | Hardware-verified | Wireless upload target after `ota_bootstrap` is running |

Source files:

- `robot/firmware/src/ota_bootstrap_main.cpp`: WiFi STA bootstrap, motor pins held low, status logs.
- `robot/firmware/src/ota_update.cpp/h`: small ArduinoOTA wrapper.
- `robot/firmware/src/config.local.example.h`: local config template.
- `robot/firmware/src/config.local.h`: ignored local secrets file.

Verified hardware result on 2026-06-25:

- Board: ESP32-S3 on `COM19`, MAC `28:84:85:54:24:b4`.
- Network: Windows hotspot / same-LAN WiFi model. The tested board IP was `192.168.137.197`.
- Serial confirmation after USB flash: `[OTA_BOOT] WiFi connected IP=192.168.137.197`, `[OTA] Ready hostname=xiao-an-esp32 auth=disabled`, and repeated `alive` logs.
- Wireless OTA confirmation: `pio run -e ota_bootstrap_wifi -t upload --upload-port 192.168.137.197` completed with espota `Result: OK` and `Success`.
- Post-OTA serial confirmation: the board rebooted and rejoined WiFi at `192.168.137.197`.

Network rule:

- The robot and base station do not need the PC hotspot specifically. They need to be on the same reachable network segment.
- A Windows hotspot is the current known-good route because the PC is usually `192.168.137.1` and the ESP32 receives `192.168.137.x`.
- A public/shared WiFi can work only if it does not isolate clients and does not block the ESP32 OTA port (`3232`) or the base-station WebSocket ports.
- Do not commit real WiFi credentials. Put them only in ignored `robot/firmware/src/config.local.h`.

Validation commands:

```powershell
python -m unittest tests.unit.test_firmware_ota_bootstrap
cd robot\firmware
pio run -e ota_bootstrap
pio run -e ota_bootstrap_wifi
```

First hardware flow:

```powershell
cd robot\firmware
pio run -e ota_bootstrap -t upload --upload-port COMxx
pio run -e ota_bootstrap_wifi -t upload --upload-port <board-ip>
```

Agent handoff rule for OTA uploads:

- `ota_bootstrap_wifi` is not a generic "upload any firmware" env. It only compiles and uploads `ota_bootstrap_main.cpp`.
- To wirelessly upload a functional env such as `mergetesting_cam_only`, `motor_cam_wifi_manual`, or `face240_9expr_merged`, create/use a matching OTA upload env for that firmware.
- The firmware being uploaded must itself preserve OTA support after reboot: connect to WiFi, enable ArduinoOTA, and call the OTA loop regularly. If it does not, the OTA bridge is overwritten and the next recovery path is USB.
- A future pattern should be `<env>_wifi` or `<env>_ota` with `upload_protocol = espota` plus that firmware's normal source set and OTA runtime support. Do not point agents at `ota_bootstrap_wifi` unless the goal is to refresh the bootstrap bridge itself.

Known-good command sequence from the first successful test:

```powershell
cd robot\firmware
pio run -e ota_bootstrap -t upload --upload-port COM19
pio run -e ota_bootstrap_wifi -t upload --upload-port 192.168.137.197
```

## OTA Camera Minimum Loop

Verified hardware result on 2026-06-25:

- Base station PC/hotspot IP: `192.168.137.1`; ESP32 IP: `192.168.137.197`.
- Firmware env: `robot/mergetesting`, `mergetesting_cam_only_ota`.
- Build: `pio run -e mergetesting_cam_only_ota` completed successfully.
- Wireless upload: `pio run -e mergetesting_cam_only_ota -t upload --upload-port 192.168.137.197` completed with espota `Result: OK`.
- Runtime result: ESP32 connected `/control`, `/video`, and `/audio`; serial showed `Camera ready QVGA320` and continuous `frame #... 320x240`.
- Base-station result: `python -u -m base_station.ws_server.server` accepted the robot and saved `runtime/latest.jpg`.

Important finding:

- The initial camera OTA image reset under watchdog during camera init when the integration build still enabled extra peripherals and VGA settings.
- The stable smoke target is now true camera-only: `MERGETEST_ENABLE_CAMERA=1`, display/motor/speaker/mic disabled, and QVGA enabled by `MERGETEST_CAMERA_USE_VGA=0`.
- If the board is already running a crashing functional image, recover by USB-flashing `ota_bootstrap`, then OTA-upload `mergetesting_cam_only_ota` again.

No wiring assumptions changed. The bootstrap only uses WiFi plus the existing DRV8833 motor GPIO constants so the wheels stay inactive during OTA.
