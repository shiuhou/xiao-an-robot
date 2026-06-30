# Base Station Monitor

This directory contains local runtime monitors and event builders. It is not the
owner of long-term user memory or product scheduling; OpenClaw owns those
product domains.

## Current Groups

| Group | Files | Role |
| --- | --- | --- |
| Emotion runtime | `emotion_runtime.py`, `emotion_event_loop.py`, `emotion_context_builder.py`, `emotion_db.py` | Local emotion events, context, and SQLite-backed runtime history. |
| ASR runtime | `asr_runtime.py`, `fixed_window_asr_demo.py` | Text/pattern/audio-file ASR event path and fixed-window `/audio` demo. `continuous_asr_demo.py` is a compatibility wrapper. |
| Legacy / deprecated | `screen_watcher.py`, `work_activity_runtime.py` | Kept for compatibility; screen monitoring is outside the current MVP. |

## Current Rules

- Keep `screen_watcher.py` deprecated. Do not extend screen or active-window
  monitoring without a new product decision.
- Do not commit SQLite databases, runtime logs, or captured audio/video/images.
- Keep ASR demos file-first or fixed-window until the autonomous ASR policy loop
  is intentionally integrated.

## Related Docs

- [../../docs/current_status.md](../../docs/current_status.md)
- [../../docs/testing/smoke/asr_vad_audio_file_smoke.md](../../docs/testing/smoke/asr_vad_audio_file_smoke.md)
- [../../docs/setup/local_api.md](../../docs/setup/local_api.md)
