"""Headless smoke test: run the real pipeline for N frames and print detections.

Exercises the full vertical slice (config → preflight → backend → tracking →
PerceptionFrame) without the FastAPI server. Also the CI entry point.

Usage:
    python scripts/smoke.py [config.yaml] [n_frames]
Defaults:
    config.yaml = config/robot.demo.yaml
    n_frames    = 5
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sdk.config import load_config
from sdk.pipeline import run


def main() -> None:
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "config/robot.demo.yaml"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    cfg = load_config(cfg_path)

    def on_frame(frame, image):
        print(
            f"[stamp={frame.stamp_ns}] objects={len(frame.objects)} "
            f"signs={len(frame.traffic_signs)} latency={frame.latency_ms:.1f}ms"
        )
        for o in frame.objects:
            b = o.bbox_2d
            box = f"({b.x:.0f},{b.y:.0f},{b.w:.0f},{b.h:.0f})" if b else "None"
            print(f"   #{o.track_id:<3} {o.cls_name:<14} conf={o.confidence:.2f} bbox={box}")
        for s in frame.traffic_signs:
            print(f"   sign {s.cls_name:<14} conf={s.confidence:.2f}")

    run(cfg, on_frame, max_frames=n)


if __name__ == "__main__":
    main()
