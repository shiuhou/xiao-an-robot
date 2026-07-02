# Demo 1 USB Mic To Agent Screen

## Goal

Demo 1 proves the first public-demo voice loop:

```text
DK-2500 / base-station USB microphone
-> fixed-window WAV recording
-> existing ASR runtime
-> runtime/demo1_transcript.json
-> runtime/demo1_transcript.txt
-> local Agent screen page
```

This is not the full private assistant. It does not require robot firmware,
`/control`, `/video`, robot motion, reminders, long-term memory, or complex
OpenClaw tool calls.

## Hardware

- Plug the USB microphone into the DK-2500 / base-station.
- Keep the microphone selected as an input-capable device in the OS.
- The robot INMP441 `/audio` path is a fallback/diagnostic path, not the primary
  Demo 1 input.

## List Microphone Devices

From the repo root:

```bash
.venv/bin/python tools/demo/demo1_usb_mic_to_agent_screen.py --list-devices
```

Pick the USB microphone index or a unique name fragment for `--device`.
The PyAudio numeric index can change between runs, so prefer the name fragment:

```text
--device USB
```

## Run Real ASR Demo

The real ASR path records a 5-second WAV, calls the existing
`base_station.monitor.asr_runtime` audio-file path, writes
`runtime/demo1_transcript.txt` and `runtime/demo1_transcript.json`, appends
`runtime/demo1_transcript.log.jsonl`, and keeps a local screen page open.

One-command run:

```bash
tools/demo/run_demo1_mic_asr.sh
```

One-command text-file check that exits:

```bash
tools/demo/run_demo1_mic_asr.sh --once --no-screen
```

Equivalent expanded command:

```bash
.venv/bin/python tools/demo/demo1_usb_mic_to_agent_screen.py \
  --device USB \
  --duration 5 \
  --asr-backend sensevoice \
  --asr-model-path base_station/models/sensevoice-small
```

Open:

```text
http://localhost:8766
```

For a one-shot CLI check that exits after writing JSON:

```bash
.venv/bin/python tools/demo/demo1_usb_mic_to_agent_screen.py \
  --device USB \
  --duration 5 \
  --asr-backend sensevoice \
  --asr-model-path base_station/models/sensevoice-small \
  --once
```

## Run Mock Fallback

Use this when the microphone, PyAudio, FunASR, or SenseVoice model is not ready.
This does not pretend to be real ASR: the JSON/log source is `mock`.

One-command fallback:

```bash
tools/demo/run_demo1_mic_mock.sh
```

```bash
.venv/bin/python tools/demo/demo1_usb_mic_to_agent_screen.py \
  --mock-text "帮我记一下，今晚八点修改报告第三章"
```

One-shot mock check:

```bash
.venv/bin/python tools/demo/demo1_usb_mic_to_agent_screen.py \
  --mock-text "帮我记一下，今晚八点修改报告第三章" \
  --once
```

## Screen Page

The page shows:

- `小安 Demo 1：基站麦克风语音识别`
- status: `idle`, `listening`, `transcribing`, `done`, or `error`
- latest transcript
- timestamp
- audio device name
- error message

API state is also available at:

```text
http://localhost:8766/api/demo1/transcript
```

## Logs And Evidence

The demo writes:

```text
runtime/demo1_transcript.json
runtime/demo1_transcript.txt
runtime/demo1_transcript.log.jsonl
runtime/demo1_audio/demo1_usb_mic_*.wav
```

`source` must be interpreted honestly:

- `asr`: transcript came from the ASR backend.
- `mock`: transcript came from `--mock-text` or fake ASR fallback.

## Troubleshooting

- No devices listed: verify the USB mic is plugged into DK-2500 and that PyAudio
  is installed in `.venv`.
- Device not selected: pass `--device "USB"` or the current PyAudio USB index
  shown by `--list-devices`.
- `hw:1,0` records silence but the PyAudio USB device works: use
  `--device "USB"`; on the checked DK-2500 this PyAudio path recorded valid
  audio at 48 kHz.
- ASR backend unavailable: check `funasr` and the local model directory, or run
  the mock fallback command.
- Empty transcript: try speaking closer to the mic, increase `--duration`, or
  adjust `--speech-trim-threshold`.
- Page does not open: check whether port `8766` is occupied; pass another
  `--port`.
- JSON updates but page is stale: open `/api/demo1/transcript` directly and
  refresh the browser.

## Acceptance Criteria

1. The command can list input-capable audio devices.
2. A selected USB mic can record a fixed-window WAV.
3. The real ASR path calls existing `asr_runtime` and writes an `asr` transcript,
   or the mock fallback writes a clearly labeled `mock` transcript.
4. `runtime/demo1_transcript.json` contains status, transcript, timestamp,
   device, source, and error fields.
5. `runtime/demo1_transcript.txt` contains the latest recognized text.
6. `http://localhost:8766` clearly displays the latest transcript.
7. `runtime/demo1_transcript.log.jsonl` proves the state chain.
