"""OpenVINO face emotion and fatigue CV model.

The module is cheap to import. OpenVINO is imported only when an
``OpenVINOFaceEmotionModel`` instance is created, and OpenCV is imported only
when frame preprocessing or real prediction runs.
"""

from __future__ import annotations

import logging
import os
import time
from collections import deque
from pathlib import Path
from typing import Any

try:
    import numpy as np
except ImportError:  # pragma: no cover - default test env has numpy
    np = None


log = logging.getLogger("openvino_face_emotion")

EMOTION_LABELS = [
    "neutral",
    "happiness",
    "surprise",
    "sadness",
    "anger",
    "disgust",
    "fear",
    "contempt",
]

FERPLUS_TO_GATE = {
    "sadness": "sad",
    "anger": "stressed",
}

SIDE_FACE_YAW_THRESHOLD = 20
EAR_CONSEC_FRAMES = 3
YAWN_CONSEC_FRAMES = 15
HEAD_PITCH_THRESHOLD = -15
EMA_ALPHA = 0.3
ADAPTIVE_BASELINE_ALPHA = 0.005
NORMAL_BLINK_RATE_LOW = 10
NORMAL_BLINK_RATE_HIGH = 25
HISTORY_SECONDS = 60
CALIBRATION_FRAMES = 20

_MODEL_RELPATHS = {
    "face": os.path.join("intel", "face-detection-0206", "FP32", "face-detection-0206.xml"),
    "emotion": os.path.join("hsemotion", "emotion-ferplus-8.onnx"),
    "landmark": os.path.join(
        "intel",
        "facial-landmarks-35-adas-0002",
        "FP32",
        "facial-landmarks-35-adas-0002.xml",
    ),
    "head_pose": os.path.join(
        "intel",
        "head-pose-estimation-adas-0001",
        "FP32",
        "head-pose-estimation-adas-0001.xml",
    ),
}

DEFAULT_MODEL_ROOT = Path(__file__).resolve().parents[1] / "models"


def _load_openvino_core() -> Any:
    try:
        try:
            from openvino.runtime import Core
        except ImportError:
            from openvino import Core
    except ImportError as exc:
        raise ImportError(
            "OpenVINO is not installed. Install openvino to use OpenVINOFaceEmotionModel."
        ) from exc
    return Core


def _resolve_model_paths(model_path: str | None = None, model_root: str | None = None) -> dict[str, str]:
    root_value = model_root or model_path or os.environ.get("OPENVINO_MODEL_DIR") or DEFAULT_MODEL_ROOT
    root = Path(root_value)
    paths = {key: str(root / rel) for key, rel in _MODEL_RELPATHS.items()}
    missing = [p for p in paths.values() if not Path(p).exists()]
    if missing:
        expected = "\n".join(f"  - {root / rel}" for rel in _MODEL_RELPATHS.values())
        raise FileNotFoundError(
            "OpenVINO CV model(s) not found. Set OPENVINO_MODEL_DIR or pass "
            "--model-path to a model root containing:\n"
            f"{expected}\n"
            f"Missing: {missing}"
        )
    return paths


def _softmax(x):
    if np is None:
        raise ImportError("numpy is required for OpenVINO face emotion inference.")
    x = x - np.max(x)
    e = np.exp(x)
    return e / np.sum(e)


class _EMAFilter:
    def __init__(self, alpha: float = EMA_ALPHA):
        self.alpha = alpha
        self.value = None

    def update(self, raw):
        self.value = raw if self.value is None else self.alpha * raw + (1 - self.alpha) * self.value
        return self.value


def _single_eye_ear(pts, c1, c2, t, b, fw, fh):
    p = pts.reshape(-1, 2).copy()
    p[:, 0] *= fw
    p[:, 1] *= fh
    horiz = np.linalg.norm(p[c1] - p[c2])
    vert = np.linalg.norm(p[t] - p[b])
    return vert / horiz if horiz > 1e-6 else 0.3


