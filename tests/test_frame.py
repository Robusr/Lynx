"""Contract tests for the standardized output schema (the product's data model)."""
from sdk.output.frame import BBox2D, Detection, PerceptionFrame, Track


def test_detection_defaults():
    d = Detection(cls_id=0, cls_name="person", confidence=0.9)
    assert d.bbox_2d is None
    assert d.bbox_3d is None
    assert d.source == "camera"
    assert d.occlusion_ratio == 0.0
    assert d.small_target_score == 0.0


def test_track_inherits_detection_and_adds_id():
    t = Track(cls_id=0, cls_name="person", confidence=0.8, track_id=3)
    assert t.track_id == 3
    assert t.velocity == (0.0, 0.0, 0.0)


def test_bbox_roundtrip():
    b = BBox2D(x=1.0, y=2.0, w=10.0, h=20.0)
    assert b.x + b.w == 11.0
    assert b.y + b.h == 22.0


def test_frame_defaults_serialize():
    f = PerceptionFrame(stamp_ns=123, frame_id="base_link")
    d = f.model_dump()
    assert d["objects"] == []
    assert d["traffic_signs"] == []
    assert d["backend"] == "offline"
    assert d["latency_ms"] == 0.0
