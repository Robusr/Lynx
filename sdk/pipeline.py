"""The walking skeleton: config → validate → backend → reader → tracker → emit.

`run()` is the product's vertical slice — every layer of the SDK is exercised in
order, and the same `run()` drives the FastAPI demo and the CI smoke test.
"""
from __future__ import annotations

import time
from typing import Callable, List, Optional

import numpy as np

from sdk.backend import EnhancedBackend, IBackend, OfflineBackend
from sdk.config import RobotConfig, load_config
from sdk.fusion.tracker import SimpleTracker
from sdk.input.replay_reader import ReplayReader
from sdk.output.frame import PerceptionFrame, TrafficSign, Track
from sdk.validate import summarize, validate

# COCO classes routed to the traffic-sign channel rather than the obstacle channel.
SIGN_NAMES = {"stop sign", "traffic light"}

# Callback signature: (PerceptionFrame, source_image_or_None).
OnFrame = Callable[[PerceptionFrame, Optional[np.ndarray]], None]


def build_backend(cfg: RobotConfig) -> IBackend:
    device = _inference_device(cfg)
    backend = cfg.perception.backend
    if backend == "enhanced":
        return EnhancedBackend(device=device)
    return OfflineBackend(device=device)


def _inference_device(cfg: RobotConfig) -> str:
    return {
        "onnx_cpu": "cpu",
        "onnx_cuda": "cuda",
        "tensorrt": "cuda",
        "onnx_acl": "cpu",
    }.get(cfg.domain_controller.inference_backend, "cpu")


def run(cfg: RobotConfig, on_frame: OnFrame, stop=None) -> None:
    """Run the perception loop until the stream ends or `stop` is set."""
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

    try:
        for batch in reader:
            if stop is not None and stop.is_set():
                break
            image = batch.camera
            if image is None:
                continue

            t0 = time.perf_counter()
            detections = backend.detect(image)
            latency_ms = (time.perf_counter() - t0) * 1000.0

            objects = [d for d in detections if d.cls_name not in SIGN_NAMES]
            signs = [
                TrafficSign(
                    cls_name=d.cls_name,
                    bbox_2d=d.bbox_2d,
                    confidence=d.confidence,
                )
                for d in detections
                if d.cls_name in SIGN_NAMES
            ]
            tracks: List[Track] = tracker.update(objects, dt=period or 0.1)

            frame = PerceptionFrame(
                stamp_ns=batch.stamp_ns,
                frame_id=cfg.output.frame_id,
                backend=backend.name,
                objects=tracks,
                traffic_signs=signs,
                latency_ms=latency_ms,
            )
            on_frame(frame, image)

            if period > 0:
                time.sleep(period)
    finally:
        backend.release()