def _ear_with_yaw(landmarks, fw, fh, yaw):
    left = _single_eye_ear(landmarks, 0, 1, 12, 13, fw, fh)
    right = _single_eye_ear(landmarks, 2, 3, 14, 15, fw, fh)
    if abs(yaw) < SIDE_FACE_YAW_THRESHOLD:
        return (left + right) / 2.0
    return left if yaw > 0 else right


def _mar(landmarks, fw, fh):
    pts = landmarks.reshape(-1, 2).copy()
    pts[:, 0] *= fw
    pts[:, 1] *= fh
    horiz = np.linalg.norm(pts[6] - pts[7])
    vert = (np.linalg.norm(pts[8] - pts[10]) + np.linalg.norm(pts[9] - pts[11])) / 2.0
    return vert / horiz if horiz > 1e-6 else 0.0


class _Calibration:
    def __init__(self):
        self.ear_samples = []
        self.mar_samples = []
        self.ear_baseline = 0.28
        self.mar_baseline = 0.25
        self.ear_threshold = 0.22
        self.mar_threshold = 0.55
        self.calibrated = False

    def add_sample(self, ear, mar):
        self.ear_samples.append(ear)
        self.mar_samples.append(mar)

    def finalize(self):
        if len(self.ear_samples) < 10:
            return
        ear_arr = np.array(self.ear_samples)
        mar_arr = np.array(self.mar_samples)
        el, eh = np.percentile(ear_arr, [10, 90])
        ml, mh = np.percentile(mar_arr, [10, 90])
        ear_clean = ear_arr[(ear_arr >= el) & (ear_arr <= eh)]
        mar_clean = mar_arr[(mar_arr >= ml) & (mar_arr <= mh)]
        if len(ear_clean) < 5:
            ear_clean = ear_arr
        if len(mar_clean) < 5:
            mar_clean = mar_arr
        self.ear_baseline = float(np.mean(ear_clean))
        self.mar_baseline = float(np.mean(mar_clean))
        self.ear_threshold = max(self.ear_baseline - 1.5 * float(np.std(ear_clean)), 0.10)
        self.mar_threshold = max(self.mar_baseline + 2.0 * float(np.std(mar_clean)), 0.35)
        self.calibrated = True
        log.info("Calibration done: EAR thresh=%.3f MAR thresh=%.3f", self.ear_threshold, self.mar_threshold)

    def adaptive_update(self, ear):
        if not self.calibrated:
            return
        if abs(ear - self.ear_baseline) < 0.08:
            self.ear_baseline = (1 - ADAPTIVE_BASELINE_ALPHA) * self.ear_baseline + ADAPTIVE_BASELINE_ALPHA * ear
            std_approx = max(abs(self.ear_baseline - self.ear_threshold) / 1.5, 0.02)
            self.ear_threshold = max(self.ear_baseline - 1.5 * std_approx, 0.10)


