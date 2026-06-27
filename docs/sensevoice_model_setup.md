# SenseVoice Model Setup

Step 43 reached the real ASR code path but could not run a real smoke because `base_station/models/sensevoice-small` was missing and `base_station/models/models_manifest.json` does not define SenseVoice or Silero downloads.

Step 43.1 standardizes SenseVoice on the public Hugging Face model:

```text
FunAudioLLM/SenseVoiceSmall
```

Local target path:

```text
base_station/models/sensevoice-small
```

The model directory is ignored by Git. Do not commit downloaded model files.

## Install Audio Requirements

```bash
.venv/bin/python -m pip install -r base_station/requirements-audio.txt
```

Do not use `sudo`, `apt install`, global pip, or broad dependency upgrades.

## Download Or Check

Step 43.1 uses a temporary audio model preparation tool because `tools/setup_models.py` currently requires a stable sha256 manifest for every file.

Download:

```bash
.venv/bin/python tools/setup_audio_models.py --only sensevoice_small
```

Check without network:

```bash
.venv/bin/python tools/setup_audio_models.py --only sensevoice_small --check
```

Inspect:

```bash
find base_station/models/sensevoice-small -maxdepth 2 -type f | sed -n '1,80p'
du -sh base_station/models/sensevoice-small
```

## Real SenseVoice No-Agent Smoke

Fake VAD:

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

Energy VAD:

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

Expected: `event_type=asr.transcript`, `asr.backend=sensevoice`, non-empty text, and `vad.speech_detected=true` for energy VAD.

## OpenClaw And mock_robot Loop

Run only after the no-agent smoke returns non-empty real ASR text.

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

Query the Local Event Store:

```bash
curl "http://127.0.0.1:8787/api/memory/recent?event_type=companion.request&limit=10"
curl "http://127.0.0.1:8787/api/tool-runs?limit=10"
curl "http://127.0.0.1:8787/api/status"
```

If ASR text contains `累`, the expected route is `link_3_companion_fast_path` with `openclaw_event_type=companion.request`. If the text does not contain `累`, record the actual text and route; do not lower production keyword thresholds just to pass.

## Silero Status

Step 43.1 does not require real Silero. Step 43.2 wires real Silero for local
WAV smoke through the `silero-vad` pip package and `load_silero_vad`; no
separate Silero model file is required for that route.

See `docs/silero_vad_audio_file_smoke.md`.

## Common Errors

- HF access failed: check network, proxy, Hugging Face availability, disk space, and `HF_TOKEN` only if the hub asks for authentication.
- Model directory empty: rerun the download; an empty directory is not a model.
- Missing `funasr`: install `base_station/requirements-audio.txt`.
- Torch/torchaudio version issue: verify both import inside `.venv`; do not use global pip.
- ASR empty text: runtime returns `asr.empty_transcript`; use clearer real speech audio.
- ASR text lacks `累`: record the text and use a clearer `audio_tired.wav`; do not change thresholds.
- WAV format incorrect: use 16 kHz mono PCM WAV where possible.
