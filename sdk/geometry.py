"""Geometry helpers shared by the backend (NMS/merge) and fusion (tracking).

Deliberately dependency-light: only numpy-free, pydantic-light box math, so it
can be unit-tested without pulling in OpenCV / ONNX / ultralytics.
"""
from __future__ import annotations

from typing import List

from sdk.output.frame import BBox2D, Detection


def iou(a: BBox2D, b: BBox2D) -> float:
    """Intersection-over-union for two axis-aligned boxes in pixel coords."""
    ax1, ay1 = a.x, a.y
    ax2, ay2 = a.x + a.w, a.y + a.h
    bx1, by1 = b.x, b.y
    bx2, by2 = b.x + b.w, b.y + b.h

    iw = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    ih = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih

    area_a = max(0.0, a.w) * max(0.0, a.h)
    area_b = max(0.0, b.w) * max(0.0, b.h)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def nms(dets: List[Detection], iou_thresh: float = 0.45) -> List[Detection]:
    """Greedy confidence-sorted NMS. Dets without a 2D box pass through."""
    if not dets:
        return []
    ordered = sorted(dets, key=lambda d: d.confidence, reverse=True)
    kept: List[Detection] = []
    for d in ordered:
        if d.bbox_2d is None:
            kept.append(d)
            continue
        if all(
            iou(d.bbox_2d, k.bbox_2d) < iou_thresh
            for k in kept
            if k.bbox_2d is not None
        ):
            kept.append(d)
    return kept


def merge_detections(
    primary: List[Detection],
    extra: List[Detection],
    iou_thresh: float = 0.45,
) -> List[Detection]:
    """Keep `primary` untouched; append `extra` dets that don't overlap any kept box.

    Used by the enhanced backend: full-frame (primary) + ROI re-inference (extra),
    deduplicated so an upscaled re-detection of an already-found object is dropped.
    """
    accepted = list(primary)
    for d in extra:
        if d.bbox_2d is None:
            accepted.append(d)
            continue
        if all(
            iou(d.bbox_2d, a.bbox_2d) < iou_thresh
            for a in accepted
            if a.bbox_2d is not None
        ):
            accepted.append(d)
    return accepted