class _FatigueDetector:
    def __init__(self, cal: _Calibration):
        self.cal = cal
        self.eye_closed_frames = 0
        self.yawn_frames = 0
        self.blink_timestamps = deque()
        self.yawn_timestamps = deque()
        self.head_nod_timestamps = deque()
        self.perclos_frames = deque()
        self.ear_filter = _EMAFilter()
        self.mar_filter = _EMAFilter()
        self.pitch_filter = _EMAFilter()

    def update(self, raw_ear, raw_mar, raw_pitch):
        ear = self.ear_filter.update(raw_ear)
        mar = self.mar_filter.update(raw_mar)
        pitch = self.pitch_filter.update(raw_pitch)
        now = time.time()
        cutoff = now - HISTORY_SECONDS

        if ear < self.cal.ear_threshold:
            self.eye_closed_frames += 1
        else:
            if self.eye_closed_frames >= EAR_CONSEC_FRAMES:
                self.blink_timestamps.append(now)
            self.eye_closed_frames = 0
            self.cal.adaptive_update(raw_ear)

        self.perclos_frames.append((now, ear < self.cal.ear_threshold))
        while self.perclos_frames and self.perclos_frames[0][0] < cutoff:
            self.perclos_frames.popleft()

        if mar > self.cal.mar_threshold:
            self.yawn_frames += 1
        else:
            if self.yawn_frames >= YAWN_CONSEC_FRAMES:
                self.yawn_timestamps.append(now)
            self.yawn_frames = 0

        if pitch < HEAD_PITCH_THRESHOLD:
            self.head_nod_timestamps.append(now)

        for dq in (self.blink_timestamps, self.yawn_timestamps, self.head_nod_timestamps):
            while dq and dq[0] < cutoff:
                dq.popleft()

    def get_perclos(self):
        if not self.perclos_frames:
            return 0.0
        return sum(1 for _, c in self.perclos_frames if c) / len(self.perclos_frames)

    def get_fatigue(self, signal_quality=1.0, face_lost_dur=0.0):
        perclos = self.get_perclos()
        yawns = len(self.yawn_timestamps)
        nods = len(self.head_nod_timestamps)
        blinks = len(self.blink_timestamps)

        score = 0.0
        score += min(perclos / 0.4, 1.0) * 35
        score += min(yawns / 3.0, 1.0) * 25
        score += min(nods / 20.0, 1.0) * 15
        if blinks < NORMAL_BLINK_RATE_LOW:
            score += min((NORMAL_BLINK_RATE_LOW - blinks) / NORMAL_BLINK_RATE_LOW, 1.0) * 15
        elif blinks > NORMAL_BLINK_RATE_HIGH:
            score += min((blinks - NORMAL_BLINK_RATE_HIGH) / 15.0, 1.0) * 15
        if face_lost_dur > 5:
            score += min((face_lost_dur - 5) / 15.0, 1.0) * 10

        neutral = 15.0
        score = neutral + (score - neutral) * signal_quality
        return max(0.0, min(score, 100.0))


