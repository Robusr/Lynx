"""ONNX Runtime backend — the hardware-agnostic inference path.

Runs a YOLO11 ONNX graph through ONNX Runtime with pluggable execution
providers (CPU / CoreML / CUDA / TensorRT / ARM ACL). Pre/post-processing
(letterbox + decode + NMS) is our own code; only the heavy model graph is
delegated to the EP, so the same `.onnx` artifact targets different hardware
without changing the SDK code path.

This is the seam that makes "one SDK, hardware-agnostic" a code fact rather
than a config comment. Export the graph first with:

    python scripts/export_models.py yolo11s.pt
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, List, Optional

import numpy as np

from sdk.backend.base import IBackend
from sdk.config import RobotConfig
from sdk.geometry import nms
from sdk.hal.base import BackendInfo
from sdk.output.frame import BBox2D, Detection, SourceMask

# COCO 80-class names, indexed by class id — the same order `model.names`
# reports for a COCO-trained YOLO11.
COCO_NAMES = (
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
    "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
    "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra",
    "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup",
    "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier",
    "toothbrush",
)

# config `domain_controller.inference_backend` → ONNX Runtime execution provider.
EP_CONFIG = {
    "onnx_cpu": "CPUExecutionProvider",
    "onnx_cuda": "CUDAExecutionProvider",
    "tensorrt": "TensorrtExecutionProvider",
    "onnx_acl": "ACLExecutionProvider",
    "onnx_coreml": "CoreMLExecutionProvider",
}


def _short_label(provider: str) -> str:
    return provider.replace("ExecutionProvider", "").lower()


def _letterbox(image: np.ndarray, size: int):
    """Resize + pad to a square, matching ultralytics' preprocessing.

    Returns (NCHW float32 tensor in [0,1], scale, left_pad, top_pad). The pads
    and scale are needed to map detections back to the source image.
    """
    import cv2

    h, w = image.shape[:2]
    r = min(size / h, size / w)
    new_w, new_h = int(round(w * r)), int(round(h * r))
    dw, dh = size - new_w, size - new_h
    left, right = int(round(dw / 2 - 0.1)), int(round(dw / 2 + 0.1))
    top, bottom = int(round(dh / 2 - 0.1)), int(round(dh / 2 + 0.1))

    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    padded = cv2.copyMakeBorder(
        resized, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114)
    )
    rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
    tensor = np.ascontiguousarray(rgb.transpose(2, 0, 1)[None], dtype=np.float32) / 255.0
    return tensor, r, left, top


def _decode(
    out: np.ndarray,
    scale: float,
    left: int,
    top: int,
    conf: float,
    max_det: int = 300,
) -> List[Detection]:
    """Map a YOLO11 logit tensor back to image-space detections.

    Accepts both export layouts, `[1, 4 + classes, N]` and `[1, N, 4 + classes]`,
    filters by confidence, keeps the top `max_det` candidates, and returns boxes
    in source-image coordinates.
    """
    d = np.asarray(out)
    if d.ndim == 3:
        d = d[0]
    if d.ndim != 2:
        raise ValueError(f"unexpected ONNX output shape {np.asarray(out).shape}")
    expected_channels = 4 + len(COCO_NAMES)  # 84 for COCO YOLO11
    if d.shape[0] == expected_channels and d.shape[1] != expected_channels:
        pass  # channels-first: [4 + classes, N]
    elif d.shape[1] == expected_channels:
        d = d.T  # channels-last: [N, 4 + classes]
    elif d.shape[0] > d.shape[1]:
        d = d.T
    if d.shape[0] < 5:
        return []

    boxes = d[:4]
    scores = d[4:]
    confs = scores.max(axis=0)
    cls_ids = scores.argmax(axis=0)

    keep = np.where(confs >= conf)[0]
    if keep.size == 0:
        return []
    keep = keep[np.argsort(-confs[keep])][:max_det]

    bx, by, bw, bh = boxes[0][keep], boxes[1][keep], boxes[2][keep], boxes[3][keep]
    cf, cid = confs[keep], cls_ids[keep]

    x1 = (bx - bw / 2 - left) / scale
    y1 = (by - bh / 2 - top) / scale
    x2 = (bx + bw / 2 - left) / scale
    y2 = (by + bh / 2 - top) / scale

    dets: List[Detection] = []
    for i in range(len(cf)):
        cls = int(cid[i])
        dets.append(
            Detection(
                cls_id=cls,
                cls_name=COCO_NAMES[cls] if cls < len(COCO_NAMES) else str(cls),
                bbox_2d=BBox2D(
                    x=float(x1[i]), y=float(y1[i]),
                    w=float(x2[i] - x1[i]), h=float(y2[i] - y1[i]),
                ),
                confidence=float(cf[i]),
                source=SourceMask.CAMERA,
            )
        )
    return dets


class OnnxBackend(IBackend):
    """Run a YOLO11 ONNX graph on ONNX Runtime with an EP chosen from config."""

    name = "onnx"

    def __init__(
        self,
        weights: str = "yolo11s.onnx",
        conf: float = 0.25,
        providers: Optional[List[str]] = None,
        input_size: int = 640,
    ):
        self.weights = weights
        self.conf = conf
        self.providers = providers  # explicit EP list, or None → derive from config
        self.input_size = input_size
        self.ep = "cpu"
        self.requested_ep = "cpu"
        self.fallback = False
        self._session: Any = None
        self._input_name: str = ""
        self._output_name: str = ""

    def init(self, cfg: RobotConfig) -> None:
        if not Path(self.weights).exists():
            raise RuntimeError(
                f"ONNX weights not found: {self.weights!r}. Run "
                f"`python scripts/export_models.py yolo11s.pt` first."
            )

        if self.providers is None:
            primary = EP_CONFIG.get(cfg.domain_controller.inference_backend, "CPUExecutionProvider")
            requested = [primary, "CPUExecutionProvider"]
        else:
            requested = list(self.providers)
            primary = requested[0]
        requested = list(dict.fromkeys(requested))  # dedupe, keep order
        self.requested_ep = _short_label(primary)

        import onnxruntime as ort

        available = ort.get_available_providers()
        providers = [p for p in requested if p in available]
        if "CPUExecutionProvider" not in providers:
            providers.append("CPUExecutionProvider")
        self.ep = _short_label(providers[0])
        self.fallback = self.ep != self.requested_ep
        if self.fallback:
            print(
                f"onnx: requested {self.requested_ep!r} but using {self.ep!r}; "
                f"available providers: {available}",
                file=sys.stderr,
            )

        session = ort.InferenceSession(self.weights, providers=providers)
        self._session = session
        inp = session.get_inputs()[0]
        self._input_name = inp.name
        if isinstance(inp.shape[2], int):
            self.input_size = inp.shape[2]
        self._output_name = session.get_outputs()[0].name
        self.name = f"onnx:{self.ep}"

    def detect(self, image: np.ndarray) -> List[Detection]:
        session = self._session
        if session is None:
            raise RuntimeError("OnnxBackend.init() must be called before detect()")
        tensor, scale, left, top = _letterbox(image, self.input_size)
        out = session.run([self._output_name], {self._input_name: tensor})[0]
        return nms(_decode(out, scale, left, top, self.conf), iou_thresh=0.45)

    def info(self) -> BackendInfo:
        return BackendInfo(
            name=self.name,
            model=self.weights,
            device=self.ep,
            extra={"requested_ep": self.requested_ep, "fallback": self.fallback},
        )

    def release(self) -> None:
        self._session = None
