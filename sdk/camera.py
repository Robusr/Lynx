"""Pinhole camera model — the 3D↔2D bridge used by LiDAR late fusion.

Frame convention matches `BBox3D` (right-handed vehicle frame: forward-x,
left-y, up-z). A point `(x, y, z)` is expressed in the camera frame; projection
follows the standard pinhole equations with `fx/fy/cx/cy`. Box projection is
axis-aligned for now (yaw is not yet applied) — sufficient for the demo fusion
path; a production build adds the full yaw rotation and per-sensor extrinsics.
"""
from __future__ import annotations

from typing import Tuple

from sdk.output.frame import BBox2D, BBox3D


class Pinhole:
    def __init__(self, fx: float, fy: float, cx: float, cy: float, width: int, height: int):
        self.fx = float(fx)
        self.fy = float(fy)
        self.cx = float(cx)
        self.cy = float(cy)
        self.width = int(width)
        self.height = int(height)

    @classmethod
    def for_size(cls, width: int, height: int) -> "Pinhole":
        """Default intrinsics from image size (fx=fy=width ≈ 53° HFOV, centered)."""
        return cls(fx=width, fy=width, cx=width / 2, cy=height / 2, width=width, height=height)

    def project(self, x: float, y: float, z: float) -> Tuple[float, float]:
        """Project a camera-frame point to pixel `(u, v)`; NaN if behind the camera."""
        if x <= 0:
            return float("nan"), float("nan")
        u = self.cx - self.fx * (y / x)
        v = self.cy - self.fy * (z / x)
        return u, v

    def project_box(self, box: BBox3D) -> BBox2D:
        """Project a 3D box to a 2D box via a center-anchored pinhole projection.

        Projects the box center and scales its width/height by the
        pixels-per-metre at that depth. Ignores near/far perspective distortion
        and yaw — a deliberate simplification for the demo association step.
        """
        if box.x <= 0:
            return BBox2D(x=0.0, y=0.0, w=0.0, h=0.0)
        u0 = self.cx - self.fx * (box.y / box.x)
        v0 = self.cy - self.fy * (box.z / box.x)
        w_px = box.w * self.fx / box.x
        h_px = box.h * self.fy / box.x
        return BBox2D(x=u0 - w_px / 2, y=v0 - h_px / 2, w=w_px, h=h_px)

    def depth_from_height(self, bbox_h_px: float, object_h_m: float) -> float:
        """Inverse of projection: recover forward depth from a 2D box height."""
        return self.fy * object_h_m / max(bbox_h_px, 1e-3)
