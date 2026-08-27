"""Generate synthetic replay frames for the demo/CI loop.

Renders a forward-looking scene (sky, ground, road, moving cars, a crossing
pedestrian, and a static stop sign) using the same pinhole projection the
dashboard's bird's-eye view assumes. This gives the dashboard a continuous
stream without a real vehicle, and a real YOLO model a chance to detect the
drawn shapes.

Usage:
    python scripts/make_demo_data.py [n_frames] [frames_dir]
Defaults:
    n_frames   = 240
    frames_dir = data/frames   (index written to data/index.csv)
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

try:
    import cv2
except ImportError as e:  # pragma: no cover - depends on env
    raise SystemExit("opencv-python is required. Run `pip install -r requirements.txt`.") from e

INTERVAL_NS = 50_000_000  # 50 ms → 20 Hz
DT = INTERVAL_NS / 1e9

SKY = (235, 206, 135)
GROUND = (70, 150, 80)
ROAD = (85, 85, 90)
LANE = (255, 255, 255)
CAR_COLORS = [(255, 0, 0), (0, 0, 255), (0, 140, 255)]  # BGR


class Pinhole:
    """Level, forward-facing ground-plane camera."""

    def __init__(self, focal: float = 500.0, width: int = 1280, height: int = 720, cam_height: float = 1.4):
        self.f = focal
        self.w = width
        self.h = height
        self.cx = width / 2.0
        self.cy = height / 2.0
        self.H = cam_height

    def u(self, X: float, Y: float) -> float:
        return self.cx + self.f * X / max(Y, 1e-3)

    def v(self, Z: float, Y: float) -> float:
        return self.cy - self.f * (Z - self.H) / max(Y, 1e-3)


def _rect(img, cam: Pinhole, X: float, Y: float, W: float, H: float, color, thickness: int = -1):
    """Draw a world-space box (lateral X, depth Y, width W, height H)."""
    u_l = cam.u(X - W / 2, Y)
    u_r = cam.u(X + W / 2, Y)
    v_b = cam.v(0.0, Y)          # bottom at ground
    v_t = cam.v(H, Y)            # top at height H
    cv2.rectangle(img, (int(u_l), int(v_t)), (int(u_r), int(v_b)), color, thickness)
    return int(u_l), int(u_r), int(v_t), int(v_b)


def _draw_car(img, cam: Pinhole, X: float, Y: float, color):
    u_l, u_r, v_t, v_b = _rect(img, cam, X, Y, 2.0, 1.5, color)
    # windshield band
    band = tuple(max(0, int(c * 0.6)) for c in color)
    cv2.rectangle(img, (int((u_l + u_r) / 2 - (u_r - u_l) * 0.15), v_t + int(0.1 * (v_b - v_t))),
                  (int((u_l + u_r) / 2 + (u_r - u_l) * 0.15), v_t + int(0.45 * (v_b - v_t))), band, -1)
    # wheels
    wh = int(0.28 * (v_b - v_t))
    ww = int(0.22 * (u_r - u_l))
    for ux in (u_l, u_r - ww):
        cv2.rectangle(img, (ux, v_b - wh), (ux + ww, v_b), (30, 30, 30), -1)


def _draw_pedestrian(img, cam: Pinhole, X: float, Y: float):
    u_l, u_r, v_t, v_b = _rect(img, cam, X, Y, 0.5, 1.7, (0, 120, 220))
    head_r = max(2, int(0.45 * (u_r - u_l)))
    cv2.circle(img, (int((u_l + u_r) / 2), v_t - head_r), head_r, (0, 180, 220), -1)


def _draw_stop_sign(img, cam: Pinhole, X: float, Y: float):
    _rect(img, cam, X, Y, 0.08, 2.2, (120, 120, 120))  # pole
    r = 0.35
    pts = []
    for k in range(8):
        ang = np.pi / 8 + k * np.pi / 4
        xw = X + r * np.cos(ang)
        zw = 2.2 + r * np.sin(ang)
        pts.append([int(cam.u(xw, Y)), int(cam.v(zw, Y))])
    cv2.fillPoly(img, [np.array(pts, np.int32)], (0, 0, 255))  # red octagon


def _scene(cam: Pinhole) -> np.ndarray:
    img = np.zeros((cam.h, cam.w, 3), np.uint8)
    cy = int(cam.cy)
    img[:cy] = SKY
    img[cy:] = GROUND
    top_half, bottom_half = 90, 620
    road = np.array([
        [cam.cx - top_half, cy],
        [cam.cx + top_half, cy],
        [cam.cx + bottom_half, cam.h],
        [cam.cx - bottom_half, cam.h],
    ], np.int32)
    cv2.fillPoly(img, [road], ROAD)
    for offset in (-180, 180):  # dashed lane markings
        for y in range(cy + 20, cam.h, 60):
            x = int(cam.cx + offset * (y - cy) / (cam.h - cy))
            cv2.line(img, (x, y), (x, y + 30), LANE, 4)
    return img


OBJECTS = [
    {"kind": "car", "x": -3.0, "y": 50.0, "vx": 0.0, "vy": -8.0, "color": CAR_COLORS[0], "y_min": 8.0, "y_max": 50.0},
    {"kind": "car", "x": 4.0, "y": 72.0, "vx": 0.0, "vy": -5.0, "color": CAR_COLORS[1], "y_min": 10.0, "y_max": 72.0},
    {"kind": "pedestrian", "x": 7.0, "y": 30.0, "vx": -1.2, "vy": 0.0, "x_min": -8.0, "x_max": 8.0},
    {"kind": "stop", "x": -2.5, "y": 20.0, "vx": 0.0, "vy": 0.0},
]


def _draw(obj, img, cam: Pinhole):
    if obj["kind"] == "car":
        _draw_car(img, cam, obj["x"], obj["y"], obj["color"])
    elif obj["kind"] == "pedestrian":
        _draw_pedestrian(img, cam, obj["x"], obj["y"])
    elif obj["kind"] == "stop":
        _draw_stop_sign(img, cam, obj["x"], obj["y"])


def _step(obj):
    obj["x"] += obj["vx"] * DT
    obj["y"] += obj["vy"] * DT
    if obj["kind"] == "car" and obj["y"] < obj["y_min"]:
        obj["y"] = obj["y_max"]
    elif obj["kind"] == "pedestrian" and obj["x"] < obj["x_min"]:
        obj["x"] = obj["x_max"]


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 240
    frames_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data/frames")
    frames_dir.mkdir(parents=True, exist_ok=True)
    index_path = frames_dir.parent / "index.csv"

    cam = Pinhole()
    with open(index_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["frame_name", "stamp_ns"])
        for i in range(n):
            img = _scene(cam)
            for obj in sorted(OBJECTS, key=lambda o: -o["y"]):  # far → near
                _draw(obj, img, cam)
            name = f"frame_{i:06d}.jpg"
            cv2.imwrite(str(frames_dir / name), img)
            w.writerow([name, i * INTERVAL_NS])
            for obj in OBJECTS:
                _step(obj)
    print(f"wrote {n} frames → {frames_dir} and index → {index_path}")


if __name__ == "__main__":
    main()
