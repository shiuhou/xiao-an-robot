"""Adapter: wire OpenFace's OpenVINO perceive into xiao-an's OpenFaceCVPipeline.

This is the concrete in-process integration point for route A (Gate 4). The
default runtime is vendored in this repository under
``base_station/perception/openface_ov_runtime`` and loads IR from
``base_station/models/openface_ov``. An external OpenFace repo can still be
provided for development by passing ``openface_repo`` or setting
``OPENFACE_REPO``.

Nothing here imports torch/openvino at module import time; those are only pulled
in when ``build_*`` is actually called (so unit tests that merely import this
module stay light).

Frame contract bridge
---------------------
xiao-an frame sources (opencv_camera / fake_camera) yield a *dict*:
    {"source", "frame_id", "timestamp_ms", "width", "height", "payload"}
where ``payload`` is the BGR uint8 ndarray (or None). OpenFace's ``perceive``
expects the raw BGR ndarray. This adapter unwraps ``payload`` before calling it,
so ``OpenFaceCVPipeline`` (which forwards whatever frame it is handed to
``perceive``) plugs straight into ``VLMGatedCameraEmotionSource``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable

from base_station.perception.openface_cv_pipeline import OpenFaceCVPipeline

_THIS_DIR = Path(__file__).resolve().parent
DEFAULT_RUNTIME_DIR = _THIS_DIR / "openface_ov_runtime"
DEFAULT_MODELS_DIR = _THIS_DIR.parent / "models" / "openface_ov"


def _resolve_runtime(openface_repo: str | None) -> tuple[str, str]:
    repo = openface_repo or os.environ.get("OPENFACE_REPO")
    if repo:
        repo_path = Path(repo)
        tools_dir = repo_path / "tools"
        if not tools_dir.is_dir():
            raise FileNotFoundError(
                f"OpenFace tools directory not found: {str(tools_dir)!r}. "
                "Pass a valid openface_repo or unset OPENFACE_REPO to use the bundled runtime."
            )
        return str(repo_path), str(tools_dir)

    if not DEFAULT_RUNTIME_DIR.is_dir():
        raise FileNotFoundError(
            f"Bundled OpenFace OV runtime not found: {str(DEFAULT_RUNTIME_DIR)!r}."
        )
    return str(DEFAULT_RUNTIME_DIR), str(DEFAULT_RUNTIME_DIR)


def _resolve_models_dir(models_dir: str | None) -> str:
    resolved = models_dir or os.environ.get("OPENFACE_OV_MODELS_DIR") or str(DEFAULT_MODELS_DIR)
    if not os.path.isdir(resolved):
        raise FileNotFoundError(
            f"OpenFace OV models directory not found: {resolved!r}. "
            "Pass openface_models_dir=... or set OPENFACE_OV_MODELS_DIR."
        )
    return resolved


def build_ov_perceive_callable(
    openface_repo: str | None = None,
    models_dir: str | None = None,
    device: str = "CPU",
) -> Callable[[Any], dict | None]:
    """Return a ``perceive(frame) -> dict | None`` backed by OpenFace OV IR.

    ``frame`` may be either a xiao-an camera frame dict (``payload`` is the BGR
    ndarray) or a raw BGR ndarray. Returns None when there is no image payload;
    otherwise returns the OpenFace perceive contract dict (landmarks/
    face_confidence/emotion_label/emotion_confidence/au).
    """
    runtime_root, tools_dir = _resolve_runtime(openface_repo)
    # ov_perceive.py self-inserts its runtime root / Pytorch_Retinaface / STAR
    # onto sys.path at import, but it must itself be importable first.
    for p in (runtime_root, tools_dir):
        if p not in sys.path:
            sys.path.insert(0, p)

    import ov_perceive

    raw_perceive = ov_perceive.build_ov_perceive(
        models_dir=_resolve_models_dir(models_dir),
        device=device,
    )

    def perceive(frame: Any) -> dict | None:
        img = frame.get("payload") if isinstance(frame, dict) else frame
        if img is None:
            return None
        return raw_perceive(img)

    return perceive


def build_openface_cv_pipeline(
    openface_repo: str | None = None,
    models_dir: str | None = None,
    device: str = "CPU",
    window_seconds: float = 20.0,
    **pipeline_kwargs: Any,
) -> OpenFaceCVPipeline:
    """Build an ``OpenFaceCVPipeline`` driven by the real OpenFace OV perceive.

    The returned object exposes ``process_frame(frame_dict) -> cv_sample`` and is
    intended to be passed as ``cv_pipeline`` to ``VLMGatedCameraEmotionSource``.
    """
    perceive = build_ov_perceive_callable(
        openface_repo=openface_repo, models_dir=models_dir, device=device
    )
    return OpenFaceCVPipeline(
        perceive=perceive, window_seconds=window_seconds, **pipeline_kwargs
    )
