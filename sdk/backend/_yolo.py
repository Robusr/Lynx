"""Lazy ultralytics glue shared by both backends.

Importing ultralytics is expensive and unavailable on Python 3.14, so it happens
only here, at init-time, with a readable error otherwise.
"""
from __future__ import annotations

from typing import List, Optional

from sdk.output.frame import BBox2D, Detection, SourceMask


def load_yolo(weights: str, device: Optional[str] = None):
    try:
        from ultralytics import YOLO
    except ImportError as e:  # pragma: no cover - depends on env
        raise RuntimeError(
            "ultralytics is not installed. Run `pip install -r requirements-ml.txt` "
            "inside a Python 3.11/3.12 virtualenv."
        ) from e
    return YOLO(weights)


def predict_detections(
    model, image, conf: float = 0.25, device: Optional[str] = None
) -> List[Detection]:
    """Run a YOLO model and map `results[0].boxes` → `Detection` (xyxy → xywh)."""
    results = model.predict(image, conf=conf, verbose=False, device=device)
    names = model.names
    dets: List[Detection] = []
    for r in results:
        boxes = getattr(r, "boxes", None)
        if boxes is None:
            continue
        for i in range(len(boxes)):
            x1, y1, x2, y2 = boxes.xyxy[i].tolist()
            cls = int(boxes.cls[i])
            dets.append(
                Detection(
                    cls_id=cls,
                    cls_name=str(names.get(cls, cls)),
                    bbox_2d=BBox2D(x=x1, y=y1, w=x2 - x1, h=y2 - y1),
                    confidence=float(boxes.conf[i]),
                    source=SourceMask.CAMERA,
                )
            )
    return dets
