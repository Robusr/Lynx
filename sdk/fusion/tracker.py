"""SORT-lite tracker: greedy IoU association + velocity estimate.

A minimal multi-object tracker that turns per-frame `Detection`s into persistent
`Track`s with ids and pixel-space velocity. Deliberately free of Kalman/BYTE
complexity so the skeleton stays legible; swap in ByteTrack at the same seam
when the demo graduates.
"""
from __future__ import annotations

from typing import Dict, List

from sdk.geometry import iou
from sdk.output.frame import Detection, Track


class SimpleTracker:
    def __init__(self, iou_thresh: float = 0.3, max_lost: int = 5):
        self.iou_thresh = iou_thresh
        self.max_lost = max_lost
        self._next_id = 0
        # id -> {bbox, velocity, det, lost}
        self._tracks: Dict[int, dict] = {}

    def update(self, detections: List[Detection], dt: float = 0.1) -> List[Track]:
        unmatched = list(detections)

        for tid, t in list(self._tracks.items()):
            best_idx = -1
            best_iou = 0.0
            for j, d in enumerate(unmatched):
                if d.bbox_2d is None or t["bbox"] is None:
                    continue
                v = iou(d.bbox_2d, t["bbox"])
                if v > best_iou:
                    best_iou, best_idx = v, j

            if best_idx >= 0 and best_iou >= self.iou_thresh:
                d = unmatched.pop(best_idx)
                prev = t["bbox"]
                vx = (d.bbox_2d.x + d.bbox_2d.w / 2 - (prev.x + prev.w / 2)) / dt
                vy = (d.bbox_2d.y + d.bbox_2d.h / 2 - (prev.y + prev.h / 2)) / dt
                t["bbox"] = d.bbox_2d
                t["velocity"] = (vx, vy, 0.0)
                t["det"] = d
                t["lost"] = 0
            else:
                t["lost"] += 1

        for tid in [tid for tid, t in self._tracks.items() if t["lost"] > self.max_lost]:
            del self._tracks[tid]

        for d in unmatched:
            self._tracks[self._next_id] = {
                "bbox": d.bbox_2d,
                "velocity": (0.0, 0.0, 0.0),
                "det": d,
                "lost": 0,
            }
            self._next_id += 1

        out: List[Track] = []
        for tid, t in self._tracks.items():
            d = t["det"]
            out.append(
                Track(
                    cls_id=d.cls_id,
                    cls_name=d.cls_name,
                    bbox_2d=t["bbox"],
                    bbox_3d=d.bbox_3d,
                    confidence=d.confidence,
                    source=d.source,
                    occlusion_ratio=d.occlusion_ratio,
                    small_target_score=d.small_target_score,
                    track_id=tid,
                    velocity=t["velocity"],
                )
            )
        return out
