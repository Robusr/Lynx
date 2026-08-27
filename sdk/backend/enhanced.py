"""Enhanced (AI large-model) backend — open-vocab + ROI re-inference.

Two-pass design:
  1. big model (YOLO11x) over the full frame,
  2. crop the distant/horizon band (top `roi_top_ratio`), upscale `roi_scale`x,
     re-infer with a smaller model to recover small/distant targets,
  3. merge with IoU dedup.

The ROI re-inference is deliberately *single-frame, single-scale* — a local
upscale on a fixed band, avoiding the multi-resolution re-project-and-merge
claim space of Tesla US11893774B2 (see 03-patent-fto.md).
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np

from sdk.backend._yolo import load_yolo, predict_detections
from sdk.backend.base import IBackend
from sdk.config import RobotConfig
from sdk.geometry import merge_detections
from sdk.hal.base import BackendInfo
from sdk.output.frame import Detection


class EnhancedBackend(IBackend):
    name = "enhanced"

    def __init__(
        self,
        big_weights: str = "yolo11x.pt",
        roi_weights: str = "yolo11s.pt",
        conf: float = 0.25,
        roi_conf: float = 0.25,
        device: Optional[str] = None,
        roi_top_ratio: float = 0.4,
        roi_scale: float = 2.0,
        merge_iou: float = 0.45,
        small_target_enhance: bool = True,
    ):
        self.big_weights = big_weights
        self.roi_weights = roi_weights
        self.conf = conf
        self.roi_conf = roi_conf
        self.device = device
        self.roi_top_ratio = roi_top_ratio
        self.roi_scale = roi_scale
        self.merge_iou = merge_iou
        self.small_target_enhance = small_target_enhance
        self._big = None
        self._roi = None

    def init(self, cfg: RobotConfig) -> None:
        self._big = load_yolo(self.big_weights, self.device)
        self._roi = load_yolo(self.roi_weights, self.device)

    def detect(self, image: np.ndarray) -> List[Detection]:
        primary = predict_detections(self._big, image, self.conf, self.device)
        if not self.small_target_enhance:
            return primary
        extra = self._reinfer_distant(image)
        return merge_detections(primary, extra, iou_thresh=self.merge_iou)

    def _reinfer_distant(self, image: np.ndarray) -> List[Detection]:
        try:
            import cv2
        except ImportError as e:  # pragma: no cover - depends on env
            raise RuntimeError("opencv-python is required by the enhanced backend.") from e

        h, w = image.shape[:2]
        top = max(1, int(h * self.roi_top_ratio))
        roi = image[0:top, :]  # distant band: the top of a forward-facing frame
        up = cv2.resize(
            roi,
            None,
            fx=self.roi_scale,
            fy=self.roi_scale,
            interpolation=cv2.INTER_LINEAR,
        )
        dets = predict_detections(self._roi, up, self.roi_conf, self.device)
        for d in dets:
            if d.bbox_2d is not None:
                d.bbox_2d.x /= self.roi_scale
                d.bbox_2d.y /= self.roi_scale
                d.bbox_2d.w /= self.roi_scale
                d.bbox_2d.h /= self.roi_scale
                d.small_target_score = d.confidence
        return dets

    def info(self) -> BackendInfo:
        return BackendInfo(
            name=self.name,
            model=f"{self.big_weights}+{self.roi_weights} (ROI)",
            device=self.device or "cpu",
            extra={"small_target_enhance": self.small_target_enhance},
        )

    def release(self) -> None:
        self._big = None
        self._roi = None
