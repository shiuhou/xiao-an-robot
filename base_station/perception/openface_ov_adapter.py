"""Adapter: wire OpenFace's OpenVINO perceive into xiao-an's OpenFaceCVPipeline.

This is the concrete in-process integration point for route A (Gate 4). The
production ``perceive()`` is OpenFace's ``tools/ov_perceive.build_ov_perceive``
(3 OpenVINO IR models + RetinaFace/STAR host-side decode), which lives in the
SEPARATE OpenFace repo. We import it via an explicit repo path so that:

  * the OV IR binaries / model assets stay in the OpenFace repo (red line: no
    large IR/binaries are copied into xiao-an), and
  * xiao-an's base_station consumes ``perceive`` purely as a Python callable.

The OpenFace repo location is resolved (in order) from the explicit
``openface_repo`` argument, the ``OPENFACE_REPO`` environment variable, then a
default dev path. Nothing here imports torch/openvino at module import time;
those are only pulled in when ``build_*`` is actually called (so unit tests that
merely import this module stay light).

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
from typing import Any, Callable

from base_station.perception.openface_cv_pipeline import OpenFaceCVPipeline

# Default dev location of the OpenFace 3.0 repo on this machine. Override with the
# ``OPENFACE_REPO`` env var or the ``openface_repo`` argument.
DEFAULT_OPENFACE_REPO = r"D:\openface3.0\OpenFace-3.0-full"


def _resolve_repo(openface_repo: str | None) -> str:
    repo = openface_repo or os.environ.get("OPENFACE_REPO") or DEFAULT_OPENFACE_REPO
    if not os.path.isdir(repo):
        raise FileNotFoundError(
            f"OpenFace repo not found: {repo!r}. "
            "Pass openface_repo=... or set the OPENFACE_REPO environment variable."
        )
    return repo


def build_ov_perceive_callable(
    openface_repo: str | None = None,
    models_dir: str = "models_ov",
    device: str = "CPU",
) -> Callable[[Any], dict | None]:
    """Return a ``perceive(frame) -> dict | None`` backed by OpenFace OV IR.

    ``frame`` may be either a xiao-an camera frame dict (``payload`` is the BGR
    ndarray) or a raw BGR ndarray. Returns None when there is no image payload;
    otherwise returns the OpenFace perceive contract dict (landmarks/
    face_confidence/emotion_label/emotion_confidence/au).
    """
    repo = _resolve_repo(openface_repo)
    tools_dir = os.path.join(repo, "tools")
    # ov_perceive.py self-inserts REPO_ROOT / Pytorch_Retinaface / STAR / tools
    # onto sys.path at import, but it must itself be importable first.
    for p in (repo, tools_dir):
        if p not in sys.path:
            sys.path.insert(0, p)

    import ov_perceive  # OpenFace tools/ov_perceive.py

    # models_dir is resolved by build_ov_perceive against the OpenFace repo root,
    # so a relative "models_ov" lands at <repo>/models_ov (IR stays in OpenFace).
    raw_perceive = ov_perceive.build_ov_perceive(models_dir=models_dir, device=device)

    def perceive(frame: Any) -> dict | None:
        img = frame.get("payload") if isinstance(frame, dict) else frame
        if img is None:
            return None
        return raw_perceive(img)

    return perceive


def build_openface_cv_pipeline(
    openface_repo: str | None = None,
    models_dir: str = "models_ov",
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
