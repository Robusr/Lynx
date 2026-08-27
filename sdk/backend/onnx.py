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

from pathlib import Path
from typing import List, Optional

import numpy as np

from sdk.backend.base import IBackend
from sdk.config import RobotConfig
from sdk.geometry import nms
from sdk.output.frame import BBox2D, Detection

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


def _decode(out: np.ndarray, scale: float, left: int, top: int, conf: float) -> List[Detection]:
    """Map a YOLO11 `[1, 84, 8400]` logit tensor back to image-space detections."""
    d = out[0]  # [4 + 80, 8400]
    boxes = d[:4]
    scores = d[4:]
    confs = scores.max(axis=0)
    cls_ids = scores.argmax(axis=0)

    keep = confs >= conf
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
                source="camera",
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
        self._session = None
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
        requested = list(dict.fromkeys(requested))  # dedupe, keep order

        import onnxruntime as ort

        available = ort.get_available_providers()
        providers = [p for p in requested if p in available]
        if "CPUExecutionProvider" not in providers:
            providers.append("CPUExecutionProvider")
        self.ep = _short_label(providers[0])

        self._session = ort.InferenceSession(self.weights, providers=providers)
        inp = self._session.get_inputs()[0]
        self._input_name = inp.name
        if isinstance(inp.shape[2], int):
            self.input_size = inp.shape[2]
        self._output_name = self._session.get_outputs()[0].name
        self.name = f"onnx:{self.ep}"

    def detect(self, image: np.ndarray) -> List[Detection]:
        tensor, scale, left, top = _letterbox(image, self.input_size)
        out = self._session.run([self._output_name], {self._input_name: tensor})[0]
        return nms(_decode(out, scale, left, top, self.conf), iou_thresh=0.45)

    def release(self) -> None:
        self._session = None
