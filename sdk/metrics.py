"""In-process runtime metrics for the perception loop.

Dependency-light (stdlib only) so it stays in the SDK core and can be exposed by
any host — the demo server, a future agent, or a CLI. Tracks latency
percentiles, throughput, and per-source object counts. It is *not* a Prometheus
client; a production build pushes this snapshot into a real telemetry stack.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Deque, Dict

from sdk.output.frame import PerceptionFrame


class Metrics:
    """Accumulates per-frame telemetry and renders a JSON-ready snapshot."""

    _MAX_LATENCY_SAMPLES = 1000

    def __init__(self) -> None:
        self._frames = 0
        self._start = time.perf_counter()
        self._backend = ""
        self._latencies: Deque[float] = deque(maxlen=self._MAX_LATENCY_SAMPLES)
        self._last_objects = 0
        self._last_sources: Dict[str, int] = {}
        self._last_signs = 0

    def record(self, frame: PerceptionFrame) -> None:
        self._frames += 1
        self._backend = frame.backend
        self._latencies.append(frame.latency_ms)
        self._last_objects = len(frame.objects)
        self._last_signs = len(frame.traffic_signs)
        sources: Dict[str, int] = {}
        for o in frame.objects:
            sources[o.source] = sources.get(o.source, 0) + 1
        self._last_sources = sources

    @staticmethod
    def _percentile(values: list, q: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        idx = min(len(ordered) - 1, int(len(ordered) * q))
        return ordered[idx]

    def snapshot(self) -> dict:
        up = time.perf_counter() - self._start
        n = self._frames
        lat = list(self._latencies)
        return {
            "frames": n,
            "uptime_s": round(up, 3),
            "fps": round(n / up, 3) if up > 0 else 0.0,
            "backend": self._backend,
            "latency_ms": {
                "last": round(lat[-1], 3) if lat else 0.0,
                "avg": round(sum(lat) / len(lat), 3) if lat else 0.0,
                "p95": round(self._percentile(lat, 0.95), 3),
                "max": round(max(lat), 3) if lat else 0.0,
            },
            "objects": {
                "last": self._last_objects,
                "sources": self._last_sources,
            },
            "traffic_signs_last": self._last_signs,
        }
