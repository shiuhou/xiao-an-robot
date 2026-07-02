#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Route A PERCEPTION-ONLY live check for the bundled xiao-an OpenFace OV path.

This deliberately stops at the perception contract. It does NOT touch the brain,
the VLM, the gate, the websocket gateway, or the robot -- those are downstream
plumbing and are not where route A's value lives. The question this answers is:

    "On my live camera, what does route A's cv_sample (judgment layer) look like?"

Chain exercised (exactly the production cv_pipeline, nothing more):

    live camera frame (BGR) ->
      base_station.monitor.emotion_runtime.build_cv_pipeline("openface_ov") ->
        openface_ov_adapter -> bundled openface_ov_runtime ->
          OpenFaceCVPipeline.process_frame -> contract cv_sample  [PRINT]

NOTE: this prints the *contract* fields that cv_sample actually carries
(emotion_tag / confidence / fatigue_score / fatigue_level / valence /
observation_quality / presence_state / polarity). The raw perception indicators
(face_confidence / ear / mar / perclos / au) are NOT in cv_sample -- they are
consumed inside process_frame. To inspect those, use the raw-perception probe.

Run (conda 'openface' env, which hosts BOTH stacks):

    set KMP_DUPLICATE_LIB_OK=TRUE
    set OMP_NUM_THREADS=1
    python tools/probe_openface_routeA_live.py --count 60 --interval 1.0

Prints per-frame contract fields and an end summary (presence rate, emotion-tag
distribution, mean confidences/fatigue/quality). No PASS/FAIL verdict is forced
here -- this is for eyeballing route A's judgment-layer output.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# cv_sample numeric contract fields we summarize (mean/min/max), in print order.
# Missing keys are skipped gracefully so this keeps working if the contract grows.
_NUMERIC_FIELDS = (
    "confidence",
    "fatigue_score",
    "observation_quality",
)

# Default local OpenVINO Qwen2.5-VL int4 package (the real VLM backend).
_DEFAULT_VLM_MODEL_PATH = (
    r"C:\Users\Lenovo\Desktop\xiao-an-robot\xiao-an-robot"
    r"\base_station\models\Qwen2.5-VL-3B-OV-int4"
)


def _get(sample, *names):
    """First present key among names (sample is a dict-like contract sample)."""
    for n in names:
        if isinstance(sample, dict) and n in sample and sample[n] is not None:
            return sample[n]
    return None


