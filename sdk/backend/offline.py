"""Offline (lightweight) backend — the embedded/deployed default.

Single small model (YOLO11s) on the whole frame, CPU-friendly, deterministic.
This is the backend the fleet actually runs; it is also the fallback when the
enhanced backend's model can't fit the domain controller.
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np

from sdk.backend._yolo import load_yolo, predict_detections
from sdk.backend.base import IBackend
from sdk.config import RobotConfig
from sdk.hal.base import BackendInfo
from sdk.output.frame import Detection


class OfflineBackend(IBackend):
    name = "offline"

    def __init__(
        self,
        weights: str = "yolo11s.pt",
        conf: float = 0.25,
        device: Optional[str] = None,
    ):
        self.weights = weights
        self.conf = conf
        self.device = device
        self._model = None

    def init(self, cfg: RobotConfig) -> None:
        self._model = load_yolo(self.weights, self.device)

    def detect(self, image: np.ndarray) -> List[Detection]:
        return predict_detections(self._model, image, self.conf, self.device)

    def info(self) -> BackendInfo:
        return BackendInfo(name=self.name, model=self.weights, device=self.device or "cpu")

    def release(self) -> None:
        self._model = None
