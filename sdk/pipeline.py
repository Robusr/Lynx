"""The walking skeleton: config → validate → backend → reader → tracker → emit.

`run()` is the product's vertical slice — every layer of the SDK is exercised in
order, and the same `run()` drives the FastAPI demo and the CI smoke test.
"""
from __future__ import annotations

import time
from typing import Callable, List, Optional

import numpy as np

from sdk.backend import EnhancedBackend, IBackend, OfflineBackend, OnnxBackend
from sdk.camera import Pinhole
from sdk.config import RobotConfig, load_config
from sdk.fusion.fuse import fuse_camera_lidar
from sdk.fusion.lidar import synthetic_lidar
from sdk.fusion.tracker import SimpleTracker
from sdk.input.replay_reader import ReplayReader
from sdk.metrics import Metrics
from sdk.output.frame import PerceptionFrame, TrafficSign, Track
from sdk.validate import summarize, validate

# COCO classes routed to the traffic-sign channel rather than the obstacle channel.
SIGN_NAMES = {"stop sign", "traffic light"}

# Callback signature: (PerceptionFrame, source_image_or_None).
OnFrame = Callable[[PerceptionFrame, Optional[np.ndarray]], None]


def build_backend(cfg: RobotConfig) -> IBackend:
    device = _inference_device(cfg)
    conf = cfg.perception.conf
    backend = cfg.perception.backend
    if backend == "enhanced":
        return EnhancedBackend(
            conf=conf,
            device=device,
            small_target_enhance=cfg.perception.small_target_enhance,
        )
    if backend == "onnx":
        return OnnxBackend(conf=conf)
    return OfflineBackend(conf=conf, device=device)


def _inference_device(cfg: RobotConfig) -> str:
    return {
        "onnx_cpu": "cpu",
        "onnx_cuda": "cuda",
        "tensorrt": "cuda",
        "onnx_acl": "cpu",
    }.get(cfg.domain_controller.inference_backend, "cpu")


def _has_lidar(cfg: RobotConfig) -> bool:
    return any(s.type == "lidar" for s in cfg.sensors)


def run(
    cfg: RobotConfig,
    on_frame: OnFrame,
    stop=None,
    max_frames: Optional[int] = None,
    metrics: Optional[Metrics] = None,
) -> None:
    """Run the perception loop until the stream ends, `stop` is set, or `max_frames` reached.

    `max_frames` bounds the loop for smoke tests / CI (a real deploy leaves it None).
    `metrics`, if given, records every emitted frame for telemetry.
    """
    checks = validate(cfg)
    print(summarize(checks))
    if any(c.severity == "error" for c in checks):
        print("preflight FAILED — aborting startup.")
        return

    backend = build_backend(cfg)
    backend.init(cfg)

    reader = ReplayReader(cfg.data.frames_dir, cfg.data.index_path, loop=True)
    tracker = SimpleTracker()
    rate = cfg.output.rate_hz
    period = 1.0 / rate if rate > 0 else 0.0

    n = 0
    try:
        for batch in reader:
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
            if _has_lidar(cfg):
                cam = Pinhole.for_size(image.shape[1], image.shape[0])
                lidar = synthetic_lidar(objects, cam)
                objects = fuse_camera_lidar(objects, lidar, cam)
            tracks: List[Track] = tracker.update(objects, dt=period or 0.1)

            frame = PerceptionFrame(
                stamp_ns=batch.stamp_ns,
                frame_id=cfg.output.frame_id,
                seq=n,
                backend=backend.name,
                objects=tracks,
                traffic_signs=signs,
                latency_ms=latency_ms,
            )
            on_frame(frame, image)
            if metrics is not None:
                metrics.record(frame)

            if period > 0:
                time.sleep(period)
    finally:
        backend.release()
