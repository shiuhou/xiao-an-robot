# 2026-07-04 OpenClaw P0 Preflight Status

## Baseline

Use this baseline before connecting the real OpenClaw decision loop:

```powershell
$env:XIAOAN_CONTROL_TTS_STREAM='1'
$env:XIAOAN_TTS_TARGET_PEAK='800'
$env:XIAOAN_TTS_VOICE='Microsoft Hanhan Desktop'
python -m base_station.ws_server.server
```

Robot firmware:

```text
env: mergetesting_care_demo_face240_spoken_tts_din41
device_id: xiaoan_robot_01
speaker pins: BCLK=39, LRC=40, DIN=41
ESP stream gain: MERGETEST_SPEAKER_STREAM_GAIN=32
```

## Result

`python tools\run_openclaw_preflight_p0.py --device-id xiaoan_robot_01` passed
P0-1 through P0-8 on COM23.

Evidence:

```text
P0-1 Robot online: PASS
P0-2 TTS intro: audio.play_tts accepted; playback_done ok; bytes_written=75750
P0-3 TTS arbitrary sentence: playback_done ok; bytes_written=69872
P0-4 TTS fallback phrase: playback_done ok; bytes_written=71562
P0-5 Local wake_01: command.ack status=ok
P0-6 Face thinking: command.ack status=ok
P0-7 Face speaking: command.ack status=ok
P0-8 Stop motion: command.ack status=ok; detail=stopped
```

## Notes

- The base station and ESP `/agent -> /control -> robot event` loop is ready
  for the next OpenClaw integration gate.
- This PC does not currently have a zh-CN SAPI voice. `Microsoft Hanhan
  Desktop` is the temporary Mandarin-compatible fallback; avoid zh-HK voices
  for the public demo.
- Speech quality is acceptable only as a sprint baseline. If time permits,
  replace SAPI with a higher-quality Mandarin TTS backend while keeping the
  same `/agent -> audio.play_tts -> audio.playback_done` acceptance standard.
