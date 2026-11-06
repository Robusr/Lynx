"""Vertical-slice tests for pipeline.run with fake sensor and backend adapters."""
import numpy as np
import pytest

from sdk import pipeline
from sdk.backend.base import IBackend
from sdk.config import (
    MountConfig,
    OutputConfig,
    PerceptionConfig,
    RobotConfig,
    ROIConfig,
    SafetyConfig,
    SensorConfig,
    VehicleConfig,
)
from sdk.hal.base import BackendInfo, HealthReport
from sdk.input.replay_reader import FrameBatch
from sdk.metrics import Metrics
from sdk.output.frame import BBox2D, Detection


def _cfg() -> RobotConfig:
    return RobotConfig(
        vehicle=VehicleConfig(name="demo"),
        sensors=[
            SensorConfig(
                name="cam",
                type="camera",
                interface="usb",
                mount=MountConfig(),
            )
        ],
        perception=PerceptionConfig(
            backend="offline",
            modules=["detection", "tracking", "traffic_sign"],
            roi=ROIConfig(forward_m=10, lateral_m=5),
        ),
        output=OutputConfig(rate_hz=1000),
        safety=SafetyConfig(redundant_fov_required=False, max_detection_latency_ms=1000),
    )


class FakeBackend(IBackend):
    name = "fake"

    def __init__(self):
        self.detect_calls = 0
        self.released = False

    def init(self, cfg):
        pass

    def detect(self, image):
        self.detect_calls += 1
        return [
            Detection(
                cls_id=2,
                cls_name="car",
                bbox_2d=BBox2D(x=1, y=1, w=5, h=5),
                confidence=0.9,
            )
        ]

    def info(self):
        return BackendInfo(name=self.name, model="fake", device="cpu")

    def release(self):
        self.released = True


class FakeAdapter:
    name = "fake-sensor"

    def __init__(self, frames: int = 5):
        self.frames = frames
        self.stopped = False
        self._i = 0

    def init(self, cfg, calib=None):
        pass

    def start(self):
        pass

    def stop(self):
        self.stopped = True

    def health(self):
        return HealthReport(status="ok", message="fake")

    def grab(self, timeout_ms: int = 0):
        if self._i >= self.frames:
            return None
        i = self._i
        self._i += 1
        return FrameBatch(stamp_ns=i, camera=np.zeros((8, 8, 3), dtype=np.uint8))


def _patch(monkeypatch, backend=None, adapter=None):
    backend = backend or FakeBackend()
    adapter = adapter or FakeAdapter()
    monkeypatch.setattr(pipeline, "build_backend", lambda cfg: backend)
    monkeypatch.setattr(pipeline, "build_sensor_adapter", lambda cfg: adapter)
    return backend, adapter


def test_run_vertical_slice(monkeypatch):
    backend, adapter = _patch(monkeypatch)
    frames = []
    metrics = Metrics()
    pipeline.run(
        _cfg(),
        lambda frame, image: frames.append(frame),
        max_frames=2,
        metrics=metrics,
    )
    assert len(frames) == 2
    assert [f.seq for f in frames] == [1, 2]
    assert frames[0].backend == "fake"
    assert frames[0].objects[0].track_id == 0
    assert backend.released and adapter.stopped
    assert metrics.snapshot()["frames"] == 2


def test_logs_go_to_stderr(monkeypatch, capsys):
    _patch(monkeypatch)
    pipeline.run(_cfg(), lambda frame, image: None, max_frames=1)
    captured = capsys.readouterr()
    assert "preflight" in captured.err
    assert captured.out == ""


def test_preflight_error_blocks_before_backend(monkeypatch):
    called = []
    monkeypatch.setattr(pipeline, "build_backend", lambda cfg: called.append(True))
    cfg = _cfg()
    cfg.sensors[0].mount = None
    with pytest.raises(pipeline.PreflightError):
        pipeline.run(cfg, lambda frame, image: None)
    assert not called


def test_warnings_require_opt_in(monkeypatch):
    _patch(monkeypatch)
    cfg = _cfg()
    cfg.safety.redundant_fov_required = True
    with pytest.raises(pipeline.PreflightError):
        pipeline.run(cfg, lambda frame, image: None, max_frames=1)
    pipeline.run(
        cfg,
        lambda frame, image: None,
        max_frames=1,
        accept_warnings=True,
    )


def test_latency_violation_marks_frame_and_metrics(monkeypatch):
    _patch(monkeypatch)
    cfg = _cfg()
    cfg.safety.max_detection_latency_ms = 1e-9
    frames = []
    metrics = Metrics()
    pipeline.run(
        cfg,
        lambda frame, image: frames.append(frame),
        max_frames=1,
        metrics=metrics,
    )
    assert "detection_latency_exceeded" in frames[0].warnings
    assert metrics.snapshot()["latency_violations"] == 1


def test_tracking_module_disabled(monkeypatch):
    _patch(monkeypatch)
    cfg = _cfg()
    cfg.perception.modules = ["detection"]
    frames = []
    pipeline.run(cfg, lambda frame, image: frames.append(frame), max_frames=1)
    assert frames[0].objects[0].track_id == -1


def test_prebuilt_backend_is_used_and_released(monkeypatch):
    backend = FakeBackend()
    _, _ = _patch(monkeypatch)
    pipeline.run(
        _cfg(),
        lambda frame, image: None,
        max_frames=1,
        backend=backend,
    )
    assert backend.detect_calls == 1
    assert backend.released
