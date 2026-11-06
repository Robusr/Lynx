"""SORT-lite tracker: class-aware greedy association + 2D/3D velocity.

A minimal multi-object tracker that turns per-frame `Detection`s into persistent
`Track`s. Association prefers 2D IoU and falls back to a 3D centre-distance gate
for lidar-only detections. Velocity is emitted in both image space (`velocity_px`)
and, when two consecutive 3D boxes exist, in the vehicle frame (`velocity`).

Deliberately free of Kalman/BYTE complexity so the skeleton stays legible; swap
in ByteTrack at the same seam when the demo graduates.
"""
from __future__ import annotations

from typing import Dict, List

from sdk.geometry import iou
from sdk.output.frame import BBox2D, BBox3D, Detection, Track


class SimpleTracker:
    def __init__(self, iou_thresh: float = 0.3, max_lost: int = 5, gate_3d_m: float = 3.0):
        self.iou_thresh = iou_thresh
        self.max_lost = max_lost
        self.gate_3d_m = gate_3d_m
        self._next_id = 0
        # id -> {bbox, pos3d, velocity, velocity_px, det, lost}
        self._tracks: Dict[int, dict] = {}

    @staticmethod
    def _match_key(d: Detection) -> str:
        """Prevent association across different classes (a car never becomes a person)."""
        return d.cls_name if d.cls_name != "obstacle" else "obstacle"

    @staticmethod
    def _center(box: BBox2D) -> tuple:
        return box.x + box.w / 2.0, box.y + box.h / 2.0

    def _score(self, det: Detection, track: dict) -> float:
        if det.bbox_2d is not None and track["bbox"] is not None:
            return iou(det.bbox_2d, track["bbox"])
        if det.bbox_3d is not None and track["pos3d"] is not None:
            a = det.bbox_3d
            b: BBox3D = track["pos3d"]
            distance = ((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2) ** 0.5
            return max(0.0, 1.0 - distance / self.gate_3d_m)
        return 0.0

    def update(self, detections: List[Detection], dt: float = 0.1) -> List[Track]:
        dt = max(dt, 1e-6)
        unmatched = list(detections)

        for tid, t in list(self._tracks.items()):
            best_idx = -1
            best_score = 0.0
            for j, d in enumerate(unmatched):
                if self._match_key(d) != t["key"]:
                    continue
                score = self._score(d, t)
                if score > best_score:
                    best_score, best_idx = score, j

            if best_idx >= 0 and best_score >= self.iou_thresh:
                d = unmatched.pop(best_idx)
                prev_bbox = t["bbox"]
                velocity = (0.0, 0.0, 0.0)
                if d.bbox_2d is not None and prev_bbox is not None:
                    cx, cy = self._center(d.bbox_2d)
                    pcx, pcy = self._center(prev_bbox)
                    velocity_px = ((cx - pcx) / dt, (cy - pcy) / dt)
                else:
                    velocity_px = (0.0, 0.0)
                if d.bbox_3d is not None and t["pos3d"] is not None:
                    prev3: BBox3D = t["pos3d"]
                    cur3 = d.bbox_3d
                    velocity = (
                        (cur3.x - prev3.x) / dt,
                        (cur3.y - prev3.y) / dt,
                        (cur3.z - prev3.z) / dt,
                    )
                t["bbox"] = d.bbox_2d
                t["pos3d"] = d.bbox_3d
                t["velocity"] = velocity
                t["velocity_px"] = velocity_px
                t["det"] = d
                t["lost"] = 0
            else:
                t["lost"] += 1

        for tid in [tid for tid, t in self._tracks.items() if t["lost"] > self.max_lost]:
            del self._tracks[tid]

        for d in unmatched:
            self._tracks[self._next_id] = {
                "key": self._match_key(d),
                "bbox": d.bbox_2d,
                "pos3d": d.bbox_3d,
                "velocity": (0.0, 0.0, 0.0),
                "velocity_px": (0.0, 0.0),
                "det": d,
                "lost": 0,
            }
            self._next_id += 1

        out: List[Track] = []
        for tid, t in self._tracks.items():
            det: Detection = t["det"]
            out.append(
                Track(
                    cls_id=det.cls_id,
                    cls_name=det.cls_name,
                    type=det.type,
                    sub_type=det.sub_type,
                    bbox_2d=t["bbox"],
                    bbox_3d=det.bbox_3d,
                    confidence=det.confidence,
                    source=det.source,
                    occlusion_ratio=det.occlusion_ratio,
                    small_target_score=det.small_target_score,
                    pose_covariance=det.pose_covariance,
                    attributes=det.attributes,
                    track_id=tid,
                    velocity=t["velocity"],
                    velocity_px=t["velocity_px"],
                )
            )
        return out