class OpenVINOFaceEmotionModel:
    """OpenVINO-backed face emotion model.

    ``model_path`` may be either a single model file (legacy placeholder mode
    used by unit tests) or a model root directory containing the real CV model
    layout. If omitted, ``OPENVINO_MODEL_DIR`` and then ``base_station/models``
    are checked before OpenVINO is imported.
    """

    def __init__(
        self,
        model_path: str | None = None,
        device: str = "CPU",
        input_size: tuple[int, int] = (224, 224),
        normalize: bool = True,
        bgr_to_rgb: bool = True,
        model_root: str | None = None,
    ):
        self.device = device
        self.input_size = input_size
        self.normalize = normalize
        self.bgr_to_rgb = bgr_to_rgb
        self._legacy_single_model = False

        explicit_path = Path(model_path) if model_path else None
        if explicit_path is not None and explicit_path.suffix and not explicit_path.exists():
            raise FileNotFoundError(f"OpenVINO model path does not exist: {model_path}")

        if explicit_path is not None and explicit_path.is_file():
            Core = _load_openvino_core()
            self.core = Core()
            self._init_single_model(str(explicit_path))
        else:
            self.model_paths = _resolve_model_paths(model_path=model_path, model_root=model_root)
            Core = _load_openvino_core()
            self.core = Core()
            self._init_real_models(model_path=model_path, model_root=model_root)

    @staticmethod
    def _load_openvino_core() -> Any:
        return _load_openvino_core()

    def _init_single_model(self, model_path: str) -> None:
        self._legacy_single_model = True
        self.model_path = model_path
        self.model = self.core.read_model(self.model_path)
        self.compiled_model = self.core.compile_model(self.model, self.device)
        self.inputs = list(getattr(self.compiled_model, "inputs", []) or [])
        self.outputs = list(getattr(self.compiled_model, "outputs", []) or [])
        self.input_layer = self.inputs[0] if self.inputs else None
        self.output_layer = self.outputs[0] if self.outputs else None

    def _init_real_models(self, model_path: str | None, model_root: str | None) -> None:
        if np is None:
            raise ImportError("numpy is required for OpenVINO face emotion inference.")
        self.model_path = str(Path(model_root or model_path or os.environ.get("OPENVINO_MODEL_DIR") or DEFAULT_MODEL_ROOT))
        self._face_net = self.core.compile_model(self.model_paths["face"], self.device)
        self._emotion_net = self.core.compile_model(self.model_paths["emotion"], self.device)
        self._landmark_net = self.core.compile_model(self.model_paths["landmark"], self.device)
        self._head_pose_net = self.core.compile_model(self.model_paths["head_pose"], self.device)
        self.cal = _Calibration()
        self.fatigue = _FatigueDetector(self.cal)
        self._frame_count = 0
        self._face_lost_start: float | None = None
        self._last_fatigue = 0.0

    def preprocess(self, frame: dict):
        if "payload" not in frame or frame["payload"] is None:
            raise ValueError("OpenVINOFaceEmotionModel.preprocess requires frame['payload'] image data.")
        if np is None:
            raise ImportError("numpy is required to preprocess OpenVINO face emotion frames.")
        try:
            import cv2  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError("opencv-python is required to preprocess OpenVINO face emotion frames.") from exc

        image = frame["payload"]
        if not isinstance(image, np.ndarray):
            image = np.asarray(image)

        input_height, input_width = self.input_size
        image = cv2.resize(image, (input_width, input_height))
        if self.bgr_to_rgb:
            image = image[:, :, ::-1]

        image = image.astype(np.float32)
        if self.normalize:
            image = image / 255.0

        return image.transpose(2, 0, 1)[None, ...]

    def infer(self, input_tensor):
        return self.compiled_model(input_tensor)

    def postprocess(self, outputs) -> dict:
        raise NotImplementedError("OpenVINO inference postprocessing is not implemented yet.")

    def _detect_face(self, frame, cv2):
        h, w = frame.shape[:2]
        blob = cv2.resize(frame, (640, 640)).transpose(2, 0, 1)[np.newaxis].astype(np.float32)
        boxes = self._face_net([blob])[self._face_net.output(0)]
        best, best_conf = None, 0.0
        for d in boxes:
            conf = float(d[4])
            if conf > best_conf and conf > 0.5:
                best_conf, best = conf, d
        if best is None:
            return None, 0.0
        sx, sy = w / 640.0, h / 640.0
        x1 = max(0, int(best[0] * sx))
        y1 = max(0, int(best[1] * sy))
        x2 = min(w, int(best[2] * sx))
        y2 = min(h, int(best[3] * sy))
        return (x1, y1, x2, y2), best_conf

    def _get_emotion(self, face, cv2, yaw=0.0):
        gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
        blob = cv2.resize(gray, (64, 64)).astype(np.float32)[np.newaxis, np.newaxis]
        res = self._emotion_net([blob])[self._emotion_net.output(0)]
        probs = _softmax(res[0])
        idx = int(np.argmax(probs))
        confidence = float(probs[idx])
        if abs(yaw) > SIDE_FACE_YAW_THRESHOLD:
            confidence *= max(0.3, 1.0 - (abs(yaw) - SIDE_FACE_YAW_THRESHOLD) / 45.0)
        return EMOTION_LABELS[idx], confidence

    def _get_landmarks(self, face, cv2):
        blob = cv2.resize(face, (60, 60)).transpose(2, 0, 1)[np.newaxis].astype(np.float32)
        return self._landmark_net([blob])[self._landmark_net.output(0)][0]

    def _get_head_pose(self, face, cv2):
        blob = cv2.resize(face, (60, 60)).transpose(2, 0, 1)[np.newaxis].astype(np.float32)
        res = self._head_pose_net([blob])
        yaw = res[self._head_pose_net.output(0)][0][0]
        pitch = res[self._head_pose_net.output(1)][0][0]
        roll = None
        try:
            roll = float(res[self._head_pose_net.output(2)][0][0])
        except (IndexError, KeyError, TypeError):
            roll = None
        return float(yaw), float(pitch), roll

    @staticmethod
    def _signal_quality(brightness, face_conf):
        q = 1.0
        if brightness < 50 or brightness > 220:
            q *= 0.3
        elif brightness < 80:
            q *= 0.7
        if face_conf < 0.7:
            q *= 0.5
        elif face_conf < 0.85:
            q *= 0.8
        return q

    def predict(self, frame: dict) -> dict:
        if self._legacy_single_model:
            input_tensor = self.preprocess(frame)
            outputs = self.infer(input_tensor)
            return self.postprocess(outputs)

        if "payload" not in frame or frame["payload"] is None:
            raise ValueError("OpenVINOFaceEmotionModel.predict requires frame['payload'] image.")
        if np is None:
            raise ImportError("numpy is required for OpenVINO face emotion inference.")
        try:
            import cv2  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError("opencv-python is required for OpenVINO face emotion inference.") from exc

        image = frame["payload"]
        if not isinstance(image, np.ndarray):
            image = np.asarray(image)

        self._frame_count += 1
        brightness = float(np.mean(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)))
        rect, conf = self._detect_face(image, cv2)

        fer_label = "neutral"
        emotion_conf = 0.0
        face_detected = False
        debug = {
            "face_box": None,
            "landmarks": None,
            "ear": None,
            "mar": None,
            "head_pose": {
                "yaw": None,
                "pitch": None,
                "roll": None,
            },
            "perclos": None,
            "blink_score": None,
            "yawn_score": None,
        }

        if rect is not None:
            x1, y1, x2, y2 = rect
            face = image[y1:y2, x1:x2]
            if face.size > 0:
                face_detected = True
                self._face_lost_start = None
                fh, fw = face.shape[:2]
                lm = self._get_landmarks(face, cv2)
                yaw, pitch, roll = self._get_head_pose(face, cv2)
                fer_label, emotion_conf = self._get_emotion(face, cv2, yaw)
                ear = _ear_with_yaw(lm.copy(), fw, fh, yaw)
                mar = _mar(lm.copy(), fw, fh)
                if not self.cal.calibrated:
                    self.cal.add_sample(ear, mar)
                    if self._frame_count >= CALIBRATION_FRAMES:
                        self.cal.finalize()
                self.fatigue.update(ear, mar, pitch)
                self._last_fatigue = self.fatigue.get_fatigue(
                    self._signal_quality(brightness, conf),
                    self._face_lost_duration(),
                )
                landmark_points = lm.reshape(-1, 2).copy()
                landmark_points[:, 0] = landmark_points[:, 0] * fw + x1
                landmark_points[:, 1] = landmark_points[:, 1] * fh + y1
                debug.update({
                    "face_box": [x1, y1, x2, y2],
                    "landmarks": landmark_points.tolist(),
                    "ear": float(ear),
                    "mar": float(mar),
                    "head_pose": {
                        "yaw": yaw,
                        "pitch": pitch,
                        "roll": roll,
                    },
                    "perclos": float(self.fatigue.get_perclos()),
                })
        else:
            if self._face_lost_start is None:
                self._face_lost_start = time.time()

        return {
            "emotion_tag": FERPLUS_TO_GATE.get(fer_label, "neutral"),
            "cv_emotion_raw": fer_label,
            "confidence": emotion_conf,
            "fatigue_score": max(0.0, min(1.0, self._last_fatigue / 100.0)),
            "face_detected": face_detected,
            "calibrated": self.cal.calibrated,
            "source": "openvino_face",
            "frame_source": frame.get("source"),
            "frame_id": frame.get("frame_id"),
            "timestamp_ms": frame.get("timestamp_ms"),
            "debug": debug,
        }

    def _face_lost_duration(self) -> float:
        return 0.0 if self._face_lost_start is None else time.time() - self._face_lost_start
