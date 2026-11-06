"""The walking skeleton: config → validate → backend → reader → tracker → emit.

`run()` is the product's vertical slice — every layer of the SDK is exercised in
order, and the same `run()` drives the FastAPI demo and the CI smoke test.

Logging goes to stderr so `JsonLineMiddlewareAdapter` can keep stdout as clean
NDJSON for pipe consumers.
"""
from __future__ import annotations

import sys
import time
from typing import Callable, List, Optional

import numpy as np

from sdk.backend import IBackend, build_backend
from sdk.camera import Pinhole
from sdk.config import RobotConfig
from sdk.fusion.fuse import fuse_camera_lidar
from sdk.fusion.lidar import synthetic_lidar
from sdk.fusion.tracker import SimpleTracker
from sdk.hal.base import MiddlewareConfig
from sdk.hal.middleware import IMiddlewareAdapter, build_middleware
from sdk.hal.sensor import ISensorAdapter
from sdk.hal.sensor import build_sensor_adapter as build_hal_sensor
from sdk.metrics import Metrics
from sdk.output.frame import Detection, PerceptionFrame, Track, TrafficSign
from sdk.validate import summarize, validate

# COCO classes routed to the traffic-sign channel rather than the obstacle channel.
SIGN_NAMES = {"stop sign", "traffic light"}

# Callback signature: (PerceptionFrame, source_image_or_None).
OnFrame = Callable[[PerceptionFrame, Optional[np.ndarray]], None]


class PreflightError(RuntimeError):
    """Preflight blocked startup, or warnings were not explicitly accepted."""


def _log(message: str) -> None:
    print(message, file=sys.stderr)


def build_sensor_adapter(cfg: RobotConfig) -> ISensorAdapter:
    """Return the input adapter for the configured sensor suite.

    The demo has a single replay source (a camera stream); a production build maps
    each sensor entry to its own adapter and merges them into one FrameBatch.
    """
    cameras = [s for s in cfg.sensors if s.type == "camera"]
    if not cameras:
        raise PreflightError(
            "no camera sensor declared; the demo pipeline requires at least one camera"
        )
    data = cfg.data.model_copy(
        update={
            "frames_dir": cfg.resolve(cfg.data.frames_dir) or cfg.data.frames_dir,
            "index_path": cfg.resolve(cfg.data.index_path),
        }
    )
    return build_hal_sensor("replay", data)


def build_middleware_adapter(cfg: RobotConfig) -> IMiddlewareAdapter:
    """Return the publish adapter for cfg.domain_controller.middleware."""
    mw = cfg.domain_controller.middleware
    return build_middleware(mw, MiddlewareConfig(middleware=mw, topic="perception"))


def _has_lidar(cfg: RobotConfig) -> bool:
    return any(s.type == "lidar" for s in cfg.sensors)


def _as_track(det: Detection) -> Track:
    """Wrap a detection as a track when the tracking module is disabled."""
    return Track(**det.model_dump(), track_id=-1)


def run(
    cfg: RobotConfig,
    on_frame: OnFrame,
    stop=None,
    max_frames: Optional[int] = None,
    metrics: Optional[Metrics] = None,
    middleware: Optional[IMiddlewareAdapter] = None,
    backend: Optional[IBackend] = None,
    accept_warnings: bool = False,
) -> None:
    """Run the perception loop until the stream ends, `stop` is set, or `max_frames` reached.

    `max_frames` bounds the loop for smoke tests / CI (a real deploy leaves it None).
    `metrics`, if given, records every emitted frame for telemetry.
    `middleware`, if given, publishes each frame through an IMiddlewareAdapter.
    `backend`, if given, must already be initialized; ownership transfers to `run`.
    `accept_warnings`, when true, lets a manifest with preflight warnings start.
    """
    checks = validate(cfg)
    _log(summarize(checks))
    errors = [c for c in checks if c.severity == "error"]
    warnings = [c for c in checks if c.severity == "warn"]
    if errors:
        detail = "; ".join(f"{c.name}: {c.message}" for c in errors)
        raise PreflightError(f"preflight failed: {detail}")
    if warnings and not accept_warnings:
        detail = "; ".join(f"{c.name}: {c.message}" for c in warnings)
        raise PreflightError(
            "preflight produced warnings; rerun with accept_warnings=True to start: " + detail
        )
    if "detection" not in cfg.perception.modules:
        raise PreflightError("perception.modules must include 'detection'")

    if backend is None:
        backend = build_backend(cfg)
        backend.init(cfg)
    info = backend.info()
    _log(f"backend: {info.name} (model={info.model}, device={info.device})")
    if info.extra.get("fallback"):
        _log(
            f"backend warning: requested {info.extra.get('requested_ep')} "
            f"but using {info.device}"
        )

    modules = set(cfg.perception.modules)
    tracker = SimpleTracker()
    rate = cfg.output.rate_hz
    period = 1.0 / rate if rate > 0 else 0.0
    deadline = time.perf_counter()
    n = 0
    adapter: Optional[ISensorAdapter] = None
    try:
        adapter = build_sensor_adapter(cfg)
        adapter.start()
        health = adapter.health()
        _log(f"sensor: {adapter.name} (status={health.status}, {health.message})")

        while True:
            batch = adapter.grab()
            if batch is None:
                break
            if stop is not None and stop.is_set():
                break
            image = batch.camera
            if image is None:
                continue
            if max_frames is not None and n >= max_frames:
                break
            n += 1

            t0 = time.perf_counter()
            detections = backend.detect(image)
            latency_ms = (time.perf_counter() - t0) * 1000.0

            if "traffic_sign" in modules:
                objects = [d for d in detections if d.cls_name not in SIGN_NAMES]
                signs = [
                    TrafficSign(
                        cls_name=d.cls_name,
                        bbox_2d=d.bbox_2d,
                        confidence=d.confidence,
                        stamp_ns=batch.stamp_ns,
                    )
                    for d in detections
                    if d.cls_name in SIGN_NAMES
                ]
            else:
                objects = list(detections)
                signs = []

            if _has_lidar(cfg):
                cam = Pinhole.for_size(image.shape[1], image.shape[0])
                lidar = synthetic_lidar(objects, cam)
                objects = fuse_camera_lidar(objects, lidar, cam)

            if "tracking" in modules:
                tracks: List[Track] = tracker.update(objects, dt=period or 0.1)
            else:
                tracks = [_as_track(d) for d in objects]

            frame_warnings: List[str] = []
            if latency_ms > cfg.safety.max_detection_latency_ms:
                frame_warnings.append("detection_latency_exceeded")
                if metrics is not None:
                    metrics.record_latency_violation()

            frame = PerceptionFrame(
                stamp_ns=batch.stamp_ns,
                frame_id=cfg.output.frame_id,
                seq=n,
                backend=backend.name,
                objects=tracks,
                traffic_signs=signs,
                latency_ms=latency_ms,
                warnings=frame_warnings,
            )
            on_frame(frame, image)
            if middleware is not None:
                middleware.publish(frame)
            if metrics is not None:
                metrics.record(frame)

            if max_frames is not None and n >= max_frames:
                break

            if period > 0:
                deadline += period
                now = time.perf_counter()
                if now > deadline + period:
                    # More than one period behind: resynchronize and count the miss.
                    if metrics is not None:
                        metrics.record_drop()
                    deadline = now + period
                else:
                    time.sleep(max(0.0, deadline - now))
    finally:
        if adapter is not None:
            adapter.stop()
        backend.release()
