"""Synthetic LiDAR for the demo — no real sensor attached.

Back-projects each camera detection to a plausible 3D box and emits it as an
independent LiDAR detection (`source="lidar"`). Depth comes from the pinhole
height heuristic (`depth = fy * object_height / bbox_height`); the remaining
pose/size terms invert `Pinhole.project_box` so the forward projection
reproduces the camera box exactly, and fusion associates 1:1. This lets the
late-fusion path run end-to-end without hardware; a production build swaps this
for a real point-cloud clustering front-end. The association in
`fuse_camera_lidar` is the same either way.
"""
from __future__ import annotations

from typing import List

from sdk.camera import Pinhole
from sdk.output.frame import BBox3D, Detection

# Typical 3D extents (l, w, h) in metres, per class, for the synthetic LiDAR.
CLASS_SIZE = {
    "car": (4.5, 1.8, 1.5),
    "truck": (7.0, 2.5, 2.8),
    "bus": (11.0, 2.5, 3.0),
    "motorcycle": (2.2, 0.8, 1.4),
    "bicycle": (1.8, 0.6, 1.2),
    "person": (0.6, 0.5, 1.7),
}


def synthetic_lidar(camera_dets: List[Detection], cam: Pinhole) -> List[Detection]:
    out: List[Detection] = []
    for d in camera_dets:
        b = d.bbox_2d
        if b is None or b.w <= 0 or b.h <= 0:
            continue
        cl, _, ch = CLASS_SIZE.get(d.cls_name, (1.0, 1.0, 1.0))
        depth = cam.depth_from_height(b.h, ch)
        # Invert `Pinhole.project_box` so the round-trip is exact: projecting this
        # box back yields the camera box, and fusion associates 1:1 (demo seed).
        u0 = b.x + b.w / 2
        v0 = b.y + b.h / 2
        y = -(u0 - cam.cx) * depth / cam.fx
        z = (cam.cy - v0) * depth / cam.fy
        w = b.w * depth / cam.fx
        out.append(
            Detection(
                cls_id=-1,
                cls_name="obstacle",
                bbox_3d=BBox3D(x=depth, y=y, z=z, l=cl, w=w, h=ch, yaw=0.0),
                confidence=d.confidence,
                source="lidar",
            )
        )
    return out
