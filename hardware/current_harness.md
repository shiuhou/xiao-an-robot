# Current Hardware Harness

Updated: 2026-06-30.

This is the quick hardware entry point for the current Xiao An bench/integrated
harness. The detailed canonical pin table remains
[wiring/esp32_pinout.md](wiring/esp32_pinout.md).

## Current Demo Target

| Area | Current path |
| --- | --- |
| Main firmware | `robot/mergetesting` |
| Full demo env | `mergetesting_full_face240` |
| Face-only check | `mergetesting_face240_only` |
| Camera check | `mergetesting_cam_only` |
| Mic ASR calibration | `mergetesting_mic_only_shift18_asr` |
| Shared mic/speaker diagnostic | `mergetesting_audio_shared_i2s_diag` |
| Reliable audible demo | `audio.play_local care_01` |

`robot/firmware` remains the isolated bring-up lab. Do not add new DK-2500
`/control`, `/video`, or `/audio` integration entrypoints there.

## Current Wiring Summary

| Subsystem | Current wiring |
| --- | --- |
| TFT face240 | ST7789 integrated map: SCK=14, MOSI=21, CS=42, DC=43, RST=44, BL tied to 3V3 or `TFT_BL=-1`. |
| Camera | GOOUUU OV2640 FPC map; do not repin DVP signals. |
| Motor | DRV8833: left IN1/IN2=GPIO1/GPIO2, right IN1/IN2=GPIO3/GPIO48. Motor VM comes from battery, not 5V distribution. |
| Mic | INMP441: BCLK=39, WS=40, SD=41, VDD=3V3. |
| Speaker candidate | MAX98357A shared-clock diagnostic: BCLK=39, WS=40, DIN=47, VIN=5V. |
| Power | Wireless receiver -> charge board -> 5V distribution; common ground across ESP32/TFT/DRV8833/mic/amp. |

## Avoid / Legacy

| Item | Status |
| --- | --- |
| MAX98357A on GPIO35/36/37 | Avoid on the current ESP32-S3 Octal PSRAM module; 2026-06-29 diagnostics hit WDT reset at embedded PCM first write. |
| Legacy TFT GPIO9/10/11/12 | Old bench harness only; conflicts with OV2640 camera pins. |
| `esp32-s3-integrated_legacy` | Historical firmware-side DK-2500 integration snapshot; use `robot/mergetesting` for new burns. |
| `voice_recognition_test` | INMP441 electrical/RMS test only, not real ASR. |
| `speaker_amp_test` | Robot-body amp smoke only; verify pins before use. |

## First Checks

```powershell
cd robot\mergetesting
pio run -e mergetesting_face240_only
pio run -e mergetesting_cam_only
pio run -e mergetesting_mic_only_shift18_asr
```

Raw mic audio check:

```powershell
python -m base_station.perception.audio_diagnostics runtime\latest_audio.pcm --wav-out runtime\manual_samples\mic_20cm.wav --report-out runtime\manual_samples\mic_20cm_stats.json
```

Fixed-window ASR check:

```powershell
python -m base_station.monitor.asr_runtime --source audio_file --audio-path runtime\manual_samples\mic_20cm.wav --asr-backend sensevoice --asr-model-path base_station\models\sensevoice-small --trim-speech --no-agent --verbose
```

## Related References

- [wiring/esp32_pinout.md](wiring/esp32_pinout.md)
- [wiring/power.md](wiring/power.md)
- [wiring/motor_driver.md](wiring/motor_driver.md)
- [../docs/current_status.md](../docs/current_status.md)
- [../docs/setup/hardware_setup.md](../docs/setup/hardware_setup.md)
