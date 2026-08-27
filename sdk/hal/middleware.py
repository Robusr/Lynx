"""Middleware adapter seam — publish the standard data model to any transport.

IMiddlewareAdapter shields ROS2 / DDS / SOME-IP / private-bus differences; the
pipeline only calls publish(PerceptionFrame). JsonLineMiddlewareAdapter is the
demo implementation: one JSON object per line on a stream (stdout by default).
"""
from __future__ import annotations

import json
import sys
from abc import ABC, abstractmethod
from typing import Callable, Optional, TextIO

from sdk.hal.base import MiddlewareConfig
from sdk.output.frame import PerceptionFrame


class IMiddlewareAdapter(ABC):
    """Publish/subscribe transport plugin (mirrors the doc's IMiddlewareAdapter)."""

    name: str = "middleware"

    @abstractmethod
    def init(self, cfg: MiddlewareConfig) -> None:
        """Configure the transport (topics, QoS, serialization)."""

    @abstractmethod
    def publish(self, frame: PerceptionFrame) -> bool:
        """Serialize + publish one frame; return True on success."""

    @abstractmethod
    def subscribe(self, topic: str, cb: Callable[[dict], None]) -> None:
        """Subscribe to a topic (e.g. localization/vehicle state)."""

    @abstractmethod
    def stop(self) -> None:
        """Tear down the transport (Python counterpart of C++ RAII)."""


class JsonLineMiddlewareAdapter(IMiddlewareAdapter):
    """NDJSON publish adapter — one PerceptionFrame per line, for CLI/pipe consumers."""

    name = "jsonline"

    def __init__(self, stream: Optional[TextIO] = None):
        self._stream = stream
        self._cfg = MiddlewareConfig()

    def init(self, cfg: MiddlewareConfig) -> None:
        self._cfg = cfg

    def publish(self, frame: PerceptionFrame) -> bool:
        out = self._stream or sys.stdout
        out.write(json.dumps(frame.model_dump(), ensure_ascii=False, default=str) + "\n")
        out.flush()
        return True

    def subscribe(self, topic: str, cb: Callable[[dict], None]) -> None:
        # Localization/vehicle-state ingest is out of demo scope; a real adapter
        # registers a transport callback here.
        raise NotImplementedError("subscribe() needs a live transport; the demo only publishes.")

    def stop(self) -> None:
        pass
