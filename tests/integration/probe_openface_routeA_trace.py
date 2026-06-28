#!/usr/bin/env python
"""Manual Route A trace probe: obs -> cv_sample -> gate UI -> final_sample -> event.

This script is intentionally not named ``test_*.py``. It touches a live camera
and optional heavy models, so it should be run manually:

    python tests/integration/probe_openface_routeA_trace.py --count 30 --interval 0.5

To highlight the force trigger condition on every frame:

    python tests/integration/probe_openface_routeA_trace.py --count 30 --interval 0.5 --force-vlm

By default the VLM model is not executed here. Pass ``--execute-vlm`` to run the
same blocking VLM step used by the runtime: when the gate triggers, the probe
pauses the CV loop until the VLM result is available.
"""

from __future__ import annotations

import argparse
from collections import deque
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


DEFAULT_VLM_MODEL_PATH = (
    r"C:\Users\Lenovo\Desktop\xiao-an-robot\xiao-an-robot"
    r"\base_station\models\Qwen2.5-VL-3B-OV-int4"
)

NEGATIVE_EMOTIONS = {"tired", "sad", "anxious", "stressed"}
WINDOW_SIZE = 5
DISPLAY_WINDOW_NAME = "OpenFace Route A gate debug"
VLM_PANEL_WIDTH = 430
AU_DISPLAY_LABELS = (
    "AU01 - Inner Brow Raiser",
    "AU02 - Outer Brow Raiser",
    "AU04 - Brow Lowerer",
    "AU06 - Cheek Raiser",
    "AU09 - Nose Wrinkler",
    "AU12 - Lip Corner Puller",
    "AU25 - Lips Part",
    "AU26 - Jaw Drop",
)


