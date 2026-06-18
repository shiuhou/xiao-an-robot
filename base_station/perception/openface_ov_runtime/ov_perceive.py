#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""OpenVINO IR perception pipeline for OpenFace 3.0 (host-side decode).

This module wires the three exported OpenVINO IR models
(``models_ov/{retinaface,star,mtl}/<name>.xml``) to the EXISTING host-side
decode code that lives in this repo (PriorBox/decode/NMS for RetinaFace, the
STAR ``Alignment`` crop/denorm/postprocess, and the MTL emotion/AU heads).
Only the THREE model forward calls are swapped from PyTorch to
``OVModelRunner.infer(...)``; everything around them mirrors the real
``realtime_demo.annotate_largest_face`` flow exactly so the numbers match the
original torch path.

Public API
----------
    from tools.ov_perceive import build_ov_perceive
    perceive = build_ov_perceive(models_dir="models_ov", device="CPU")
    out = perceive(frame_bgr)   # frame_bgr: OpenCV BGR uint8 ndarray

``perceive`` returns a dict with this contract (always these 5 keys):
    {
        "landmarks":          np.ndarray shape (98, 2) in the CROPPED-face
                              coordinate system, or None if no face,
        "face_confidence":    float (0.0 when no face),
        "emotion_label":      str (one of demo2.expression_labels) or None,
        "emotion_confidence": float (softmax max) or None,
        "au":                 list[float] length 8 or None,
    }

