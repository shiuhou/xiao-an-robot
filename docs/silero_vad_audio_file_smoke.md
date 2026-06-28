# Silero VAD Audio File Smoke

Step 43.2 verifies real Silero VAD on a local WAV file, then sends detected
speech through real SenseVoice ASR and the existing OpenClaw + mock_robot loop.

This step is audio-file only. Do not connect a real microphone, ESP32, firmware,
real camera, real TTS hardware, or screen monitoring.

## Silero Route

Use the `silero-vad` pip package. This is preferred over `torch.hub` because it
is installed into the project `.venv`, does not fetch GitHub code at runtime,
and exposes `load_silero_vad`, `read_audio`, and `get_speech_timestamps`.

Step 43.2 uses the package model through `load_silero_vad`; no separate Silero
model file is required.

## Install

```bash
.venv/bin/python -m pip install -r base_station/requirements-audio.txt
```

Do not use `sudo`, `apt install`, global pip, or broad dependency upgrades.

## Dependency Probe

```bash
.venv/bin/python - <<'PY'
mods = [
    "silero_vad",
    "torch",
    "torchaudio",
    "soundfile",
    "numpy",
    "funasr",
]
for m in mods:
    try:
        mod = __import__(m, fromlist=["*"])
        print(f"OK {m}: {getattr(mod, '__version__', 'unknown')}")
    except Exception as e:
        print(f"MISSING {m}: {type(e).__name__}: {e}")
PY
```

## Real Silero And Real SenseVoice No-Agent

```bash
.venv/bin/python -m base_station.monitor.asr_runtime \
  --source audio_file \
  --audio-path runtime/manual_samples/audio_tired.wav \
  --vad-backend silero \
  --vad-threshold 0.5 \
  --asr-backend sensevoice \
  --asr-model-path base_station/models/sensevoice-small \
  --no-agent \
  --verbose
```

Expected: `event_type=asr.transcript`, `vad.backend=silero`,
`vad.speech_detected=true`, non-empty `vad.timestamps`,
`asr.backend=sensevoice`, and non-empty ASR text.

## Silence No-Speech

Create a temporary silence WAV outside the repo:

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
import wave
path = Path("/tmp/xiaoan_silence.wav")
frames = b"\x00\x00" * 16000
with wave.open(str(path), "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(16000)
    wav.writeframes(frames)
print(path)
PY
```

Run:

```bash
.venv/bin/python -m base_station.monitor.asr_runtime \
  --source audio_file \
  --audio-path /tmp/xiaoan_silence.wav \
  --vad-backend silero \
  --vad-threshold 0.5 \
  --asr-backend sensevoice \
  --asr-model-path base_station/models/sensevoice-small \
  --no-agent \
  --verbose
```

Expected: `event_type=asr.no_speech`, `vad.backend=silero`,
`vad.speech_detected=false`, and no ASR result.

## OpenClaw And mock_robot Loop

Run only after the no-agent command returns non-empty real SenseVoice text.

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
  --vad-backend silero \
  --vad-threshold 0.5 \
  --asr-backend sensevoice \
  --asr-model-path base_station/models/sensevoice-small \
  --gateway-url ws://127.0.0.1:8765/agent \
  --verbose
```

If the text contains `累`, the expected route is
`link_3_companion_fast_path`, `openclaw_event_type=companion.request`, and
mock_robot should receive at least one of `display.expression`,
`motion.execute`, or `audio.play_tts`.

## Local Event Store Queries

```bash
curl "http://127.0.0.1:8787/api/memory/recent?event_type=companion.request&limit=10"
curl "http://127.0.0.1:8787/api/tool-runs?limit=10"
curl "http://127.0.0.1:8787/api/status"
```

## Common Issues

- `silero_vad import failed`: install `base_station/requirements-audio.txt`
  into `.venv`; do not use global pip.
- `torch/torchaudio version mismatch`: verify imports inside `.venv`; do not
  change Torch versions casually because SenseVoice depends on the same stack.
- `unsupported sample rate`: convert the WAV to 16 kHz mono PCM. The Silero
  backend accepts only 8000 Hz or 16000 Hz.
- `unsupported sample width`: use 16-bit PCM WAV.
- `Silero no speech`: ASR is intentionally skipped and `asr.no_speech` is
  emitted. Check WAV clarity, format, and threshold; do not fake success with
  energy VAD.
- `SenseVoice empty text`: use clearer speech audio and keep the real
  `sensevoice` backend.
- `ASR text lacks 累`: record the actual text and route; do not lower keyword
  thresholds just to force companion fast path.
- `OpenClaw Gateway not running`: `xiaoan-runtime` cannot handle
  `companion.request`.
- `mock_robot offline`: robot action acknowledgements will be missing.

Do not commit audio samples, models, runtime files, databases, logs, `.venv`,
`frontend/dist`, or `node_modules`.
