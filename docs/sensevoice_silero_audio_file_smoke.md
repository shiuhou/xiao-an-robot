# SenseVoice Silero Audio File Smoke

Step 43 prepares real audio-file ASR/VAD dependencies and verifies local WAV inference without touching live hardware.

## Boundary

This step only uses `--source audio_file`. Do not connect a real microphone, ESP32, firmware flashing, real camera, real TTS hardware, or screen monitoring.

No command here downloads SenseVoice or Silero models automatically. Real model files must already exist in an ignored local model directory.

## Dependency Probe

```bash
.venv/bin/python - <<'PY'
mods = [
    "funasr",
    "torch",
    "torchaudio",
    "numpy",
    "soundfile",
    "librosa",
]
for m in mods:
    try:
        mod = __import__(m, fromlist=["*"])
        print(f"OK {m}: {getattr(mod, '__version__', 'unknown')}")
    except Exception as e:
        print(f"MISSING {m}: {type(e).__name__}: {e}")
PY
```

## Install Audio Dependencies

```bash
.venv/bin/python -m pip install -r base_station/requirements-audio.txt
```

Use only the project `.venv`. Do not use `sudo`, `apt install`, global pip, or broad dependency upgrades.

## Model Directories

Preferred local paths:

```text
base_station/models/sensevoice-small
base_station/models/silero-vad
```

External local paths are also acceptable:

```text
~/models/sensevoice-small
~/models/silero-vad
```

The SenseVoice path must be an existing non-empty directory. The optional Silero path used by the CLI must be an existing model file such as:

```text
base_station/models/silero-vad/silero_vad.jit
```

Empty directories are not valid models.

## Test WAV

Use a local, ignored WAV file:

```text
runtime/manual_samples/audio_tired.wav
```

Recommended format: 16 kHz, mono, PCM WAV. Recommended Mandarin content: `我有点累`.

If this file is synthetic audio or does not contain real speech, do not claim real ASR semantic smoke passed.

## Fake VAD And Real SenseVoice

```bash
.venv/bin/python -m base_station.monitor.asr_runtime \
  --source audio_file \
  --audio-path runtime/manual_samples/audio_tired.wav \
  --vad-backend fake \
  --vad-pattern speech \
  --asr-backend sensevoice \
  --asr-model-path base_station/models/sensevoice-small \
  --no-agent \
  --verbose
```

Expected: `event_type=asr.transcript`, `asr.backend=sensevoice`, and non-empty real ASR text. If the model path is missing or empty, the command must fail clearly.

## Energy VAD And Real SenseVoice

```bash
.venv/bin/python -m base_station.monitor.asr_runtime \
  --source audio_file \
  --audio-path runtime/manual_samples/audio_tired.wav \
  --vad-backend energy \
  --vad-threshold 0.01 \
  --asr-backend sensevoice \
  --asr-model-path base_station/models/sensevoice-small \
  --no-agent \
  --verbose
```

Expected: `vad.speech_detected=true`, `asr.backend=sensevoice`, and non-empty real ASR text.

## Optional Silero And SenseVoice

Silero is optional for Step 43. If the exact Silero model format is not wired, use energy VAD for the real SenseVoice smoke.

```bash
.venv/bin/python -m base_station.monitor.asr_runtime \
  --source audio_file \
  --audio-path runtime/manual_samples/audio_tired.wav \
  --vad-backend silero \
  --vad-model-path base_station/models/silero-vad/silero_vad.jit \
  --asr-backend sensevoice \
  --asr-model-path base_station/models/sensevoice-small \
  --no-agent \
  --verbose
```

Expected for the current shell path: clear failure if `--vad-model-path` is missing. Do not treat fake or energy VAD as a successful Silero model test.

## OpenClaw And mock_robot Loop

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
  --vad-backend energy \
  --vad-threshold 0.01 \
  --asr-backend sensevoice \
  --asr-model-path base_station/models/sensevoice-small \
  --gateway-url ws://127.0.0.1:8765/agent \
  --verbose
```

Passing criteria:

- `vad.speech_detected=true`
- `asr.backend=sensevoice`
- ASR text contains `累`, or naturally triggers the local fatigue companion path
- `event_type=asr.transcript`
- `route=link_3_companion_fast_path`
- `openclaw_event_type=companion.request`
- `mock_robot` receives at least one display, motion, or TTS command
- Local Event Store contains `companion.request` and recent tool runs

## Local Event Store Queries

```bash
curl "http://127.0.0.1:8787/api/memory/recent?event_type=companion.request&limit=10"
curl "http://127.0.0.1:8787/api/tool-runs?limit=10"
curl "http://127.0.0.1:8787/api/status"
```

## Common Issues

- Missing `funasr`: install `base_station/requirements-audio.txt` into `.venv`.
- Missing `torch`: install `base_station/requirements-audio.txt` into `.venv`; do not use global pip.
- SenseVoice `model_dir` missing: place a real local model in an ignored path and pass `--asr-model-path`.
- SenseVoice `model_dir` empty: an empty directory is not a model.
- Silero `model_path` missing: pass a real local Silero file, or use energy VAD for Step 43.
- ASR empty text: runtime returns `asr.empty_transcript` and does not emit `asr.transcript`.
- ASR text lacks `累`: do not lower keyword thresholds just to pass; record the text and use clearer audio.
- WAV is not PCM: convert to 16 kHz mono PCM WAV before running this smoke.
- OpenClaw Gateway is not running: companion events cannot reach `xiaoan-runtime`.
- `mock_robot` offline: the loop can route but no robot action is acknowledged.

## Do Not Commit

Do not commit models, audio samples, `runtime/`, databases, logs, `.venv`, `frontend/dist`, or `node_modules`.
