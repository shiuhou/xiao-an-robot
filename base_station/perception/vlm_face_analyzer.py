"""Triggered Qwen2.5-VL face analyzer.

Importing this module doesn't import heavy model dependencies. They are loaded
only when ``VLMFaceAnalyzer`` is instantiated or real image analysis runs.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[1] / "models" / "Qwen2.5-VL-3B-OV-int4"
_DEFAULT_PROMPT_FILE = _REPO_ROOT / "vlm_prompt.txt"

MAX_PIXELS = 147456
MAX_NEW_TOKENS = 160
MAX_CONTEXT_PROMPT_CHARS = 3000

_FALLBACK_PROMPT = """请观察图中人物，只根据画面中确实可见的面部和姿态线索判断，只返回 JSON：
- polarity：必须是以下之一（正面 / 负面）
- emotion：用一个最贴切的英文词描述当前情绪，如 neutral, tired, irritable, depressed
- emotion_score：情绪明显程度，0 到 1 的小数
- fatigue_score：疲劳程度，0 到 1 的小数
- confidence：你对本次判断的把握，0 到 1
- visible_evidence：数组，列出 1 到 3 个画面中确实可见的线索；看不清时返回 []
- valid_observation：布尔值；如果画面中人脸/姿态线索足够判断则为 true，否则为 false
- message：如果 polarity 是正面或无需干预，必须为空字符串；如果 polarity 是负面，生成一句自然简短的中文关怀话
要求：只描述你真正看到的，不要编造画面外的信息或用户在做的事，不确定就给低分。
原样返回：
{"polarity":"","emotion":"","emotion_score":0.0,"fatigue_score":0.0,"confidence":0.0,"visible_evidence":[],"valid_observation":true,"message":""}
只返回 JSON。"""


def _load_prompt(path: Path = _DEFAULT_PROMPT_FILE) -> str:
    if path.is_file():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    return _FALLBACK_PROMPT


PROMPT = _load_prompt()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _context_prompt(context: dict | None) -> str:
    if not isinstance(context, dict) or not context:
        return ""

    import json

    safe_context = {
        key: _json_safe(context.get(key))
        for key in ("cv", "asr", "history")
        if key in context
    }
    cv_context = safe_context.get("cv")
    if isinstance(cv_context, dict):
        cv_context = dict(cv_context)
        cv_context.pop("au_json", None)
        safe_context["cv"] = cv_context

    if not safe_context:
        return ""

    text = json.dumps(safe_context, ensure_ascii=False, sort_keys=True)
    if len(text) > MAX_CONTEXT_PROMPT_CHARS:
        text = text[:MAX_CONTEXT_PROMPT_CHARS] + "...<truncated>"
    return (
        "\n\nAuxiliary context for this frame. Use it only as reference; "
        "the image is the primary evidence. If context conflicts with visible "
        "image evidence, trust the image. Do not infer facts outside the image.\n"
        f"{text}"
    )


class VLMFaceAnalyzer:
    """Triggered VLM analyzer; load once, then call predict()/analyze_frame()."""

    def __init__(
        self,
        model_dir: str | Path = _DEFAULT_MODEL_DIR,
        device: str = "CPU",
        face_crop: bool = False,
        crop_margin: float = 0.4,
    ):
        self.model_dir = Path(model_dir)
        if not self.model_dir.exists():
            raise FileNotFoundError(
                f"VLM model not found: {self.model_dir}. Copy the Qwen2.5-VL OpenVINO "
                "model under base_station/models or pass --vlm-model-path."
            )
        self.device = device
        self.face_crop = face_crop
        self.crop_margin = crop_margin

        import cv2  # type: ignore[import-not-found]
        from optimum.intel import OVModelForVisualCausalLM
        from transformers import AutoProcessor

        self._cv2 = cv2
        self._frontal = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        self._profile = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")
        self.processor = AutoProcessor.from_pretrained(
            str(self.model_dir),
            max_pixels=MAX_PIXELS,
            fix_mistral_regex=True,
        )
        self.model = OVModelForVisualCausalLM.from_pretrained(str(self.model_dir), device=device)

    def _detect_face(self, gray):
        cv2 = self._cv2
        for cascade, src in ((self._frontal, gray), (self._profile, gray), (self._profile, cv2.flip(gray, 1))):
            faces = cascade.detectMultiScale(src, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
            if len(faces):
                if src is not gray:
                    width = gray.shape[1]
                    faces = [(width - x - w, y, w, h) for (x, y, w, h) in faces]
                return max(faces, key=lambda face: face[2] * face[3])
        return None

    def _crop(self, bgr):
        gray = self._cv2.cvtColor(bgr, self._cv2.COLOR_BGR2GRAY)
        box = self._detect_face(gray)
        if box is None:
            return bgr, False
        x, y, w, h = box
        mx, my = int(w * self.crop_margin), int(h * self.crop_margin)
        height, width = bgr.shape[:2]
        return (
            bgr[max(0, y - my):min(height, y + h + my), max(0, x - mx):min(width, x + w + mx)],
            True,
        )

    def analyze_image(self, bgr_image, context: dict | None = None) -> dict:
        """Analyze a single BGR ndarray and return parsed VLM fields."""

        from PIL import Image
        from qwen_vl_utils import process_vision_info

        found = False
        image = bgr_image
        if self.face_crop:
            image, found = self._crop(bgr_image)
        pil = Image.fromarray(image[:, :, ::-1])

        messages = [{
            "role": "user",
            "content": [
                {"type": "image", "image": pil},
                {"type": "text", "text": PROMPT + _context_prompt(context)},
            ],
        }]
        text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = self.processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )
        generated = self.model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS)
        trimmed = [output[len(input_ids):] for input_ids, output in zip(inputs.input_ids, generated)]
        raw = self.processor.batch_decode(
            trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0].strip()

        result = _parse(raw)
        if self.face_crop:
            result["face_found"] = found
        return result

    def analyze_frame(self, frame: dict, context: dict | None = None) -> dict:
        if not isinstance(frame, dict) or frame.get("payload") is None:
            raise ValueError("VLMFaceAnalyzer.analyze_frame requires frame['payload'] image.")
        import numpy as np

        payload = frame["payload"]
        if not isinstance(payload, np.ndarray):
            payload = np.asarray(payload)
        return self.analyze_image(payload, context=context)

    def predict(self, frame: dict, context: dict | None = None) -> dict:
        parsed = self.analyze_frame(frame, context=context)
        sample = {
            "polarity": parsed["polarity"],
            "emotion_tag": parsed["emotion"],
            "emotion": parsed["emotion"],
            "emotion_score": parsed.get("emotion_score"),
            "fatigue_score": parsed["fatigue_score"],
            "confidence": parsed["confidence"],
            "visible_evidence": parsed.get("visible_evidence", []),
            "valid_observation": parsed.get("valid_observation", True),
            "message": parsed["message"],
            "source": "vlm_face",
            "frame_source": frame.get("source"),
            "frame_id": frame.get("frame_id"),
            "timestamp_ms": frame.get("timestamp_ms", int(time.time() * 1000)),
        }
        if "face_found" in parsed:
            sample["face_found"] = parsed["face_found"]
        return sample


def _normalize_polarity(value: Any) -> str:
    text = str(value or "").strip().lower()
    if "负" in text or text in {"negative", "neg"}:
        return "负面"
    return "正面"


def _clamp_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return max(0.0, min(1.0, number))


def _optional_clamp_float(value: Any) -> float | None:
    if value is None:
        return None
    return _clamp_float(value)


def _evidence_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _empty(raw: str, error: str) -> dict:
    return {
        "polarity": "正面",
        "emotion": "",
        "emotion_score": None,
        "fatigue_score": 0.0,
        "confidence": 0.0,
        "visible_evidence": [],
        "valid_observation": False,
        "message": "",
        "_raw": raw,
        "_error": error,
    }


def _parse(text: str) -> dict:
    import json
    import re

    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return _empty(text, "unparseable")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return _empty(text, "invalid_json")
    if not isinstance(data, dict):
        return _empty(text, "not_an_object")
    return {
        "polarity": _normalize_polarity(data.get("polarity", "")),
        "emotion": str(data.get("emotion", "") or ""),
        "emotion_score": _optional_clamp_float(data.get("emotion_score")),
        "fatigue_score": _clamp_float(data.get("fatigue_score", 0.0)),
        "confidence": _clamp_float(data.get("confidence", 0.0)),
        "visible_evidence": _evidence_list(data.get("visible_evidence")),
        "valid_observation": bool(data.get("valid_observation", True)),
        "message": str(data.get("message", "") or ""),
    }
