"""FastAPI demo server: runs the perception pipeline and streams results.

- `GET  /`            → dashboard (single-page HTML)
- `WS   /ws`          → streams {frame: PerceptionFrame, image: base64 JPEG}
- `GET  /api/state`   → backend + liveness
- `GET  /api/metrics` → runtime telemetry (latency / throughput / sources)
- `POST /api/switch`  → flip offline ↔ enhanced ↔ onnx at runtime

The pipeline runs in a daemon thread; the server only holds the latest frame and
broadcasts it. Annotation (drawing boxes) lives here, in the presentation layer —
the SDK itself never mutates pixels.
"""
from __future__ import annotations

import asyncio
import base64
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel

from sdk import pipeline
from sdk.config import load_config
from sdk.metrics import Metrics
from sdk.output.frame import PerceptionFrame

REPO = Path(__file__).resolve().parent
CONFIG_PATH = os.environ.get("LYNX_CONFIG", str(REPO / "config" / "robot.demo.yaml"))


def annotate(image: np.ndarray, frame: PerceptionFrame) -> np.ndarray:
    """Draw object + traffic-sign boxes onto a copy (presentation only)."""
    out = image.copy()
    for o in frame.objects:
        if o.bbox_2d is None:
            continue
        b = o.bbox_2d
        x1, y1 = int(b.x), int(b.y)
        x2, y2 = int(b.x + b.w), int(b.y + b.h)
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)
        label = f"{o.cls_name} #{o.track_id} {o.confidence:.2f}"
        cv2.putText(out, label, (x1, max(15, y1 - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    for s in frame.traffic_signs:
        if s.bbox_2d is None:
            continue
        b = s.bbox_2d
        x1, y1 = int(b.x), int(b.y)
        x2, y2 = int(b.x + b.w), int(b.y + b.h)
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 255), 2)
        cv2.putText(out, s.cls_name, (x1, max(15, y1 - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
    return out


class PerceptionService:
    """Owns the pipeline thread and the latest broadcast payload."""

    def __init__(self, cfg_path: str):
        self.cfg = load_config(cfg_path)
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None
        self.latest: dict | None = None
        self.latest_jpeg: str | None = None
        self.metrics = Metrics()

    @property
    def backend(self) -> str:
        return self.cfg.perception.backend

    def _on_frame(self, frame: PerceptionFrame, image: np.ndarray | None) -> None:
        jpeg_b64 = None
        if image is not None:
            ok, buf = cv2.imencode(".jpg", annotate(image, frame))
            if ok:
                jpeg_b64 = base64.b64encode(buf.tobytes()).decode("ascii")
        with self.lock:
            self.latest = frame.model_dump()
            self.latest_jpeg = jpeg_b64

    def start(self) -> None:
        self.stop.clear()
        self.thread = threading.Thread(
            target=pipeline.run,
            args=(self.cfg, self._on_frame, self.stop),
            kwargs={"metrics": self.metrics},
            daemon=True,
        )
        self.thread.start()

    def switch(self, backend: str) -> None:
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=2.0)
        self.cfg.perception.backend = backend
        self.start()


service = PerceptionService(CONFIG_PATH)


@asynccontextmanager
async def lifespan(app: FastAPI):
    service.start()
    yield
    service.stop.set()


app = FastAPI(title="Lynx Perception SDK Demo", lifespan=lifespan)


@app.get("/")
async def index():
    return FileResponse(str(REPO / "dashboard" / "index.html"))


@app.get("/api/state")
async def state():
    running = service.thread is not None and service.thread.is_alive()
    return {"backend": service.backend, "running": running, "has_frame": service.latest is not None}


@app.get("/api/metrics")
async def metrics():
    return service.metrics.snapshot()


class SwitchRequest(BaseModel):
    backend: str  # offline | enhanced | onnx


@app.post("/api/switch")
async def switch(req: SwitchRequest):
    if req.backend not in ("offline", "enhanced", "onnx"):
        return {"error": f"unknown backend {req.backend!r}"}
    service.switch(req.backend)
    return {"backend": service.backend}


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            with service.lock:
                payload = service.latest
                jpeg = service.latest_jpeg
            await websocket.send_json({"frame": payload, "image": jpeg})
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
