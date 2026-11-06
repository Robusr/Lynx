"""Tracker tests: id persistence, class gating, 2D/3D velocity."""
from sdk.fusion.tracker import SimpleTracker
from sdk.output.frame import BBox2D, BBox3D, Detection


def _det(cls_name: str, x: float, y: float = 0.0, z: float = 1.0) -> Detection:
    return Detection(
        cls_id=2,
        cls_name=cls_name,
        bbox_2d=BBox2D(x=x, y=y, w=10, h=10),
        bbox_3d=BBox3D(x=x, y=y, z=z, l=4.5, w=1.8, h=1.5, yaw=0.0),
        confidence=0.9,
    )


def test_keeps_id_and_estimates_2d_and_3d_velocity():
    tracker = SimpleTracker()
    first = tracker.update([_det("car", 0)], dt=1.0)
    second = tracker.update([_det("car", 2)], dt=1.0)
    track = next(t for t in second if t.track_id == first[0].track_id)
    assert track.velocity_px[0] == 2.0
    assert track.velocity[0] == 2.0


def test_does_not_associate_across_classes():
    tracker = SimpleTracker()
    first = tracker.update([_det("car", 0)], dt=1.0)
    second = tracker.update([_det("person", 0)], dt=1.0)
    person = next(t for t in second if t.cls_name == "person")
    assert person.track_id != first[0].track_id


def test_matches_3d_only_detections_by_distance():
    tracker = SimpleTracker()
    a = Detection(
        cls_id=-1,
        cls_name="obstacle",
        bbox_3d=BBox3D(x=10, y=0, z=1, l=1, w=1, h=1, yaw=0),
        confidence=0.9,
    )
    b = Detection(
        cls_id=-1,
        cls_name="obstacle",
        bbox_3d=BBox3D(x=11.5, y=0, z=1, l=1, w=1, h=1, yaw=0),
        confidence=0.9,
    )
    first = tracker.update([a], dt=1.0)
    second = tracker.update([b], dt=1.0)
    assert first[0].track_id == second[0].track_id
    assert second[0].velocity[0] == 1.5
