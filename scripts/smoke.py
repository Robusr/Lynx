"""Headless smoke test: run the real pipeline for N frames and print detections.

Exercises the full vertical slice (config → preflight → backend → tracking →
PerceptionFrame) without the FastAPI server. Also the CI entry point.

Usage:
    python scripts/smoke.py [config.yaml] [n_frames] [--jsonl]
Defaults:
    config.yaml = config/robot.demo.yaml
    n_frames    = 5
Options:
    --jsonl     publish each PerceptionFrame as NDJSON (JsonLineMiddlewareAdapter)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sdk.config import load_config
from sdk.pipeline import build_middleware_adapter, run


def main() -> None:
    argv = [a for a in sys.argv[1:] if a != "--jsonl"]
    jsonl = "--jsonl" in sys.argv[1:]
    cfg_path = argv[0] if argv else "config/robot.demo.yaml"
    n = int(argv[1]) if len(argv) > 1 else 5
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

    middleware = build_middleware_adapter(cfg) if jsonl else None
    run(cfg, on_frame, max_frames=n, middleware=middleware)


if __name__ == "__main__":
    main()
