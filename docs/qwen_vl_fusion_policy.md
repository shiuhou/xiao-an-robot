# Qwen VLM Fusion Policy

Step 41.1 hardens the Qwen VLM path so malformed model output cannot crash `emotion_runtime`, and so CV and VLM signals have an explicit conservative merge policy.

## Why Fusion Exists

The CV path is fast and stable enough to drive the continuous emotion stream. The Qwen VLM path is slower but can add semantic visual judgment when the VLM trigger gate fires. Fusion keeps CV as the baseline while allowing high-confidence VLM evidence to influence the top-level sample used by proactive care.

## CV And VLM Responsibilities

- CV produces the first `emotion_tag`, `confidence`, `fatigue_score`, frame metadata, and OpenFace-style metrics.
- VLM runs only when the gate fires, or when `--force-vlm` is used for manual smoke.
- `cv_sample` preserves the original CV result.
- `vlm` preserves the normalized VLM result or a structured VLM error.
- Top-level `emotion_tag`, `confidence`, and `fatigue_score` are the fused values used by proactive care.

## conservative_v1 Rules

`fusion.strategy` is `conservative_v1`.

| Condition | Decision | Top-level result |
| --- | --- | --- |
| VLM failed or raised | `cv_only_vlm_error` | Keep CV result |
| CV and VLM both indicate tired/sad/anxious/stressed, and VLM confidence >= 0.65 | `cv_vlm_agree_negative` | Use the more severe negative tag, max confidence, max fatigue |
| CV is not negative, VLM is tired/sad/anxious/stressed, VLM confidence >= 0.75, and VLM fatigue_score >= 0.70 | `vlm_promoted_negative` | Promote VLM tag, confidence, and fatigue |
| CV is tired/sad/anxious/stressed, VLM is neutral, VLM confidence >= 0.85, CV confidence < 0.65, and CV fatigue_score < 0.75 | `vlm_suppressed_low_conf_cv` | Reduce top-level result to neutral |
| Anything else | `cv_primary_vlm_aux` | Keep CV result and retain VLM as auxiliary evidence |

## VLM Promotion

VLM can promote a negative result only when it is confident and its own fatigue score is high. This prevents a single vague VLM label from creating an intervention when CV is neutral.

## VLM Suppression

VLM neutral can suppress only low-confidence CV negative output with modest fatigue. It must not override high-confidence or high-fatigue CV tired/stressed results.

## VLM Error Fallback

If Qwen loading, generation, or JSON parsing fails, the runtime yields a sample instead of exiting:

- `vlm_triggered=true`
- `vlm.executed=false`
- `vlm.status=error`
- `vlm.error=<short message>`
- `fusion.decision=cv_only_vlm_error`

This keeps the CV stream alive and prevents one slow or malformed VLM call from breaking OpenClaw delivery.

## Verbose Logs

With `--verbose`, the gate prints concise VLM and fusion lines:

```text
[vlm.start] frame_id=... backend=openvino_qwen_vl
[vlm.done] frame_id=... status=ok emotion_tag=... confidence=... fatigue_score=... seconds=...
[vlm.error] frame_id=... error=...
[fusion] frame_id=... decision=... top_emotion=... top_fatigue=...
```

Normal mode avoids these extra lines.

## Manual Smoke

Image file with real Qwen VLM gate:

```bash
.venv/bin/python -m base_station.monitor.emotion_runtime \
  --source image_file \
  --image-path runtime/manual_samples/image.png \
  --model-backend mock \
  --pattern tired \
  --enable-vlm-gate \
  --vlm-backend openvino_qwen_vl \
  --vlm-model-path base_station/models/Qwen2.5-VL-3B-OV-int4 \
  --force-vlm \
  --count 1 \
  --no-agent \
  --verbose
```

VLM error fallback with a missing model path:

```bash
.venv/bin/python -m base_station.monitor.emotion_runtime \
  --source image_file \
  --image-path runtime/manual_samples/image.png \
  --model-backend mock \
  --pattern tired \
  --enable-vlm-gate \
  --vlm-backend openvino_qwen_vl \
  --vlm-model-path base_station/models/missing-qwen-vl \
  --force-vlm \
  --count 1 \
  --no-agent \
  --verbose
```

Do not commit model files, manual images, `runtime/`, databases, logs, `.venv`, `frontend/dist`, or `node_modules`.
