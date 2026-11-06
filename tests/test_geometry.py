"""Geometry tests: IoU, class-aware NMS, and class-aware merge."""
from sdk.geometry import iou, merge_detections, nms
from sdk.output.frame import BBox2D, Detection


def _det(cls_name: str, x: float, confidence: float) -> Detection:
    return Detection(
        cls_id=2,
        cls_name=cls_name,
        bbox_2d=BBox2D(x=x, y=0, w=10, h=10),
        confidence=confidence,
    )


def test_iou_partial_overlap():
    a = BBox2D(x=0, y=0, w=10, h=10)
    b = BBox2D(x=5, y=0, w=10, h=10)
    assert abs(iou(a, b) - 50 / 150) < 1e-9


def test_nms_suppresses_same_class_overlap():
    kept = nms([_det("car", 0, 0.9), _det("car", 1, 0.8)], iou_thresh=0.45)
    assert len(kept) == 1
    assert kept[0].confidence == 0.9


def test_nms_keeps_different_classes():
    kept = nms([_det("car", 0, 0.9), _det("person", 0, 0.8)], iou_thresh=0.45)
    assert len(kept) == 2


def test_merge_deduplicates_same_class_only():
    primary = [_det("car", 0, 0.9)]
    merged = merge_detections(primary, [_det("car", 0, 0.7), _det("person", 0, 0.6)])
    assert len(merged) == 2
    assert {d.cls_name for d in merged} == {"car", "person"}