Run requirements (user's machine):
    conda activate openface          # provides torch / cv2 / openvino / PIL
    # IR already exported to models_ov/ via tools/export_ov_ir.py

This file deliberately imports the LOW-LEVEL decode modules directly
(Pytorch_Retinaface.* and STAR.demo.*) and NOT demo2 / realtime_demo, to avoid
pulling in dlib / matplotlib. The numpy constants and label list that live in
demo2 are duplicated here as small literals (kept in sync with demo2).
"""

from __future__ import annotations

import os
import sys

# --- make repo packages importable regardless of CWD (mirror ov_conversion_spike) ---
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = _THIS_DIR
for _p in (
    REPO_ROOT,
    os.path.join(REPO_ROOT, "Pytorch_Retinaface"),
    os.path.join(REPO_ROOT, "STAR"),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# tools/ on path so "from ov_runner import OVModelRunner" works.
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

# These are safe in the conda 'openface' env. They are NOT deferred (unlike
# openvino inside OVModelRunner) because torch/cv2/PIL are always present there.
import cv2
import numpy as np
import torch
from PIL import Image
from torchvision import transforms

from ov_runner import OVModelRunner

# --- low-level decode imports (no dlib / matplotlib pulled in) ----------------
from Pytorch_Retinaface.data import cfg_mnet
from Pytorch_Retinaface.layers.functions.prior_box import PriorBox
from Pytorch_Retinaface.utils.box_utils import decode, decode_landm
from Pytorch_Retinaface.utils.nms.py_cpu_nms import py_cpu_nms

# STAR crop/denorm helpers. Importing STAR.demo only touches cv2/numpy/torch and
# STAR.lib (no dlib at import time; dlib is only used under __main__ there).
from STAR.demo import GetCropMatrix, TransformPerspective

# --- constants duplicated from demo2 (kept in sync, NOT imported to dodge dlib) ---
# demo2.expression_labels (8 classes, in head order).
EXPRESSION_LABELS = [
    "Neutral", "Happy", "Sad", "Surprise", "Fear", "Disgust", "Anger", "Contempt",
]

# demo2.transform : Resize(224) + ToTensor + ImageNet normalize.
_MTL_TRANSFORM = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

# RetinaFace BGR mean (demo2.preprocess_image line 45).
_RETINA_MEAN = (104, 117, 123)

# STAR config (STAR/demo.py Alignment defaults: input_size=256, target_face_scale=1.0,
# GetCropMatrix align_corners=True).
_STAR_INPUT_SIZE = 256
_STAR_TARGET_FACE_SCALE = 1.0


def _empty_result():
    return {
        "landmarks": None,
        "face_confidence": 0.0,
        "emotion_label": None,
        "emotion_confidence": None,
        "au": None,
    }


# =============================================================================
# Seam 1: RetinaFace detect (replaces demo2.preprocess_image forward at line 50)
# =============================================================================
def _detect_faces(frame_bgr, retina_runner, resize=1,
                  confidence_threshold=0.02, nms_threshold=0.4):
    """Replicate demo2.preprocess_image, but the model forward is OV.infer.

    Returns dets: ndarray (N, 15) = [x1,y1,x2,y2,score, 10 landmark coords].
    """
    device = torch.device("cpu")
    # The RetinaFace OV IR is exported with a FIXED input shape (1,3,640,640),
    # so we must resize the frame to 640x640 before inference. Decode results
    # come back normalized, so the scale tensors below use the ORIGINAL image
    # size to map boxes/landmarks straight back into original pixel coords.
    orig_h, orig_w = frame_bgr.shape[:2]
    # Network input is always 640x640 (the fixed IR input size).
    im_height, im_width = 640, 640
    img = cv2.resize(np.float32(frame_bgr), (im_width, im_height),
                     interpolation=cv2.INTER_LINEAR)
    # boxes/landms decode to normalized coords; multiply by original image size
    # so the returned dets land in original pixel coordinates (x/y scaled
    # independently, which exactly undoes the 640x640 resize distortion).
    scale = torch.Tensor([orig_w, orig_h, orig_w, orig_h])
    img -= _RETINA_MEAN
    img = img.transpose(2, 0, 1)
    img_t = torch.from_numpy(img).unsqueeze(0)  # (1,3,640,640)

    # --- SEAM: was `loc, conf, landms = retinaface_model(img_t)` ---
    # OV export output_names = ["bbox", "cls", "ldm"] -> infer() returns that
    # port order. Convert numpy -> torch so the rest of decode is bit-identical
    # to the original torch path.
    ov_out = retina_runner.infer(img_t.numpy())  # list[np.ndarray], len 3
    loc = torch.from_numpy(np.asarray(ov_out[0]))     # bbox
    conf = torch.from_numpy(np.asarray(ov_out[1]))    # cls
    landms = torch.from_numpy(np.asarray(ov_out[2]))  # ldm

    # PriorBox uses the network input size (640x640), not the original frame.
    priorbox = PriorBox(cfg_mnet, image_size=(im_height, im_width))
    priors = priorbox.forward().to(device)
    prior_data = priors.data
    boxes = decode(loc.data.squeeze(0), prior_data, cfg_mnet["variance"])
    boxes = boxes * scale / resize
    boxes = boxes.cpu().numpy()
    scores = conf.squeeze(0).data.cpu().numpy()[:, 1]
    landms = decode_landm(landms.data.squeeze(0), prior_data, cfg_mnet["variance"])
    # landms decode to normalized coords -> multiply by ORIGINAL image size.
    scale1 = torch.Tensor([orig_w, orig_h, orig_w, orig_h,
                           orig_w, orig_h, orig_w, orig_h,
                           orig_w, orig_h])
    landms = landms * scale1 / resize
    landms = landms.cpu().numpy()

    inds = np.where(scores > confidence_threshold)[0]
    boxes = boxes[inds]
    landms = landms[inds]
    scores = scores[inds]

    order = scores.argsort()[::-1]
    boxes = boxes[order]
    landms = landms[order]
    scores = scores[order]

    dets = np.hstack((boxes, scores[:, np.newaxis])).astype(np.float32, copy=False)
    keep = py_cpu_nms(dets, nms_threshold)
    dets = dets[keep, :]
    landms = landms[keep]
    dets = np.concatenate((dets, landms), axis=1)
    return dets


def _select_largest_face(dets, conf_threshold):
    """Mirror realtime_demo.select_largest_face."""
    if dets is None or len(dets) == 0:
        return None
    best_det = None
    best_area = -1
    for det in dets:
        conf = float(det[4])
        if conf < conf_threshold:
            continue
        x1, y1, x2, y2 = det[:4]
        area = max(0.0, float(x2 - x1)) * max(0.0, float(y2 - y1))
        if area > best_area:
            best_area = area
            best_det = det
    return best_det


def _scale_bbox(x1, y1, x2, y2, scale_factor=0.1):
    """Mirror demo2.scale_bbox."""
    width = x2 - x1
    height = y2 - y1
    dx = int(width * scale_factor)
    dy = int(height * scale_factor)
    x1_new = max(x1 - dx, 0)
    y1_new = max(y1 - dy, 0)
    x2_new = x2 + dx
    y2_new = y2 + dy
    return x1_new, y1_new, x2_new, y2_new


# =============================================================================
# Seam 2: STAR landmarks (replaces STAR Alignment.analyze forward at line 171)
# =============================================================================
class _StarDecoder:
    """Replicates STAR.demo.Alignment's preprocess/denorm/postprocess, but the
    forward is OV.infer. Standalone so we never construct the torch net."""

    def __init__(self, star_runner):
        self.input_size = _STAR_INPUT_SIZE
        self.target_face_scale = _STAR_TARGET_FACE_SCALE
        self.runner = star_runner
        # Alignment uses align_corners=True for the crop matrix (STAR/demo.py 124-125).
        self.getCropMatrix = GetCropMatrix(
            image_size=self.input_size,
            target_face_scale=self.target_face_scale,
            align_corners=True,
        )
        self.transformPerspective = TransformPerspective(image_size=self.input_size)

    def _denorm_points(self, points, align_corners=False):
        # IMPORTANT: STAR Alignment.analyze calls self.denorm_points(landmarks)
        # with the DEFAULT align_corners=False (STAR/demo.py line 176), even
        # though the crop matrix uses align_corners=True. We replicate that
        # exact (quirky) original behavior so landmarks are bit-identical.
        if align_corners:
            return (points + 1) / 2 * torch.tensor(
                [self.input_size - 1, self.input_size - 1]).to(points).view(1, 1, 2)
        return ((points + 1) * torch.tensor(
            [self.input_size, self.input_size]).to(points).view(1, 1, 2) - 1) / 2

    @staticmethod
    def _invert_affine(matrix):
        """Inverse of a 3x3 affine crop matrix, returned as a 2x3 [[a,b,c],[d,e,f]].

        Equivalent to ``np.linalg.inv(matrix)[:2]`` for an affine matrix, but uses
        OpenCV's closed-form affine inverse instead of LAPACK. This deliberately
        avoids ``numpy.linalg`` because the in-process integration env can ship a
        numpy/OpenBLAS build whose LAPACK ordinals fault at runtime (a native
        STATUS_ORDINAL_NOT_FOUND crash). A 3x3 affine inverse never needs LAPACK;
        cv2.invertAffineTransform is exact to floating-point and keeps the result
        numerically identical to the original np.linalg.inv path.
        """
        return cv2.invertAffineTransform(np.asarray(matrix, dtype=np.float64)[:2])

    @staticmethod
    def _postprocess(srcPoints, coeff):
        dstPoints = np.zeros(srcPoints.shape, dtype=np.float32)
        for i in range(srcPoints.shape[0]):
            dstPoints[i][0] = coeff[0][0] * srcPoints[i][0] + coeff[0][1] * srcPoints[i][1] + coeff[0][2]
            dstPoints[i][1] = coeff[1][0] * srcPoints[i][0] + coeff[1][1] * srcPoints[i][1] + coeff[1][2]
        return dstPoints

    def analyze(self, image, scale, center_w, center_h):
        """image: cropped-face BGR ndarray (HWC). Returns (98,2) landmarks in
        the cropped-face coordinate system (matches demo2.landmark_detection)."""
        # --- preprocess (STAR Alignment.preprocess lines 145-154) ---
        matrix = self.getCropMatrix.process(scale, center_w, center_h)
        input_tensor = self.transformPerspective.process(image, matrix)
        input_tensor = input_tensor[np.newaxis, :]
        input_tensor = torch.from_numpy(input_tensor).float().permute(0, 3, 1, 2)
        input_tensor = input_tensor / 255.0 * 2.0 - 1.0  # (1,3,256,256) in [-1,1]

        # --- SEAM: was `output = self.alignment(input_tensor); landmarks = output[-1][0]` ---
        # OV export output_names = ["fusion_heatmap_last", "landmarks"] via
        # _StarCleanWrapper -> landmarks is the 2nd output (index 1).
        ov_out = self.runner.infer(input_tensor.numpy())  # list[np.ndarray], len 2
        landmarks_np = np.asarray(ov_out[1])  # (1, 98, 2)
        landmarks = torch.from_numpy(landmarks_np)[0]  # (98,2) == output[-1][0]

        # --- denorm + postprocess (STAR analyze lines 176-178) ---
        landmarks = self._denorm_points(landmarks)
        landmarks = landmarks.data.cpu().numpy()[0]  # remove leading dim -> (98,2)
        landmarks = self._postprocess(landmarks, self._invert_affine(matrix))
        return landmarks


def _landmark_detection(face_bgr, star_decoder):
    """Mirror demo2.landmark_detection scale/center math, OV forward inside."""
    face_np = np.array(face_bgr)
    face_height, face_width = face_np.shape[:2]
    center_w = face_width / 2
    center_h = face_height / 2
    scale = min(face_width, face_height) / 200 * 1.05
    landmarks = star_decoder.analyze(face_np, float(scale), float(center_w), float(center_h))
    return landmarks


# =============================================================================
# Seam 3: MTL emotion/gaze/au (replaces demo2 forward at line 332)
# =============================================================================
def _run_mtl(face_bgr, mtl_runner):
    """face_bgr -> RGB -> PIL -> transform -> OV.infer. Returns (emotion_label,
    emotion_confidence, au_list)."""
    face_rgb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
    face_pil = Image.fromarray(face_rgb)
    gaze_image = _MTL_TRANSFORM(face_pil).unsqueeze(0)  # (1,3,224,224)

    # --- SEAM: was `emotion_output, gaze_output, au_output = model(gaze_image)` ---
    # OV export output_names = ["emotion", "gaze", "au"].
    ov_out = mtl_runner.infer(gaze_image.numpy())  # list[np.ndarray], len 3
    emotion_output = torch.from_numpy(np.asarray(ov_out[0]))  # (1, 8) logits
    au_output = torch.from_numpy(np.asarray(ov_out[2]))       # (1, 8)

    probs = torch.softmax(emotion_output[0], dim=0)
    emotion_index = int(torch.argmax(probs).item())
    emotion_label = EXPRESSION_LABELS[emotion_index]
    emotion_confidence = float(probs[emotion_index].item())
    au_list = [float(v) for v in au_output[0].cpu().numpy().tolist()]
    return emotion_label, emotion_confidence, au_list


# =============================================================================
# Factory
# =============================================================================
def build_ov_perceive(models_dir="models_ov", device="CPU",
                      conf_threshold=0.7, min_face_size=96):
    """Construct the 3 OV runners and return a ``perceive(frame_bgr) -> dict``.

    models_dir : directory holding {retinaface,star,mtl}/<name>.xml. If a
                 relative path, it is resolved against the repo root.
    device     : OpenVINO device string ("CPU", "GPU", "NPU", ...).
    """
    if not os.path.isabs(models_dir):
        models_dir = os.path.join(REPO_ROOT, models_dir)

    retina_xml = os.path.join(models_dir, "retinaface", "retinaface.xml")
    star_xml = os.path.join(models_dir, "star", "star.xml")
    mtl_xml = os.path.join(models_dir, "mtl", "mtl.xml")

    retina_runner = OVModelRunner(retina_xml, device=device)
    star_runner = OVModelRunner(star_xml, device=device)
    mtl_runner = OVModelRunner(mtl_xml, device=device)

    star_decoder = _StarDecoder(star_runner)

    def perceive(frame_bgr):
        # 1. detect + pick largest face
        dets = _detect_faces(frame_bgr, retina_runner)
        det = _select_largest_face(dets, conf_threshold)
        if det is None:
            return _empty_result()

        # 2. scale_bbox 0.15 + clamp to frame (mirror annotate_largest_face)
        x1, y1, x2, y2 = det[:4].astype(int)
        x1, y1, x2, y2 = _scale_bbox(x1, y1, x2, y2, 0.15)
        height, width = frame_bgr.shape[:2]
        x1, y1 = max(x1, 0), max(y1, 0)
        x2, y2 = min(x2, width), min(y2, height)
        if min(x2 - x1, y2 - y1) < min_face_size:
            return _empty_result()

        face = frame_bgr[y1:y2, x1:x2]
        if face.size == 0:
            return _empty_result()

        face_confidence = float(det[4])

        # 3. STAR landmarks (cropped-face coords, (98,2))
        landmarks = _landmark_detection(face, star_decoder)

        # 4. MTL emotion / au
        emotion_label, emotion_confidence, au_list = _run_mtl(face, mtl_runner)

        return {
            "landmarks": np.asarray(landmarks, dtype=np.float32),
            "face_confidence": face_confidence,
            "emotion_label": emotion_label,
            "emotion_confidence": emotion_confidence,
            "au": au_list,
        }

    return perceive


if __name__ == "__main__":
    # Tiny smoke check: build perceive and run on images/0.jpg if present.
    test_img = os.path.join(REPO_ROOT, "images", "0.jpg")
    perceive = build_ov_perceive()
    if os.path.exists(test_img):
        frame = cv2.imread(test_img)
        result = perceive(frame)
        print("perceive(images/0.jpg) ->")
        for k, v in result.items():
            if k == "landmarks" and v is not None:
                print(f"  {k}: ndarray {v.shape}")
            else:
                print(f"  {k}: {v}")
    else:
        print(f"No test image at {test_img}; perceive built OK.")
