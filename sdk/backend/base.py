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
from sdk.output.frame import Detection


class IBackend(ABC):
    """A perception backend maps a camera frame to a list of detections."""

    name: str = "base"

    @abstractmethod
    def init(self, cfg: RobotConfig) -> None:
        """Load models / allocate resources, guided by the validated config."""

    @abstractmethod
    def detect(self, image: np.ndarray) -> List[Detection]:
        """Run inference on a BGR (H, W, 3) uint8 image."""

    @abstractmethod
    def release(self) -> None:
        """Free model memory / close sessions."""
