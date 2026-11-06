"""Headless smoke test: run the real pipeline for N frames and print detections.

Exercises the full vertical slice (config → preflight → backend → tracking →
PerceptionFrame) without the FastAPI server. Also the CI entry point.

Usage:
    python scripts/smoke.py [config.yaml] [n_frames] [--jsonl] [--accept-warnings]
Defaults:
    config.yaml = config/robot.demo.yaml
    n_frames    = 5
Options:
    --jsonl             publish each PerceptionFrame as NDJSON on stdout
    --accept-warnings   allow a manifest with preflight warnings to start

Human-readable logs always go to stderr, so `--jsonl` stdout is pure NDJSON.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from sdk.config import load_config
from sdk.pipeline import PreflightError, build_middleware_adapter, run


def main() -> None:
    jsonl = "--jsonl" in sys.argv[1:]
    accept_warnings = "--accept-warnings" in sys.argv[1:]
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    cfg_path = argv[0] if argv else str(REPO / "config" / "robot.demo.yaml")
    n = int(argv[1]) if len(argv) > 1 else 5
    cfg = load_config(cfg_path)

    def human(*args) -> None:
        print(*args, file=sys.stderr if jsonl else sys.stdout)

    def on_frame(frame, image):
        human(
            f"[stamp={frame.stamp_ns}] objects={len(frame.objects)} "
            f"signs={len(frame.traffic_signs)} latency={frame.latency_ms:.1f}ms"
        )
        for o in frame.objects:
            b = o.bbox_2d
            box = f"({b.x:.0f},{b.y:.0f},{b.w:.0f},{b.h:.0f})" if b else "None"
            human(f"   #{o.track_id:<3} {o.cls_name:<14} conf={o.confidence:.2f} bbox={box}")
        for s in frame.traffic_signs:
            human(f"   sign {s.cls_name:<14} conf={s.confidence:.2f}")

    try:
        middleware = build_middleware_adapter(cfg) if jsonl else None
        run(
            cfg,
            on_frame,
            max_frames=n,
            middleware=middleware,
            accept_warnings=accept_warnings,
        )
    except PreflightError as exc:
        print(f"smoke: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