def _fmt(v):
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def main():
    ap = argparse.ArgumentParser(description="Route A perception-only live check.")
    ap.add_argument("--openface-repo", default=None,
                    help="Optional external OpenFace repo for development. Defaults to bundled runtime.")
    ap.add_argument("--openface-models-dir", default=None,
                    help="OpenFace OV IR model directory. Defaults to base_station/models/openface_ov.")
    ap.add_argument("--camera-index", "--camera", dest="camera_index", type=int, default=0,
                    help="cv2.VideoCapture index")
    ap.add_argument("--count", type=int, default=60, help="frames to sample")
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between samples")
    ap.add_argument("--device", default="CPU")
    ap.add_argument("--enable-vlm-gate", action="store_true",
                    help="After each cv_sample, run VLMTriggerGate and (on trigger) the fake VLM.")
    ap.add_argument("--force-vlm", action="store_true",
                    help="Force the gate to trigger every frame (reason=force) to verify the VLM path.")
    ap.add_argument("--vlm-backend", default="vlm_face",
                    choices=["vlm_face", "fake", "qwen_vl", "openvino_qwen_vl"],
                    help="VLM backend on trigger. 'vlm_face' = REAL local Qwen2.5-VL "
                         "(implemented, recommended); 'fake'/'qwen_vl' = canned FakeQwenVL; "
                         "'openvino_qwen_vl' = unfinished stub, raises NotImplementedError.")
    ap.add_argument("--vlm-model-path", default=_DEFAULT_VLM_MODEL_PATH,
                    help="OpenVINO Qwen-VL model dir (used by real VLM backends).")
    ap.add_argument("--fatigue-threshold", type=float, default=70.0,
                    help="Gate fatigue_score threshold (cv_sample fatigue_score is 0-100).")
    ap.add_argument("--vlm-pattern", default="neutral",
                    choices=["neutral", "tired", "sad", "anxious", "mixed"],
                    help="Fake VLM output pattern (only used when --vlm-backend fake/qwen_vl).")
    args = ap.parse_args()

    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    if args.openface_repo:
        os.environ.setdefault("OPENFACE_REPO", args.openface_repo)
    if args.openface_models_dir:
        os.environ.setdefault("OPENFACE_OV_MODELS_DIR", args.openface_models_dir)

    import cv2
    import base_station.monitor.emotion_runtime as er

    # The exact production cv_pipeline the live runtime uses for route A.
    cv_pipeline = er.build_cv_pipeline(
        model_backend="openface_ov",
        pattern="neutral",
        model_path=None,
        device=args.device,
        openface_repo=args.openface_repo,
        openface_models_dir=args.openface_models_dir,
    )

    # Optional: gate + fake VLM (reuses the EXACT production gate + VLM factory).
    gate = vlm_model = context_builder = None
    if args.enable_vlm_gate:
        from base_station.perception.vlm_trigger_gate import VLMTriggerGate
        from base_station.monitor.emotion_context_builder import EmotionContextBuilder

        gate = VLMTriggerGate(fatigue_threshold=args.fatigue_threshold)
        context_builder = EmotionContextBuilder()
        print(f"[gate] fatigue_threshold={args.fatigue_threshold}  vlm_backend={args.vlm_backend}")
        if args.vlm_backend in ("vlm_face", "openvino_qwen_vl"):
            print(f"[vlm] loading REAL Qwen2.5-VL ({args.vlm_backend}) from {args.vlm_model_path} "
                  f"(first load is slow) ...")
        vlm_model = er.create_vlm_emotion_model(
            vlm_backend=args.vlm_backend,
            pattern=args.vlm_pattern,
            vlm_model_path=args.vlm_model_path,
            device=args.device,
        )
        print("[vlm] ready.\n")

    cap = cv2.VideoCapture(args.camera_index)
    if not cap.isOpened():
        print(f"Cannot open camera index {args.camera_index}", file=sys.stderr)
        return 2

    print(f"Route A perception-only: sampling {args.count} frames @ {args.interval}s ...\n")

    n_total = 0
    n_present = 0
    n_triggered = 0
    labels = Counter()
    presence = Counter()
    trigger_reasons = Counter()
    sums = {k: 0.0 for k in _NUMERIC_FIELDS}
    cnts = {k: 0 for k in _NUMERIC_FIELDS}
    mins = {k: float("inf") for k in _NUMERIC_FIELDS}
    maxs = {k: float("-inf") for k in _NUMERIC_FIELDS}
    first_keys_printed = False

    try:
        while n_total < args.count:
            ok, frame = cap.read()
            if not ok:
                print("camera read failed, stopping")
                break
            h, w = frame.shape[:2]
            n_total += 1
            frame_dict = {
                "source": "opencv_camera",
                "frame_id": n_total,
                "timestamp_ms": int(time.time() * 1000),
                "width": int(w),
                "height": int(h),
                "payload": frame,
            }

            sample = cv_pipeline.process_frame(frame_dict)

            if isinstance(sample, dict) and not first_keys_printed:
                print(f"[contract keys] {sorted(sample.keys())}\n")
                first_keys_printed = True

            presence_state = _get(sample, "presence_state")
            if presence_state is not None:
                presence[str(presence_state)] += 1
            if presence_state == "present":
                n_present += 1

            label = _get(sample, "emotion_tag")
            if label is not None:
                labels[str(label)] += 1

            for k in _NUMERIC_FIELDS:
                v = _get(sample, k)
                if v is not None:
                    try:
                        fv = float(v)
                    except (TypeError, ValueError):
                        continue
                    sums[k] += fv
                    cnts[k] += 1
                    mins[k] = min(mins[k], fv)
                    maxs[k] = max(maxs[k], fv)

            row = (
                f"#{n_total:>3} "
                f"emo={str(label) if label is not None else '-':<10} "
                f"conf={_fmt(_get(sample,'confidence')) if _get(sample,'confidence') is not None else '-':>6} "
                f"fscore={_fmt(_get(sample,'fatigue_score')) if _get(sample,'fatigue_score') is not None else '-':>6} "
                f"flevel={str(_get(sample,'fatigue_level')) if _get(sample,'fatigue_level') is not None else '-':<20} "
                f"val={str(_get(sample,'valence')) if _get(sample,'valence') is not None else '-':<10} "
                f"obs_q={_fmt(_get(sample,'observation_quality')) if _get(sample,'observation_quality') is not None else '-':>6} "
                f"presence={str(presence_state) if presence_state is not None else '-'}"
            )
            print(row)

            # gate + (on trigger) fake VLM -- pure observation, no judgment changes
            if gate is not None:
                gate_result = gate.evaluate(sample, force_vlm=args.force_vlm)
                triggered = bool(gate_result.get("should_trigger"))
                reason = str(gate_result.get("reason", "normal"))
                trigger_reasons[reason] += 1
                print(f"      gate  : trigger={triggered}  reason={reason}")
                if triggered:
                    n_triggered += 1
                    context = context_builder.build(cv_sample=sample, history_summary=None)
                    vlm_out = vlm_model.predict(frame_dict, context)
                    print(f"      VLM  -> {json.dumps(vlm_out, ensure_ascii=False)}")

            time.sleep(max(0.0, args.interval))
    finally:
        cap.release()

    print("\n==== ROUTE A PERCEPTION SUMMARY ====")
    print(f"frames sampled      : {n_total}")
    if n_total:
        print(f"present rate        : {n_present}/{n_total} = {100.0*n_present/n_total:.1f}%")
    print(f"presence states     : {dict(presence)}")
    print(f"emotion tags        : {dict(labels)}")
    if gate is not None:
        print(f"VLM triggers        : {n_triggered}/{n_total}")
        print(f"trigger reasons     : {dict(trigger_reasons)}")
    for k in _NUMERIC_FIELDS:
        if cnts[k]:
            print(
                f"  {k:<20}: mean={sums[k]/cnts[k]:.3f}  "
                f"min={mins[k]:.3f}  max={maxs[k]:.3f}  (n={cnts[k]})"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
