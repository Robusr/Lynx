"""Unit tests for the in-process runtime metrics collector."""

from sdk.metrics import Metrics
from sdk.output.frame import BBox2D, PerceptionFrame, SourceMask, Track


def _frame(objects, latency: float = 10.0, backend: str = "offline") -> PerceptionFrame:
    return PerceptionFrame(
        stamp_ns=0,
        frame_id="base_link",
        backend=backend,
        objects=objects,
        latency_ms=latency,
    )


def _track(track_id: int, source: SourceMask) -> Track:
    return Track(
        track_id=track_id,
        cls_id=-1 if source == SourceMask.LIDAR else 2,
        cls_name="obstacle" if source == SourceMask.LIDAR else "car",
        confidence=0.9,
        source=source,
        bbox_2d=None if source == SourceMask.LIDAR else BBox2D(x=0, y=0, w=10, h=10),
    )


def test_empty_snapshot_is_safe():
    s = Metrics().snapshot()
    assert s["frames"] == 0
    assert s["fps"] == 0.0
    assert s["latency_ms"]["avg"] == 0.0
    assert s["objects"]["sources"] == {}


def test_accumulates_frames_and_latency():
    m = Metrics()
    m.record(_frame([], latency=5.0))
    m.record(_frame([], latency=15.0))
    s = m.snapshot()
    assert s["frames"] == 2
    assert s["backend"] == "offline"
    assert s["latency_ms"]["avg"] == 10.0
    assert s["latency_ms"]["max"] == 15.0
    assert s["latency_ms"]["last"] == 15.0


def test_counts_sources_and_objects():
    m = Metrics()
    m.record(_frame([
        _track(1, SourceMask.CAMERA | SourceMask.LIDAR),
        _track(2, SourceMask.CAMERA),
        _track(3, SourceMask.LIDAR),
    ]))
    s = m.snapshot()
    assert s["objects"]["last"] == 3
    assert s["objects"]["sources"] == {"fusion": 1, "camera": 1, "lidar": 1}
