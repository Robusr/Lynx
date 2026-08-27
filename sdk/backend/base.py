"""Backend abstraction: one interface, two implementations.

`IBackend` is the plugin seam the whole product is built around — offline and
enhanced are interchangeable behind it, and third-party/hardware-specific
backends drop in without touching the pipeline. See 02-technical-architecture.md.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

import numpy as np

from sdk.config import RobotConfig
from sdk.hal.base import BackendInfo
from sdk.output.frame import Detection


class IBackend(ABC):
    """A perception backend maps a camera frame to a list of detections.

    Doc-alignment notes (02-technical-architecture.md §3.2):
      * the doc's `detect(const FrameBatch&)` is `detect(image: np.ndarray)` here —
        the demo pipeline reduces a FrameBatch to its camera frame before detection;
        a multi-sensor backend (lidar/radar/imu in FrameBatch) is a later milestone.
      * the doc's `init(const ModelConfig&)` is `init(cfg: RobotConfig)` here — the
        validated RobotConfig is the demo's convenient superset; sdk.hal.ModelConfig
        is the per-model deploy spec threaded when real deployments land.
      * the doc's `track()` lives in sdk.fusion.tracker.SimpleTracker (sensor-agnostic,
        outside the backend) — see the Decision A/B reconciliation.
    """

    name: str = "base"

    @abstractmethod
    def init(self, cfg: RobotConfig) -> None:
        """Load models / allocate resources, guided by the validated config."""

    @abstractmethod
    def detect(self, image: np.ndarray) -> List[Detection]:
        """Run inference on a BGR (H, W, 3) uint8 image."""

    @abstractmethod
    def info(self) -> BackendInfo:
        """Backend name, model, device, and telemetry (@ai-telemetry)."""

    @abstractmethod
    def release(self) -> None:
        """Free model memory / close sessions."""


# The doc names this seam IInferenceBackend; IBackend is the Python demo's name.
IInferenceBackend = IBackend
