"""Contract + unit tests for LiDAR late fusion (camera ↔ lidar association)."""

from sdk.camera import Pinhole
from sdk.fusion.fuse import fuse_camera_lidar
from sdk.fusion.lidar import synthetic_lidar
from sdk.output.frame import BBox2D, BBox3D, Detection


def _cam() -> Pinhole:
    return Pinhole(fx=640, fy=640, cx=320, cy=214, width=640, height=428)


def test_project_forward_center():
    cam = _cam()
    u, v = cam.project(10.0, 0.0, 0.0)
    assert u == 320 and v == 214


def test_project_up_is_higher_in_image():
    cam = _cam()
    _, v0 = cam.project(10.0, 0.0, 0.0)
    _, v1 = cam.project(10.0, 0.0, 2.0)
    assert v1 < v0  # higher z → smaller v (higher in the image)


def test_project_left_is_smaller_u():
    cam = _cam()
    u0, _ = cam.project(10.0, 0.0, 0.0)
    u1, _ = cam.project(10.0, 1.0, 0.0)
    assert u1 < u0  # +y is left → left of center


def test_project_behind_is_nan():
    cam = _cam()
    u, v = cam.project(-1.0, 0.0, 0.0)
    assert u != u and v != v


def test_fuse_associates_overlapping_box():
    cam = _cam()
    lidar_box = BBox3D(x=10.0, y=0.0, z=0.75, l=4.5, w=1.8, h=1.5, yaw=0.0)
    lidar_det = Detection(cls_id=-1, cls_name="obstacle", bbox_3d=lidar_box, confidence=0.9, source="lidar")
    b2 = cam.project_box(lidar_box)
    cam_det = Detection(cls_id=2, cls_name="car", bbox_2d=b2, confidence=0.9, source="camera")

    fused = fuse_camera_lidar([cam_det], [lidar_det], cam)
    assert len(fused) == 1
    assert fused[0].source == "fusion"
    assert fused[0].cls_name == "car"
    assert fused[0].bbox_2d is not None and fused[0].bbox_3d is not None


def test_fuse_keeps_unmatched_detections():
    cam = _cam()
    cam_det = Detection(cls_id=2, cls_name="car", bbox_2d=BBox2D(x=10, y=10, w=50, h=40), confidence=0.9, source="camera")
    lidar_det = Detection(cls_id=-1, cls_name="obstacle", bbox_3d=BBox3D(x=10, y=0, z=0.75, l=4.5, w=1.8, h=1.5, yaw=0.0), confidence=0.9, source="lidar")

    fused = fuse_camera_lidar([cam_det], [lidar_det], cam)
    assert len(fused) == 2  # both survive, unmatched
    assert {d.source for d in fused} == {"camera", "lidar"}


def test_synthetic_lidar_back_projects_every_camera_box():
    cam = _cam()
    cam_dets = [
        Detection(cls_id=2, cls_name="car", bbox_2d=BBox2D(x=100, y=100, w=80, h=60), confidence=0.9),
        Detection(cls_id=0, cls_name="person", bbox_2d=BBox2D(x=300, y=50, w=20, h=80), confidence=0.8),
    ]
    lidar = synthetic_lidar(cam_dets, cam)
    assert len(lidar) == 2
    assert all(d.source == "lidar" and d.bbox_3d is not None for d in lidar)
    # a taller object at a given 2D height is further away than a short one
    car_depth = lidar[0].bbox_3d.x
    person_depth = lidar[1].bbox_3d.x
    assert person_depth < car_depth
