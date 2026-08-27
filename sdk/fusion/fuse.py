"""Late fusion — associate camera 2D detections with LiDAR 3D boxes.

Late fusion fuses at the *detection* level: each sensor detects independently,
then a cheap association (2D IoU after projecting LiDAR 3D boxes through the
pinhole model) pairs them. Matched pairs become fused objects carrying both the
camera's class + 2D box and the LiDAR's 3D box (`source="fusion"`). Unmatched
detections pass through unchanged.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from sdk.camera import Pinhole
from sdk.geometry import iou
from sdk.output.frame import Detection, SourceMask


def fuse_camera_lidar(
    camera_dets: List[Detection],
    lidar_dets: List[Detection],
    cam: Pinhole,
    iou_thresh: float = 0.3,
) -> List[Detection]:
    fused: List[Detection] = []
    lidar_2d: List[Tuple[Detection, object]] = [
        (d, cam.project_box(d.bbox_3d)) for d in lidar_dets if d.bbox_3d is not None
    ]
    matched_lidar: set = set()
    matched_cam: set = set()

    for ci, cd in enumerate(camera_dets):
        if cd.bbox_2d is None:
            matched_cam.add(ci)
            fused.append(cd)
            continue
        best: Optional[Tuple[int, Detection]] = None
        best_iou = iou_thresh
        for li, (ld, lb) in enumerate(lidar_2d):
            if li in matched_lidar or lb.w <= 0 or lb.h <= 0:
                continue
            v = iou(cd.bbox_2d, lb)
            if v > best_iou:
                best_iou = v
                best = (li, ld)
        if best is not None:
            li, ld = best
            fused.append(
                Detection(
                    cls_id=cd.cls_id,
                    cls_name=cd.cls_name,
                    bbox_2d=cd.bbox_2d,
                    bbox_3d=ld.bbox_3d,
                    confidence=max(cd.confidence, ld.confidence),
                    source=SourceMask.CAMERA | SourceMask.LIDAR,
                    occlusion_ratio=cd.occlusion_ratio,
                    small_target_score=cd.small_target_score,
                    pose_covariance=cd.pose_covariance,
                    attributes=cd.attributes,
                )
            )
            matched_lidar.add(li)
            matched_cam.add(ci)

    for ci, cd in enumerate(camera_dets):  # camera-only survivors
        if ci not in matched_cam:
            fused.append(cd)
    for li, (ld, _) in enumerate(lidar_2d):  # lidar-only survivors
        if li not in matched_lidar:
            fused.append(ld)
    return fused
