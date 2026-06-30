# Base Station Perception

This directory contains DK-2500-side perception code. Keep imports stable here
until a dedicated refactor updates tests and runtime entrypoints in the same
commit.

## Current Groups

| Group | Files | Role |
| --- | --- | --- |
| Sources | `frame_source.py`, `fake_camera.py`, `opencv_camera.py`, `static_image_source.py`, `ws_video_source.py`, `audio_source.py` | Camera, image, WebSocket frame, and audio-file inputs. |
| Vision | `face_emotion*.py`, `openface_*`, `openvino_face_emotion_model.py`, `head_pose.py`, `fatigue/` | Face emotion, OpenFace/OpenVINO, head pose, and fatigue metrics. |
| VLM | `qwen_vl_*`, `openvino_qwen_*`, `vlm_face_analyzer.py`, `vlm_trigger_gate.py` | Qwen-VL and VLM gate paths. |
| Audio | `asr.py`, `vad.py`, `tts.py`, `audio_diagnostics.py`, `audio_segments.py`, `audio_emotion.py`, `asr_emotion_trigger.py` | File-first ASR/VAD/TTS interfaces, `/audio` diagnostics, and fixed-window ASR helpers. |
| Policy / legacy | `valence_mapping.py`, `work_activity.py` | Small policy helpers and legacy compatibility. |
| Vendored runtime | `openface_ov_runtime/` | Bundled OpenFace/OpenVINO runtime with fragile import paths; do not move during ordinary cleanup. |

## Current Rules

- Do not move files physically until import paths, tests, docs, and runtime
  commands are updated together.
- Keep raw camera/audio local to the base station unless the user explicitly
  approves another path.
- Use `audio_diagnostics.py` and `audio_segments.py` before changing ASR model
  settings; unclear WAV audio is a capture/wiring/gain issue first.
- Treat OpenVINO/Qwen/SenseVoice/Silero model files as local setup artifacts, not
  Git content.

## Related Docs

- [../../docs/setup/model_download.md](../../docs/setup/model_download.md)
- [../../docs/testing/smoke/asr_vad_audio_file_smoke.md](../../docs/testing/smoke/asr_vad_audio_file_smoke.md)
- [../../docs/perception/openface_au_mapping.md](../../docs/perception/openface_au_mapping.md)
- [../../docs/perception/qwen_vl_fusion_policy.md](../../docs/perception/qwen_vl_fusion_policy.md)