def json_safe(value: Any) -> Any:
    """Convert common model outputs into JSON-safe values for trace printing."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]

    shape = getattr(value, "shape", None)
    if shape is not None:
        return {
            "_type": type(value).__name__,
            "shape": [int(dim) for dim in shape],
        }
    return str(value)


def sanitize_frame(frame: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": frame.get("source"),
        "frame_id": frame.get("frame_id"),
        "timestamp_ms": frame.get("timestamp_ms"),
        "width": frame.get("width"),
        "height": frame.get("height"),
    }


def sanitize_obs(obs: dict[str, Any] | None, print_arrays: bool = False) -> dict[str, Any] | None:
    if obs is None:
        return None

    landmarks = obs.get("landmarks")
    shape = getattr(landmarks, "shape", None)
    sanitized: dict[str, Any] = {
        "has_landmarks": landmarks is not None,
        "landmarks_shape": [int(dim) for dim in shape] if shape is not None else None,
        "face_confidence": json_safe(obs.get("face_confidence")),
        "emotion_label": json_safe(obs.get("emotion_label")),
        "emotion_confidence": json_safe(obs.get("emotion_confidence")),
        "au": json_safe(obs.get("au")),
    }
    if print_arrays:
        sanitized["landmarks"] = json_safe(landmarks)
    return sanitized


def sanitize_sample(sample: dict[str, Any] | None, print_arrays: bool = False) -> dict[str, Any] | None:
    if sample is None:
        return None
    if print_arrays:
        return json_safe(sample)

    sanitized = {}
    for key, value in sample.items():
        if key == "frame_b64":
            sanitized[key] = "<omitted>" if value else value
        else:
            sanitized[key] = json_safe(value)
    return sanitized


def load_prompt_override(args: argparse.Namespace) -> str | None:
    if args.vlm_prompt_file:
        return Path(args.vlm_prompt_file).read_text(encoding="utf-8")
    return args.vlm_prompt


def apply_vlm_prompt_override(prompt: str | None) -> None:
    if prompt is None:
        return
    import base_station.perception.vlm_face_analyzer as vlm_face_analyzer

    vlm_face_analyzer.PROMPT = prompt


def active_prompt_preview(args: argparse.Namespace, override: str | None) -> str | None:
    if override is not None:
        return override
    if args.vlm_backend != "vlm_face":
        return None
    import base_station.perception.vlm_face_analyzer as vlm_face_analyzer

    return vlm_face_analyzer.PROMPT


def compact_text(value: Any, fallback: str = "--") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def wrap_text(text: str, max_chars: int) -> list[str]:
    wrapped: list[str] = []
    for raw_line in compact_text(text).splitlines():
        line = raw_line.strip()
        while len(line) > max_chars:
            wrapped.append(line[:max_chars])
            line = line[max_chars:]
        wrapped.append(line)
    return wrapped or ["--"]


_UNICODE_FONT_CACHE: dict[int, Any] = {}


def _unicode_font(size: int):
    if size in _UNICODE_FONT_CACHE:
        return _UNICODE_FONT_CACHE[size]

    from PIL import ImageFont

    for path in (
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
        Path(r"C:\Windows\Fonts\arialuni.ttf"),
    ):
        if path.exists():
            font = ImageFont.truetype(str(path), size=size)
            _UNICODE_FONT_CACHE[size] = font
            return font

    font = ImageFont.load_default()
    _UNICODE_FONT_CACHE[size] = font
    return font


def draw_panel_text(cv2, image, text: Any, origin: tuple[int, int], font_scale: float, color, thickness: int = 1):
    text = compact_text(text)
    if all(ord(char) < 128 for char in text):
        cv2.putText(image, text, origin, cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness, cv2.LINE_AA)
        return image

    try:
        import numpy as np
        from PIL import Image, ImageDraw

        rgb = image[:, :, ::-1].copy()
        pil_image = Image.fromarray(rgb)
        draw = ImageDraw.Draw(pil_image)
        font_size = max(10, int(round(font_scale * 32)))
        draw.text(origin, text, font=_unicode_font(font_size), fill=(int(color[2]), int(color[1]), int(color[0])))
        image[:] = np.asarray(pil_image)[:, :, ::-1]
        return image
    except Exception:
        cv2.putText(image, text, origin, cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness, cv2.LINE_AA)
        return image


def _float_value(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0.0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def should_process_frame(frame_id: int, count: int) -> bool:
    return count <= 0 or frame_id <= count


def cooldown_remaining(now: float, last_completed: float | None, cooldown_seconds: float) -> float:
    if last_completed is None or cooldown_seconds <= 0:
        return 0.0
    return max(0.0, cooldown_seconds - (now - last_completed))


def build_gate_state(
    *,
    cv_sample: dict[str, Any],
    gate_result: dict[str, Any],
    gate: Any,
    force_vlm: bool,
    fatigue_score_window,
    negative_window,
) -> dict[str, Any]:
    emotion_tag = str(cv_sample.get("emotion_tag", cv_sample.get("emotion", "neutral")) or "neutral")
    confidence = _float_value(cv_sample.get("confidence"))
    fatigue_score = _float_value(cv_sample.get("fatigue_score"))
    fatigue_threshold = _float_value(getattr(gate, "fatigue_threshold", 70.0), 70.0)
    negative_confidence_threshold = _float_value(
        getattr(gate, "negative_confidence_threshold", 0.75),
        0.75,
    )
    negative_count_threshold = int(getattr(gate, "negative_count_threshold", 2))
    is_negative = emotion_tag in NEGATIVE_EMOTIONS
    negative_count = int(sum(1 for item in negative_window if item))

    rules = [
        {
            "code": "FORCE",
            "label": "FORCE",
            "value": bool(force_vlm),
            "threshold": True,
            "fired": bool(force_vlm),
            "unit": "",
        },
        {
            "code": "HIGH_FATIGUE",
            "label": "HIGH FATIGUE",
            "value": fatigue_score,
            "threshold": fatigue_threshold,
            "fired": fatigue_score >= fatigue_threshold,
            "unit": "",
        },
        {
            "code": "NEG_CONF",
            "label": f"NEG CONF {emotion_tag}",
            "value": confidence,
            "threshold": negative_confidence_threshold,
            "fired": is_negative and confidence >= negative_confidence_threshold,
            "unit": "",
        },
        {
            "code": "NEG_WINDOW",
            "label": "NEG WINDOW",
            "value": negative_count,
            "threshold": negative_count_threshold,
            "fired": negative_count >= negative_count_threshold,
            "unit": "",
        },
    ]

    return {
        "should_trigger": bool(gate_result.get("should_trigger", False)),
        "reason": str(gate_result.get("reason", "normal")),
        "emotion_tag": emotion_tag,
        "confidence": confidence,
        "fatigue_score": fatigue_score,
        "negative_count": negative_count,
        "fatigue_score_window": list(fatigue_score_window),
        "negative_window": list(negative_window),
        "vlm_executed": False,
        "rules": rules,
    }


def _format_rule_value(value: Any, unit: str = "") -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "--"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def normalize_au_values(au: Any) -> list[tuple[str, float]]:
    if au is None:
        return []
    if isinstance(au, dict):
        values = []
        for key, value in sorted(au.items(), key=lambda item: str(item[0])):
            try:
                values.append((str(key), float(value)))
            except (TypeError, ValueError):
                continue
        return values
    if isinstance(au, (list, tuple)):
        values = []
        for index, value in enumerate(au):
            try:
                if index < len(AU_DISPLAY_LABELS):
                    label = AU_DISPLAY_LABELS[index]
                else:
                    label = f"AU_UNKNOWN_{index}"
                values.append((label, float(value)))
            except (TypeError, ValueError):
                continue
        return values
    return []


def project_landmarks_to_frame(obs: dict[str, Any] | None):
    if not obs:
        return None
    landmarks = obs.get("landmarks")
    if landmarks is None:
        return None
    import numpy as np

    points = np.asarray(landmarks, dtype=np.float32)
    if points.ndim != 2 or points.shape[1] != 2:
        return None
    face_bbox = obs.get("face_bbox")
    if isinstance(face_bbox, (list, tuple)) and len(face_bbox) >= 2:
        points = points.copy()
        points[:, 0] += float(face_bbox[0])
        points[:, 1] += float(face_bbox[1])
    return points


def build_obs_metrics(obs: dict[str, Any] | None) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "ear": None,
        "mar": None,
        "face_confidence": None,
        "emotion_label": None,
        "emotion_confidence": None,
        "face_bbox": None,
        "au_values": [],
    }
    if not obs:
        return metrics

    metrics["face_confidence"] = obs.get("face_confidence")
    metrics["emotion_label"] = obs.get("emotion_label")
    metrics["emotion_confidence"] = obs.get("emotion_confidence")
    metrics["face_bbox"] = obs.get("face_bbox")
    metrics["au_values"] = normalize_au_values(obs.get("au"))
    landmarks = obs.get("landmarks")
    if landmarks is not None:
        from base_station.perception.fatigue.face_metrics import compute_ear, compute_mar

        metrics["ear"] = compute_ear(landmarks)
        metrics["mar"] = compute_mar(landmarks)
    return metrics


def _draw_window_curve(cv2, image, title: str, values: list[float], origin: tuple[int, int], color, max_value: float):
    x0, y0 = origin
    width, height = 190, 58
    muted = (110, 110, 110)
    cv2.putText(image, title, (x0, y0 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1, cv2.LINE_AA)
    cv2.rectangle(image, (x0, y0), (x0 + width, y0 + height), muted, 1)
    if len(values) < 2:
        return image

    points = []
    for index, raw in enumerate(values):
        value = max(0.0, min(float(raw), max_value))
        x = x0 + int(round(index * width / max(1, WINDOW_SIZE - 1)))
        y = y0 + height - int(round((value / max_value) * height)) if max_value > 0 else y0 + height
        points.append((x, y))
    for left, right in zip(points, points[1:]):
        cv2.line(image, left, right, color, 2, cv2.LINE_AA)
    return image


def draw_probe_header(cv2, image, gate_state: dict[str, Any], frame_id: int, display_fps: float):
    trigger = gate_state["should_trigger"]
    color = (0, 0, 255) if trigger else (0, 255, 0)
    vlm_text = "VLM EXEC ON" if gate_state.get("vlm_enabled") else "VLM EXEC OFF"
    if gate_state.get("vlm_executed"):
        vlm_text = f"VLM DONE {gate_state.get('vlm_elapsed_seconds', 0.0):.1f}s"
    elif gate_state.get("vlm_suppressed_by_cooldown"):
        vlm_text = f"VLM COOLDOWN {gate_state.get('vlm_cooldown_remaining', 0.0):.1f}s"
    cv2.putText(
        image,
        f"ROUTE A LIVE | frame {frame_id} | display {display_fps:.1f} FPS",
        (12, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.62,
        (0, 255, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.circle(image, (24, 58), 9, color, -1, cv2.LINE_AA)
    cv2.putText(
        image,
        f"VLM GATE {'TRIGGER' if trigger else 'NORMAL'} | reason={gate_state['reason']} | {vlm_text}",
        (42, 64),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
        color,
        2,
        cv2.LINE_AA,
    )
    return image


def draw_route_a_metrics(cv2, image, cv_sample: dict[str, Any], gate_state: dict[str, Any]):
    obs_metrics = gate_state.get("obs_metrics") or {}
    evidence = cv_sample.get("evidence_codes") or []
    evidence_text = ",".join(str(item) for item in evidence) if evidence else "--"
    lines = [
        (
            "emotion={emotion} conf={confidence:.2f} fatigue={fatigue} neg_count={negative}/5".format(
                emotion=gate_state["emotion_tag"],
                confidence=gate_state["confidence"],
                fatigue=_format_rule_value(gate_state["fatigue_score"]),
                negative=gate_state["negative_count"],
            ),
            (255, 255, 0),
        ),
        (
            "EAR={ear} MAR={mar} face_conf={face_conf} raw_expr={expr} raw_conf={expr_conf}".format(
                ear=_format_rule_value(obs_metrics.get("ear")),
                mar=_format_rule_value(obs_metrics.get("mar")),
                face_conf=_format_rule_value(obs_metrics.get("face_confidence")),
                expr=obs_metrics.get("emotion_label"),
                expr_conf=_format_rule_value(obs_metrics.get("emotion_confidence")),
            ),
            (255, 255, 0),
        ),
        (
            "quality={quality} presence={presence} level={level}".format(
                quality=_format_rule_value(cv_sample.get("observation_quality")),
                presence=cv_sample.get("presence_state"),
                level=cv_sample.get("fatigue_level"),
            ),
            (220, 220, 220),
        ),
        (
            f"evidence={evidence_text}",
            (220, 220, 220),
        ),
    ]
    y = 92
    for text, color in lines:
        cv2.putText(image, text, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.52, color, 2, cv2.LINE_AA)
        y += 24
    return image


def draw_landmarks_and_face(cv2, image, obs: dict[str, Any] | None):
    if not obs:
        return image
    face_bbox = obs.get("face_bbox")
    if isinstance(face_bbox, (list, tuple)) and len(face_bbox) == 4:
        x1, y1, x2, y2 = [int(round(float(value))) for value in face_bbox]
        cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2, cv2.LINE_AA)

    points = project_landmarks_to_frame(obs)
    if points is None:
        return image
    for point in points:
        cv2.circle(
            image,
            (int(round(float(point[0]))), int(round(float(point[1])))),
            2,
            (0, 255, 0),
            -1,
            cv2.LINE_AA,
        )
    return image


def make_au_panel(
    cv2,
    height: int,
    au_values: list[tuple[str, float]],
    gate_state: dict[str, Any] | None = None,
    width: int = 300,
):
    import numpy as np

    panel = np.ones((height, width, 3), dtype=np.uint8) * 255
    cv2.putText(panel, "AU", (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 0), 2, cv2.LINE_AA)

    y = 64
    bar_x = 78
    bar_w = width - bar_x - 22
    chart_top = max(150, height - 170)
    if not au_values:
        cv2.putText(panel, "no AU", (16, 68), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (120, 120, 120), 1, cv2.LINE_AA)

    for label, value in au_values[:14]:
        if y > chart_top - 18:
            break
        value = max(0.0, min(float(value), 1.0))
        cv2.putText(panel, label, (14, y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
        cv2.rectangle(panel, (bar_x, y - 10), (bar_x + bar_w, y + 8), (210, 210, 210), 1)
        cv2.rectangle(panel, (bar_x, y - 10), (bar_x + int(round(bar_w * value)), y + 8), (0, 180, 0), -1)
        cv2.putText(
            panel,
            f"{value:.2f}",
            (bar_x + bar_w - 42, y + 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            (0, 0, 0),
            1,
            cv2.LINE_AA,
        )
        y += 28

    if gate_state is not None:
        cv2.line(panel, (12, chart_top - 16), (width - 12, chart_top - 16), (190, 190, 190), 1, cv2.LINE_AA)
        _draw_window_curve(
            cv2,
            panel,
            "fatigue last 5",
            gate_state["fatigue_score_window"],
            (16, chart_top + 8),
            (0, 170, 230),
            100.0,
        )
        negative_counts = []
        running = []
        for value in gate_state["negative_window"]:
            running.append(value)
            negative_counts.append(sum(1 for item in running if item))
        _draw_window_curve(
            cv2,
            panel,
            "negative count",
            negative_counts,
            (16, chart_top + 92),
            (0, 160, 0),
            float(WINDOW_SIZE),
        )
    return panel


def make_vlm_panel(
    cv2,
    height: int,
    *,
    gate_state: dict[str, Any],
    vlm_result: dict[str, Any] | None,
    status: str,
    prompt: str | None,
    context: dict[str, Any] | None = None,
    width: int = VLM_PANEL_WIDTH,
):
    import numpy as np

    panel = np.ones((height, width, 3), dtype=np.uint8) * 245
    title_color = (0, 0, 180) if gate_state.get("should_trigger") else (0, 130, 0)
    cv2.putText(panel, "VLM", (16, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.82, title_color, 2, cv2.LINE_AA)
    cv2.putText(panel, status, (90, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.56, title_color, 2, cv2.LINE_AA)

    y = 68
    fields = [
        ("trigger", str(gate_state.get("should_trigger", False))),
        ("reason", gate_state.get("reason", "normal")),
        ("executed", str(gate_state.get("vlm_executed", False))),
    ]
    if vlm_result:
        fields.extend([
            ("emotion", vlm_result.get("emotion_tag", vlm_result.get("emotion"))),
            ("polarity", vlm_result.get("polarity")),
            ("confidence", _format_rule_value(vlm_result.get("confidence"))),
            ("fatigue", _format_rule_value(vlm_result.get("fatigue_score"))),
        ])
    for label, value in fields:
        draw_panel_text(
            cv2,
            panel,
            f"{label}: {compact_text(value)}",
            (16, y),
            0.48,
            (40, 40, 40),
            1,
        )
        y += 24

    cv2.line(panel, (14, y), (width - 14, y), (190, 190, 190), 1, cv2.LINE_AA)
    y += 28
    cv2.putText(panel, "message", (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2, cv2.LINE_AA)
    y += 26
    message = vlm_result.get("message") if vlm_result else ""
    if not message and vlm_result:
        message = vlm_result.get("vlm_observation") or vlm_result.get("visual_reason")
    for line in wrap_text(compact_text(message), 30)[:7]:
        draw_panel_text(cv2, panel, line, (16, y), 0.48, (20, 20, 20), 1)
        y += 24

    y += 10
    cv2.line(panel, (14, y), (width - 14, y), (190, 190, 190), 1, cv2.LINE_AA)
    y += 24
    cv2.putText(panel, "context", (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2, cv2.LINE_AA)
    y += 22
    context_text = json.dumps(json_safe(context), ensure_ascii=False, sort_keys=True) if context else "--"
    for line in wrap_text(context_text, 38)[:5]:
        draw_panel_text(cv2, panel, line, (16, y), 0.38, (60, 60, 60), 1)
        y += 18

    y = max(y + 12, height - 130)
    cv2.line(panel, (14, y), (width - 14, y), (190, 190, 190), 1, cv2.LINE_AA)
    y += 26
    cv2.putText(panel, "prompt", (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2, cv2.LINE_AA)
    y += 24
    for line in wrap_text(compact_text(prompt, "default VLMFaceAnalyzer.PROMPT"), 34)[:5]:
        draw_panel_text(cv2, panel, line, (16, y), 0.42, (80, 80, 80), 1)
        y += 20
    return panel


def draw_gate_rules_panel(cv2, image, gate_state: dict[str, Any]):
    height, width = image.shape[:2]
    panel_x = 12
    y = max(150, height - 150)
    panel_w = min(430, width - 24)
    panel_h = 138
    cv2.rectangle(
        image,
        (panel_x - 6, y - 24),
        (panel_x + panel_w, min(height - 10, y - 24 + panel_h)),
        (0, 0, 0),
        -1,
    )
    cv2.rectangle(
        image,
        (panel_x - 6, y - 24),
        (panel_x + panel_w, min(height - 10, y - 24 + panel_h)),
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        image,
        "VLM GATE / WHY",
        (panel_x, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.56,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    y += 22
    cv2.putText(
        image,
        f"SHOULD_TRIGGER {str(gate_state['should_trigger']).upper()}",
        (panel_x, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.54,
        (0, 0, 255) if gate_state["should_trigger"] else (80, 255, 80),
        2,
        cv2.LINE_AA,
    )
    y += 22

    muted = (200, 200, 200)
    for rule in gate_state["rules"]:
        fired = bool(rule["fired"])
        color = (0, 80, 255) if fired else muted
        value = _format_rule_value(rule["value"], rule.get("unit", ""))
        threshold = _format_rule_value(rule["threshold"], rule.get("unit", ""))
        text = f"{rule['label']:<18} {value}/{threshold}"
        cv2.putText(image, text, (panel_x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.46, color, 2 if fired else 1, cv2.LINE_AA)
        cv2.circle(image, (min(width - 18, panel_x + 276), y - 4), 4, color, -1 if fired else 1, cv2.LINE_AA)
        y += 18
    return image


def draw_route_a_display(
    cv2,
    frame: dict[str, Any],
    row: dict[str, Any],
    obs: dict[str, Any] | None,
    gate_state: dict[str, Any],
    display_fps: float,
    vlm_result: dict[str, Any] | None = None,
    vlm_status: str = "idle",
    prompt: str | None = None,
    vlm_context: dict[str, Any] | None = None,
    show_vlm_panel: bool = False,
):
    image = frame["payload"].copy()
    frame_id = int(row["frame"].get("frame_id") or 0)
    if not show_vlm_panel:
        image = draw_landmarks_and_face(cv2, image, obs)
    image = draw_probe_header(cv2, image, gate_state, frame_id, display_fps)
    if show_vlm_panel:
        au_panel = make_vlm_panel(
            cv2,
            image.shape[0],
            gate_state=gate_state,
            vlm_result=vlm_result,
            status=vlm_status,
            prompt=prompt,
            context=vlm_context,
        )
    else:
        image = draw_route_a_metrics(cv2, image, row["cv_sample"], gate_state)
        image = draw_gate_rules_panel(cv2, image, gate_state)
        au_panel = make_au_panel(
            cv2,
            image.shape[0],
            (gate_state.get("obs_metrics") or {}).get("au_values") or [],
            gate_state=gate_state,
        )
    import numpy as np

    return np.hstack((image, au_panel))


def build_final_sample(
    cv_sample: dict[str, Any],
    gate_result: dict[str, Any],
    vlm_result: dict[str, Any] | None,
) -> dict[str, Any]:
    """Mirror VLMGatedCameraEmotionSource.samples() final_sample semantics."""
    reason = str(gate_result.get("reason", "normal"))
    final_sample = dict(cv_sample)
    triggered = bool(gate_result.get("should_trigger", False)) and vlm_result is not None
    final_sample["vlm_triggered"] = triggered
    final_sample["vlm_trigger_reason"] = reason
    if not triggered:
        return final_sample

    from base_station.monitor.emotion_runtime import fuse_cv_vlm_sample, normalize_vlm_result

    normalized_vlm = normalize_vlm_result(
        vlm_result,
        executed=True,
        status=str(vlm_result.get("status", "ok")) if isinstance(vlm_result, dict) else "ok",
    )
    final_sample = fuse_cv_vlm_sample(cv_sample, normalized_vlm)
    final_sample["vlm_triggered"] = True
    final_sample["vlm_trigger_reason"] = reason

    return final_sample


def build_trace_row(
    *,
    frame: dict[str, Any],
    obs: dict[str, Any] | None,
    cv_sample: dict[str, Any],
    gate_result: dict[str, Any],
    vlm_result: dict[str, Any] | None,
    final_sample: dict[str, Any],
    print_arrays: bool = False,
) -> dict[str, Any]:
    from base_station.monitor.emotion_event_loop import EmotionEventLoop

    event = EmotionEventLoop(brain=None).build_event(final_sample)
    return {
        "frame": sanitize_frame(frame),
        "obs": sanitize_obs(obs, print_arrays=print_arrays),
        "cv_sample": sanitize_sample(cv_sample, print_arrays=print_arrays),
        "gate_result": json_safe(gate_result),
        "vlm_result": sanitize_sample(vlm_result, print_arrays=print_arrays),
        "final_sample": sanitize_sample(final_sample, print_arrays=print_arrays),
        "event": sanitize_sample(event, print_arrays=print_arrays),
    }


def make_frame(
    frame_id: int,
    image: Any,
    *,
    timestamp_ms: int | None = None,
    source: str = "opencv_camera",
) -> dict[str, Any]:
    height, width = image.shape[:2]
    return {
        "source": source,
        "frame_id": frame_id,
        "timestamp_ms": int(time.time() * 1000) if timestamp_ms is None else int(timestamp_ms),
        "width": int(width),
        "height": int(height),
        "payload": image,
    }


def _safe_cap_get(cap: Any, prop: int, default: float = 0.0) -> float:
    try:
        value = float(cap.get(prop))
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def video_timestamp_ms(cv2: Any, cap: Any, fps: float) -> int:
    pos_msec = _safe_cap_get(cap, cv2.CAP_PROP_POS_MSEC, default=-1.0)
    raw_frame_number = max(0.0, _safe_cap_get(cap, cv2.CAP_PROP_POS_FRAMES, default=1.0) - 1.0)
    fallback_msec = (raw_frame_number / fps) * 1000.0 if fps > 0 else 0.0
    if pos_msec > 0.0 or raw_frame_number == 0.0:
        return int(round(max(0.0, pos_msec)))
    return int(round(max(0.0, fallback_msec)))


def build_traced_openface_pipeline(args: argparse.Namespace):
    from base_station.perception.openface_cv_pipeline import OpenFaceCVPipeline
    from base_station.perception.openface_ov_adapter import build_ov_perceive_callable

    raw_perceive = build_ov_perceive_callable(
        openface_repo=args.openface_repo,
        models_dir=args.openface_models_dir,
        device=args.device,
    )
    state: dict[str, Any] = {"last_obs": None}

    def traced_perceive(frame: Any) -> dict[str, Any] | None:
        obs = raw_perceive(frame)
        state["last_obs"] = obs
        return obs

    return OpenFaceCVPipeline(perceive=traced_perceive), state


def build_vlm_components(args: argparse.Namespace):
    from base_station.perception.vlm_trigger_gate import VLMTriggerGate

    gate = VLMTriggerGate(fatigue_threshold=args.fatigue_threshold)
    if not args.execute_vlm:
        return gate, None

    prompt = load_prompt_override(args)
    if args.vlm_backend == "vlm_face":
        apply_vlm_prompt_override(prompt)

    from base_station.monitor.emotion_runtime import create_vlm_emotion_model

    vlm_model = create_vlm_emotion_model(
        vlm_backend=args.vlm_backend,
        pattern=args.vlm_pattern,
        vlm_model_path=args.vlm_model_path,
        device=args.device,
    )
    return gate, vlm_model


def build_vlm_context(cv_sample: dict[str, Any]) -> dict[str, Any]:
    from base_station.monitor.emotion_context_builder import EmotionContextBuilder

    return EmotionContextBuilder().build(
        cv_sample=cv_sample,
        vlm_sample=None,
        asr_text=None,
        history_summary=None,
    )


def predict_vlm(vlm_model: Any, frame: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return vlm_model.predict(frame, context)


def run_trace(args: argparse.Namespace) -> int:
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    if args.openface_repo:
        os.environ.setdefault("OPENFACE_REPO", args.openface_repo)
    if args.openface_models_dir:
        os.environ.setdefault("OPENFACE_OV_MODELS_DIR", args.openface_models_dir)

    import cv2

    cv_pipeline, trace_state = build_traced_openface_pipeline(args)
    gate, vlm_model = build_vlm_components(args)
    prompt_override = load_prompt_override(args)
    prompt_preview = active_prompt_preview(args, prompt_override)
    fatigue_score_window = deque(maxlen=WINDOW_SIZE)
    negative_window = deque(maxlen=WINDOW_SIZE)
    last_vlm_completed_at: float | None = None

    output_file = None
    if args.jsonl:
        Path(args.jsonl).parent.mkdir(parents=True, exist_ok=True)
        output_file = open(args.jsonl, "w", encoding="utf-8")

    video_mode = bool(args.video)
    cap_source = args.video if video_mode else args.camera_index
    cap = cv2.VideoCapture(cap_source)
    if not cap.isOpened():
        if output_file is not None:
            output_file.close()
        if video_mode:
            print(f"Cannot open video {args.video}", file=sys.stderr)
        else:
            print(f"Cannot open camera index {args.camera_index}", file=sys.stderr)
        return 2

    video_fps = _safe_cap_get(cap, cv2.CAP_PROP_FPS, default=0.0) if video_mode else 0.0
    video_step_ms = float(args.video_step_seconds) * 1000.0
    next_sample_ms = 0.0
    raw_video_frame_id = 0
    video_sample_count = 0
    start_time = time.perf_counter()
    try:
        frame_id = 1
        while True:
            if video_mode:
                if args.count > 0 and video_sample_count >= args.count:
                    break
            elif not should_process_frame(frame_id, args.count):
                break

            ok, image = cap.read()
            if not ok:
                if not video_mode:
                    print("camera read failed, stopping", file=sys.stderr)
                break

            frame_timestamp_ms = None
            if video_mode:
                raw_video_frame_id += 1
                frame_timestamp_ms = video_timestamp_ms(cv2, cap, video_fps)
                if frame_timestamp_ms < next_sample_ms:
                    continue
                output_frame_id = raw_video_frame_id
            else:
                output_frame_id = frame_id
            frame = make_frame(
                output_frame_id,
                image,
                timestamp_ms=frame_timestamp_ms,
                source="opencv_video" if video_mode else "opencv_camera",
            )
            if video_mode:
                cv_sample = cv_pipeline.process_frame(frame, timestamp_ms=frame_timestamp_ms)
            else:
                cv_sample = cv_pipeline.process_frame(frame)
            obs = trace_state.get("last_obs")
            fatigue_score = _float_value(cv_sample.get("fatigue_score"))
            emotion_tag = str(cv_sample.get("emotion_tag", cv_sample.get("emotion", "neutral")) or "neutral")
            fatigue_score_window.append(fatigue_score)
            negative_window.append(1 if emotion_tag in NEGATIVE_EMOTIONS else 0)
            gate_result = gate.evaluate(cv_sample, force_vlm=args.force_vlm)
            gate_state = build_gate_state(
                cv_sample=cv_sample,
                gate_result=gate_result,
                gate=gate,
                force_vlm=args.force_vlm,
                fatigue_score_window=fatigue_score_window,
                negative_window=negative_window,
            )
            gate_state["obs_metrics"] = build_obs_metrics(obs)
            gate_state["vlm_enabled"] = vlm_model is not None
            now = time.perf_counter()
            remaining_cooldown = cooldown_remaining(now, last_vlm_completed_at, args.vlm_cooldown)
            gate_state["vlm_cooldown_seconds"] = args.vlm_cooldown
            gate_state["vlm_cooldown_remaining"] = remaining_cooldown
            gate_state["vlm_suppressed_by_cooldown"] = (
                bool(gate_result.get("should_trigger", False))
                and vlm_model is not None
                and remaining_cooldown > 0
            )

            vlm_result = None
            vlm_context = None
            should_execute_vlm = (
                bool(gate_result.get("should_trigger", False))
                and vlm_model is not None
                and remaining_cooldown <= 0
            )
            if should_execute_vlm:
                vlm_context = build_vlm_context(cv_sample)
                pending_sample = build_final_sample(cv_sample, gate_result, None)
                pending_row = build_trace_row(
                    frame=frame,
                    obs=obs,
                    cv_sample=cv_sample,
                    gate_result=gate_result,
                    vlm_result=None,
                    final_sample=pending_sample,
                    print_arrays=args.print_arrays,
                )
                elapsed = max(time.perf_counter() - start_time, 1e-6)
                display_fps = max(1, video_sample_count + 1) / elapsed if video_mode else frame_id / elapsed
                display = draw_route_a_display(
                    cv2,
                    frame,
                    pending_row,
                    obs,
                    gate_state,
                    display_fps,
                    vlm_result=None,
                    vlm_status="running - CV paused",
                    prompt=prompt_preview,
                    vlm_context=vlm_context,
                    show_vlm_panel=True,
                )
                cv2.imshow(DISPLAY_WINDOW_NAME, display)
                cv2.waitKey(1)

                vlm_start = time.perf_counter()
                vlm_result = predict_vlm(vlm_model, frame, vlm_context)
                gate_state["vlm_executed"] = True
                gate_state["vlm_elapsed_seconds"] = time.perf_counter() - vlm_start
                last_vlm_completed_at = time.perf_counter()

            final_sample = build_final_sample(cv_sample, gate_result, vlm_result)
            row = build_trace_row(
                frame=frame,
                obs=obs,
                cv_sample=cv_sample,
                gate_result=gate_result,
                vlm_result=vlm_result,
                final_sample=final_sample,
                print_arrays=args.print_arrays,
            )
            row["gate_state"] = json_safe(gate_state)

            if args.event_only:
                printable = {
                    "frame": row["frame"],
                    "final_sample": row["final_sample"],
                    "event": row["event"],
                    "gate_state": row["gate_state"],
                }
            else:
                printable = row

            text = json.dumps(printable, ensure_ascii=False, indent=2 if args.pretty else None)
            print(text)
            if output_file is not None:
                output_file.write(json.dumps(row, ensure_ascii=False) + "\n")
                output_file.flush()

            elapsed = max(time.perf_counter() - start_time, 1e-6)
            display_fps = max(1, video_sample_count + 1) / elapsed if video_mode else frame_id / elapsed
            display = draw_route_a_display(
                cv2,
                frame,
                row,
                obs,
                gate_state,
                display_fps,
                vlm_result=vlm_result,
                vlm_status="done" if vlm_result else "idle",
                prompt=prompt_preview,
                vlm_context=vlm_context,
                show_vlm_panel=vlm_result is not None,
            )
            cv2.imshow(DISPLAY_WINDOW_NAME, display)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

            if video_mode:
                video_sample_count += 1
                next_sample_ms += video_step_ms
            else:
                time.sleep(max(0.0, args.interval))
                frame_id += 1
    finally:
        cap.release()
        if output_file is not None:
            output_file.close()
        cv2.destroyAllWindows()

    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Trace OpenFace Route A live data contracts.")
    parser.add_argument("--openface-repo", default=None)
    parser.add_argument("--openface-models-dir", default=None)
    parser.add_argument("--camera-index", "--camera", dest="camera_index", type=int, default=0)
    parser.add_argument("--video", default=None, help="Optional local video path for offline Route A replay.")
    parser.add_argument(
        "--video-step-seconds",
        type=positive_float,
        default=0.5,
        help="Seconds between sampled video frames when --video is set.",
    )
    parser.add_argument("--count", type=int, default=30, help="Frames to process. 0 means unlimited.")
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--device", default="CPU")
    parser.add_argument("--enable-vlm-gate", action="store_true", help="Legacy flag; gate UI is always enabled.")
    parser.add_argument("--force-vlm", action="store_true")
    parser.add_argument("--fatigue-threshold", type=float, default=70.0)
    parser.add_argument(
        "--vlm-backend",
        default="vlm_face",
        choices=["vlm_face", "fake", "qwen_vl", "openvino_qwen_vl"],
        help="VLM backend used when --execute-vlm is set and the gate triggers.",
    )
    parser.add_argument("--vlm-model-path", default=DEFAULT_VLM_MODEL_PATH)
    parser.add_argument(
        "--vlm-pattern",
        default="neutral",
        choices=["neutral", "tired", "sad", "anxious", "mixed"],
    )
    parser.add_argument(
        "--execute-vlm",
        action="store_true",
        help="Run VLM synchronously when the gate triggers, pausing the CV loop until it finishes.",
    )
    parser.add_argument(
        "--vlm-cooldown",
        type=float,
        default=30.0,
        help="Seconds to suppress additional VLM calls after one VLM call completes. CV keeps running.",
    )
    parser.add_argument(
        "--vlm-prompt",
        default=None,
        help="Override VLMFaceAnalyzer.PROMPT for this probe run. Only applies to --vlm-backend vlm_face.",
    )
    parser.add_argument(
        "--vlm-prompt-file",
        default=None,
        help="Read the VLMFaceAnalyzer prompt override from a UTF-8 text file.",
    )
    parser.add_argument("--jsonl", default=None, help="Optional path to save full trace rows.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print terminal JSON.")
    parser.add_argument("--print-arrays", action="store_true", help="Include array summaries in trace output.")
    parser.add_argument("--event-only", action="store_true", help="Print only final_sample and event.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return run_trace(parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
