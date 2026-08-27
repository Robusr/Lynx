"""Sensor adapter seam — the "hardware-agnostic" input layer.

ISensorAdapter is the plugin interface every physical sensor exposes. The core
pipeline only ever sees FrameBatch, so adding a sensor means adding an adapter
with zero change to detection/fusion/tracking. Pull-mode is the SDK default
(doc §3.1) so streams stay deterministic and replayable.

ReplaySensorAdapter is the demo/CI concrete implementation: it wraps the
recorded-frame ReplayReader behind the same interface a live driver would.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator, Optional

from sdk.hal.base import HealthReport
from sdk.input.replay_reader import FrameBatch, ReplayReader


class ISensorAdapter(ABC):
    """Pull-mode sensor driver interface (mirrors the doc's ISensorAdapter)."""

    name: str = "sensor"

    @abstractmethod
    def init(self, cfg, calib=None) -> None:
        """Open the device / validate config. `calib` is a CalibStore (None in the demo).

        Doc §3.1 passes `SensorConfig + CalibStore` per sensor; the demo's single
        replay adapter instead receives `DataConfig` (the whole-stream source) because
        the demo has one adapter for the recorded stream, not one adapter per sensor.
        """

    @abstractmethod
    def start(self) -> None:
        """Begin streaming (no-op for replay)."""

    @abstractmethod
    def stop(self) -> None:
        """Stop streaming / release the device."""

    @abstractmethod
    def grab(self, timeout_ms: int = 0) -> Optional[FrameBatch]:
        """Return the next time-aligned FrameBatch, or None at end-of-stream."""

    @abstractmethod
    def health(self) -> HealthReport:
        """Health snapshot for @ai-telemetry."""


class ReplaySensorAdapter(ISensorAdapter):
    """Plays back recorded frames as a camera stream (the demo's only source)."""

    name = "replay"

    def __init__(self, loop: bool = True):
        self._loop = loop
        self._reader: Optional[ReplayReader] = None

    def init(self, cfg, calib=None) -> None:
        self._reader = ReplayReader(cfg.frames_dir, cfg.index_path, loop=self._loop)

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def grab(self, timeout_ms: int = 0) -> Optional[FrameBatch]:
        if self._reader is None:
            return None
        try:
            batch = next(self._reader)
        except StopIteration:
            return None
        batch.frame_id = batch.frame_id or "camera"  # replay source is a camera stream
        return batch

    def health(self) -> HealthReport:
        frames = len(self._reader) if self._reader is not None else 0
        return HealthReport(
            status="ok", message="replay source", detail={"frames": frames, "loop": self._loop}
        )

    def __iter__(self) -> Iterator[FrameBatch]:
        return self

    def __next__(self) -> FrameBatch:
        batch = self.grab()
        if batch is None:
            raise StopIteration
        return batch
