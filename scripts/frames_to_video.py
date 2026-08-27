"""Encode the generated replay frames into an MP4 video.

Works with OpenCV only (no ffmpeg dependency), so it runs anywhere the SDK's
core deps are installed. FPS defaults to 20 to match `make_demo_data.py`'s
50 ms frame interval.

Usage:
    python scripts/frames_to_video.py [frames_dir] [out_mp4] [fps]
Defaults:
    frames_dir = data/frames
    out_mp4    = data/demo.mp4
    fps        = 20
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2


def main() -> None:
    frames_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/frames")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data/demo.mp4")
    fps = float(sys.argv[3]) if len(sys.argv) > 3 else 20.0

    files = sorted(frames_dir.glob("*.jpg"))
    if not files:
        raise SystemExit(f"no *.jpg found in {frames_dir}")

    first = cv2.imread(str(files[0]))
    h, w = first.shape[:2]
    writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    if not writer.isOpened():
        raise SystemExit(f"could not open VideoWriter for {out}")

    for f in files:
        img = cv2.imread(str(f))
        if img is None:
            continue
        writer.write(img)
    writer.release()
    print(f"wrote {len(files)} frames → {out} ({fps} fps, {w}x{h})")


if __name__ == "__main__":
    main()
