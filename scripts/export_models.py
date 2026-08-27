"""Export YOLO weights to ONNX for hardware-agnostic inference.

The SDK runs inference through ONNX Runtime so the same model graph targets
CPU / CUDA / TensorRT / ARM ACL without code changes. This script produces the
`.onnx` artifacts (committed nowhere — see .gitignore).

Usage:
    python scripts/export_models.py yolo11s.pt [yolo11x.pt ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    try:
        from ultralytics import YOLO
    except ImportError as e:
        raise SystemExit(
            "ultralytics not installed. Run `pip install -r requirements-ml.txt` "
            "in a Python 3.11/3.12 virtualenv."
        ) from e

    weights = sys.argv[1:] or ["yolo11s.pt"]
    for w in weights:
        model = YOLO(w)
        out = model.export(format="onnx", opset=12, simplify=True)
        print(f"exported {w} → {out}")


if __name__ == "__main__":
    main()
