# ASR VAD Audio File Smoke

Step 42 verifies the software voice-input chain before real microphone or real ASR/VAD model work. The path is:

```text
audio_file or fake input -> VAD -> ASR -> asr.transcript -> XiaoAnBrain/OpenClaw -> mock_robot
```

This step does not use a real microphone, ESP32, firmware flashing, real camera, real TTS hardware, or screen monitoring.

## Raw Mic WAV First

Do not debug ASR before the raw INMP441 recording is listenable. For real
hardware, start the base station, flash/use `mergetesting_mic_only`, then record
the `/audio` PCM that the server writes to `runtime/latest_audio.pcm`.

Recommended capture set:

```text
1. quiet room, no speech, 5 seconds
2. normal speech at 20 cm, 10 seconds
3. normal speech at 50 cm, 10 seconds
4. speak while the robot speaker is playing, 10 seconds
```

Convert the latest bounded PCM window to WAV and write a JSON report:

```powershell
python -m base_station.perception.audio_diagnostics runtime\latest_audio.pcm --wav-out runtime\manual_samples\mic_20cm.wav --report-out runtime\manual_samples\mic_20cm_stats.json
```

Default format assumptions are `pcm_s16le`, 16000 Hz, mono. The report includes
RMS dBFS, peak dBFS, clipping percentage, DC offset, sample count, and duration.
The WebSocket server also mirrors these fields under
`runtime/audio_stats.json` as `latest_window`.

Treat the result as the layer split:

- 20 cm WAV clear but ASR bad: investigate ASR, language, VAD segmentation, or preprocessing.
- 20 cm WAV noisy, distorted, tiny, or wrong speed: investigate I2S format, INMP441 shift, sample rate, channel, byte order, power, wiring, or acoustics.
- Quiet-room RMS high: investigate noise, power, or gain.
- Speech peak stuck near 0 dBFS or `clipping_percent` above 0: reduce gain or revisit the 32-bit to 16-bit shift.
- Speaker playback breaks recognition: use half-duplex first; pause mic/ASR while robot audio is playing before attempting AEC.

## Current Boundary

- `audio_file` reads a local PCM WAV file.
- `fake` VAD and fake ASR are the default smoke backends.
- `energy` VAD is a simple local threshold backend with no model dependency.
- Step 42 introduced fake/energy audio-file smoke.
- Step 43.1 verified real SenseVoice audio-file ASR.
- Step 43.2 verifies real Silero VAD through the `silero-vad` pip package.
  The Silero pip route does not require `--vad-model-path`; it uses the package
  model loaded by `load_silero_vad`.
- Tests generate temporary WAV files and do not commit audio samples.

## Legacy Pattern And Text

```bash
.venv/bin/python -m base_station.monitor.asr_runtime --pattern tired --verbose
.venv/bin/python -m base_station.monitor.asr_runtime --text "我有点累" --verbose
```

## No-Agent Audio File Smoke

```bash
.venv/bin/python -m base_station.monitor.asr_runtime \
  --source audio_file \
  --audio-path runtime/manual_samples/audio_tired.wav \
  --vad-backend fake \
  --vad-pattern speech \
  --asr-backend fake \
  --fake-transcript "我有点累" \
  --no-agent \
  --verbose
```

Expected: `asr.transcript` output with `source=audio_file`, `vad.speech_detected=true`, and fake ASR text.

## Companion Request Loop

Terminal 1:

```bash
.venv/bin/python -m base_station.ws_server.server
```

Terminal 2:

```bash
.venv/bin/python tests/mocks/mock_robot.py --host 127.0.0.1 --port 8765
```

Terminal 3:

```bash
XIAO_AN_OPENCLAW_BACKEND=gateway \
XIAO_AN_OPENCLAW_GATEWAY_URL=ws://127.0.0.1:18789 \
XIAO_AN_OPENCLAW_AGENT=xiaoan-runtime \
.venv/bin/python -m base_station.api.server \
  --host 127.0.0.1 \
  --port 8787 \
  --db-path agent/data/xiao_an.db \
  --verbose
```

Terminal 4:

```bash
XIAO_AN_OPENCLAW_BACKEND=gateway \
XIAO_AN_OPENCLAW_GATEWAY_URL=ws://127.0.0.1:18789 \
XIAO_AN_OPENCLAW_AGENT=xiaoan-runtime \
.venv/bin/python -m base_station.monitor.asr_runtime \
  --source audio_file \
  --audio-path runtime/manual_samples/audio_tired.wav \
  --vad-backend fake \
  --vad-pattern speech \
  --asr-backend fake \
  --fake-transcript "我有点累" \
  --gateway-url ws://127.0.0.1:8765/agent \
  --verbose
```

Expected: `asr.transcript` enters the companion fast path, OpenClaw receives `companion.request`, and mock robot receives at least one care action or speech command.

## Daily Voice Interaction Loop

```bash
XIAO_AN_OPENCLAW_BACKEND=gateway \
XIAO_AN_OPENCLAW_GATEWAY_URL=ws://127.0.0.1:18789 \
XIAO_AN_OPENCLAW_AGENT=xiaoan-runtime \
.venv/bin/python -m base_station.monitor.asr_runtime \
  --source audio_file \
  --audio-path runtime/manual_samples/audio_normal.wav \
  --vad-backend fake \
  --vad-pattern speech \
  --asr-backend fake \
  --fake-transcript "你好小安" \
  --gateway-url ws://127.0.0.1:8765/agent \
  --verbose
```

Expected: `asr.transcript` goes through the normal OpenClaw route and mock robot receives a reply speech command.

## No Speech

```bash
.venv/bin/python -m base_station.monitor.asr_runtime \
  --source audio_file \
  --audio-path runtime/manual_samples/audio_silence.wav \
  --vad-backend fake \
  --vad-pattern silence \
  --asr-backend fake \
  --fake-transcript "这句话不应该被发送" \
  --no-agent \
  --verbose
```

Expected: `asr.no_speech`, `vad.speech_detected=false`, ASR is not executed, and OpenClaw is not initialized.

## Local Event Store Queries

```bash
curl "http://127.0.0.1:8787/api/memory/recent?event_type=companion.request&limit=10"
curl "http://127.0.0.1:8787/api/tool-runs?limit=10"
curl "http://127.0.0.1:8787/api/status"
```

## Common Issues

- `audio file missing`: create a local WAV file or use a temporary generated file for smoke.
- `VAD no speech`: fake VAD `silence` intentionally skips ASR and emits `asr.no_speech`.
- `ASR empty transcript`: the runtime returns `asr.empty_transcript` and does not send `asr.transcript`.
- `SenseVoice dependency missing`: Step 42 only provides the shell; install and wire real dependencies in a separate confirmed step.
- `Silero dependency missing`: Step 42 only provides the shell; no model download happens automatically.
- `OpenClaw Gateway not running`: agent mode cannot deliver `companion.request` or normal ASR events to `xiaoan-runtime`.
- `mock_robot offline`: tool runs may fail or no robot action will be acknowledged.

For the real Silero + real SenseVoice audio-file smoke, see
`docs/testing/smoke/silero_vad_audio_file_smoke.md`.

Do not commit `runtime/manual_samples` audio, model files, databases, logs, `.venv`, `frontend/dist`, or `node_modules`.
