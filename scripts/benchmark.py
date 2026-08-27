"""Benchmark the backends against each other (latency + detection count).

Compares offline (PyTorch) with the ONNX Runtime path on every EP this host
supports (CPU, CoreML on macOS, ...), so the "hardware-agnostic, pluggable EP"
story is backed by numbers rather than a config comment.

Usage:
    python scripts/benchmark.py [frame_index] [n_iter]
Defaults:
    frame_index = 0     (data/frames/frame_000000.jpg — the busiest scene)
    n_iter      = 20
"""
from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2

from sdk.backend import OfflineBackend, OnnxBackend
from sdk.config import load_config


def main() -> None:
    idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    cfg = load_config("config/robot.demo.yaml")

    frames = sorted(Path("data/frames").glob("*.jpg"))
    if not frames:
        raise SystemExit("no frames in data/frames/ — run scripts/fetch_demo_data.py first")
    frame_path = frames[idx % len(frames)]
    img = cv2.imread(str(frame_path))
    print(f"frame: {frame_path.name} ({img.shape[1]}x{img.shape[0]})  iters={n}\n")

    import onnxruntime as ort

    avail = ort.get_available_providers()
    candidates = [("offline (PyTorch)", OfflineBackend)]
    if "CoreMLExecutionProvider" in avail:
        candidates.append(("onnx:coreml", lambda: OnnxBackend(providers=["CoreMLExecutionProvider"])))
    candidates.append(("onnx:cpu", OnnxBackend))

    results: dict[str, float] = {}
    for label, factory in candidates:
        be = factory()
        try:
            be.init(cfg)
        except Exception as e:  # pragma: no cover - host-dependent
            print(f"{label:20s} SKIP ({type(e).__name__}: {e})")
            continue
        for _ in range(3):
            be.detect(img)  # warmup (EP compile / alloc)
        times, nobj = [], 0
        for _ in range(n):
            t0 = time.perf_counter()
            dets = be.detect(img)
            times.append((time.perf_counter() - t0) * 1000.0)
            nobj = len(dets)
        be.release()
        med = statistics.median(times)
        results[label] = med
        print(f"{label:20s} {med:6.1f} ms/frame (median)   objects={nobj:3d}")

    base = results.get("offline (PyTorch)")
    if base:
        print("\nvs PyTorch baseline:")
        for lab, med in results.items():
            if lab == "offline (PyTorch)":
                continue
            print(f"  {lab:20s} {med / base:5.2f}x  ({'faster' if med < base else 'slower'})")


if __name__ == "__main__":
    main()
