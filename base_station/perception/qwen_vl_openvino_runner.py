"""OpenVINO Qwen VL runner shell with lazy heavy dependencies."""

from __future__ import annotations

from importlib import import_module
import json
from pathlib import Path
import time
from typing import Any


EMOTION_TAGS = ("neutral", "tired", "sad", "anxious", "stressed", "happy", "unknown")
OUTPUT_FIELDS = ("emotion_tag", "confidence", "fatigue_score", "visual_reason", "vlm_observation")


class QwenVLOpenVINORunner:
    """Configuration shell for an OpenVINO/Optimum Intel Qwen2.5-VL runner."""

    def __init__(
        self,
        model_dir: str,
        device: str = "AUTO",
        max_new_tokens: int = 128,
    ):
        if not model_dir:
            raise ValueError("model_dir must not be empty.")
        if max_new_tokens <= 0:
            raise ValueError("max_new_tokens must be greater than 0.")

        self.model_dir = str(Path(model_dir).expanduser())
        self.device = device
        self.max_new_tokens = max_new_tokens
        self.last_timings: dict[str, float] = {}
        self._model: Any | None = None
        self._processor: Any | None = None
        self._vision_processor: Any | None = None
        self._loaded = False

    def load(self) -> None:
        """Load the OpenVINO Qwen VL model lazily."""

        if self._loaded:
            return

        started = time.perf_counter()
        self._validate_model_dir()
        deps = self._import_dependencies()

        try:
            processor = deps["AutoProcessor"].from_pretrained(
                self.model_dir,
                trust_remote_code=True,
            )
            model = deps["OVModelForVisualCausalLM"].from_pretrained(
                self.model_dir,
                device=self.device,
                trust_remote_code=True,
            )
        except Exception as exc:
            raise RuntimeError(
                "Failed to load Qwen2.5-VL OpenVINO model from "
                f"{self.model_dir!r} on device {self.device!r}: {exc}"
            ) from exc

        self._processor = processor
        self._model = model
        self._vision_processor = deps["process_vision_info"]
        self._loaded = True
        self.last_timings["load_seconds"] = time.perf_counter() - started

    def generate(self, image, prompt: str, context: dict | None = None) -> str:
        if not prompt or not prompt.strip():
            raise ValueError("prompt must not be empty.")

        started = time.perf_counter()
        self.load()
        after_load = time.perf_counter()
        if self._model is None or self._processor is None or self._vision_processor is None:
            raise RuntimeError("Qwen2.5-VL OpenVINO runner failed to initialize.")

        model_image = self._prepare_image_for_model(image)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": model_image},
                    {"type": "text", "text": prompt},
                ],
            }
        ]

        try:
            text = self._processor.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
            image_inputs, video_inputs = self._vision_processor(messages)
            inputs = self._processor(
                text=[text],
                images=image_inputs,
                videos=video_inputs,
                padding=True,
                return_tensors="pt",
            )
            generated_ids = self._model.generate(**inputs, max_new_tokens=self.max_new_tokens)
            generated_ids_trimmed = [
                output_ids[len(input_ids):]
                for input_ids, output_ids in zip(inputs.input_ids, generated_ids)
            ]
            decoded = self._processor.batch_decode(
                generated_ids_trimmed,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )
        except Exception as exc:
            raise RuntimeError(f"Qwen2.5-VL OpenVINO generation failed: {exc}") from exc

        if not decoded:
            raise RuntimeError("Qwen2.5-VL OpenVINO generation returned no text.")
        finished = time.perf_counter()
        self.last_timings["generate_seconds"] = finished - after_load
        self.last_timings["total_seconds"] = finished - started
        return str(decoded[0]).strip()

    @staticmethod
    def _prepare_image_for_model(image):
        shape = getattr(image, "shape", None)
        if shape is None:
            return image

        try:
            from PIL import Image  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError(
                "QwenVLOpenVINORunner received an ndarray image and requires Pillow "
                "to convert it for Qwen VL processing."
            ) from exc

        try:
            import cv2  # type: ignore[import-not-found]
        except ImportError:
            cv2 = None

        array = image
        if cv2 is not None and len(shape) == 3 and int(shape[2]) == 3:
            array = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        return Image.fromarray(array)

    def _validate_model_dir(self) -> None:
        path = Path(self.model_dir)
        if not path.exists():
            raise FileNotFoundError(
                "Qwen2.5-VL OpenVINO model directory does not exist: "
                f"{self.model_dir}. Export or copy the model directory before running."
            )
        if not path.is_dir():
            raise RuntimeError(f"Qwen2.5-VL OpenVINO model path is not a directory: {self.model_dir}")
        if not any(path.glob("*.xml")) or not any(path.glob("*.bin")):
            raise RuntimeError(
                "Qwen2.5-VL OpenVINO model directory format mismatch: "
                f"{self.model_dir} does not contain top-level OpenVINO .xml and .bin files. "
                "Use an OpenVINO/Optimum Intel exported Qwen2.5-VL-3B Instruct directory, "
                "not the original Hugging Face PyTorch model directory."
            )

    @staticmethod
    def _import_dependencies() -> dict[str, Any]:
        missing: list[str] = []

        try:
            transformers = import_module("transformers")
        except ImportError:
            missing.append("transformers")
            transformers = None

        try:
            optimum_openvino = import_module("optimum.intel.openvino")
        except ImportError:
            missing.append("optimum-intel[openvino]")
            optimum_openvino = None

        try:
            qwen_vl_utils = import_module("qwen_vl_utils")
        except ImportError:
            missing.append("qwen-vl-utils")
            qwen_vl_utils = None

        if missing:
            raise ImportError(
                "QwenVLOpenVINORunner requires missing package(s): "
                + ", ".join(missing)
                + ". Install the OpenVINO/Optimum Intel Qwen VL runtime in the local environment."
            )

        AutoProcessor = getattr(transformers, "AutoProcessor", None)
        OVModelForVisualCausalLM = getattr(optimum_openvino, "OVModelForVisualCausalLM", None)
        process_vision_info = getattr(qwen_vl_utils, "process_vision_info", None)
        if AutoProcessor is None:
            raise ImportError("transformers.AutoProcessor is required for QwenVLOpenVINORunner.")
        if OVModelForVisualCausalLM is None:
            raise ImportError(
                "optimum.intel.openvino.OVModelForVisualCausalLM is required for QwenVLOpenVINORunner."
            )
        if process_vision_info is None:
            raise ImportError("qwen_vl_utils.process_vision_info is required for QwenVLOpenVINORunner.")

        return {
            "AutoProcessor": AutoProcessor,
            "OVModelForVisualCausalLM": OVModelForVisualCausalLM,
            "process_vision_info": process_vision_info,
        }


def build_emotion_analysis_prompt(context: dict | None = None) -> str:
    lines = [
        "Analyze the user's visible emotional state from the image.",
        "Return JSON only, with these fields:",
        json.dumps({field: "<value>" for field in OUTPUT_FIELDS}, ensure_ascii=False),
        "emotion_tag must be one of: " + ", ".join(EMOTION_TAGS) + ".",
        "confidence and fatigue_score must be numbers from 0.0 to 1.0.",
        "visual_reason should explain visible evidence briefly.",
        "vlm_observation should summarize the user's apparent state briefly.",
    ]

    if context:
        lines.append("Context summary:")
        for key in ("cv", "vlm", "asr", "history"):
            if key in context:
                lines.append(f"{key}: {json.dumps(context[key], ensure_ascii=False, sort_keys=True)}")

    return "\n".join(lines)
