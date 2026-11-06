"""FastAPI demo server: runs the perception pipeline and streams results.

- `GET  /`            → dashboard (single-page HTML)
- `WS   /ws`          → streams {frame: PerceptionFrame, image: base64 JPEG}
- `GET  /api/state`   → backend, liveness, last error, latency ceiling
- `GET  /api/metrics` → runtime telemetry (latency / throughput / sources)
- `POST /api/switch`  → flip offline ↔ enhanced ↔ onnx at runtime

The pipeline runs in a daemon thread; annotation and JPEG encoding run in a
separate broadcaster thread so expensive presentation work never blocks
detection. The server only holds the latest frame and image.
"""
from __future__ import annotations

import asyncio
import base64
import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from sdk import pipeline
from sdk.backend import build_backend
from sdk.config import load_config
from sdk.metrics import Metrics
from sdk.output.frame import PerceptionFrame
from sdk.validate import validate

REPO = Path(__file__).resolve().parent
CONFIG_PATH = os.environ.get("LYNX_CONFIG", str(REPO / "config" / "robot.demo.yaml"))
DASHBOARD_PATH = REPO / "dashboard" / "index.html"
ACCEPT_WARNINGS = os.environ.get("LYNX_ACCEPT_WARNINGS", "0") == "1"


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
    """Owns the pipeline thread, the broadcaster thread, and the latest payload."""

    def __init__(self, cfg_path: str):
        self.cfg = load_config(cfg_path)
        self.lock = threading.RLock()
        self._stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self._broadcast_stop = threading.Event()
        self._broadcast_thread: Optional[threading.Thread] = None
        self._frame_event = threading.Event()
        self._pending_image: Optional[np.ndarray] = None
        self.latest_frame: Optional[PerceptionFrame] = None
        self.latest_jpeg: Optional[str] = None
        self.jpeg_seq = 0
        self.viewers = 0
        self.metrics = Metrics()
        self.last_error = ""
        self.accept_warnings = ACCEPT_WARNINGS

    @property
    def backend(self) -> str:
        return self.cfg.perception.backend

    # -- pipeline ---------------------------------------------------------

    def _on_frame(self, frame: PerceptionFrame, image: Optional[np.ndarray]) -> None:
        with self.lock:
            self.latest_frame = frame
        if image is not None:
            with self.lock:
                self._pending_image = image
            self._frame_event.set()

    def _run_pipeline(self, cfg, backend, metrics: Metrics, stop_event: threading.Event) -> None:
        try:
            pipeline.run(
                cfg,
                self._on_frame,
                stop=stop_event,
                metrics=metrics,
                backend=backend,
                accept_warnings=self.accept_warnings,
            )
        except Exception as exc:  # surface startup/runtime failures to /api/state
            with self.lock:
                self.last_error = f"{type(exc).__name__}: {exc}"
            print(f"lynx: pipeline stopped: {exc}", file=sys.stderr)

    def start(self, backend=None) -> None:
        with self.lock:
            self.last_error = ""
            self._stop_event = threading.Event()
            event = self._stop_event
            metrics = self.metrics
            cfg = self.cfg
        self.thread = threading.Thread(
            target=self._run_pipeline,
            args=(cfg, backend, metrics, event),
            name="lynx-pipeline",
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=30.0)

    def switch(self, backend_name: str) -> None:
        """Pre-initialize the new backend, then swap it in without losing the old one on failure."""
        if backend_name not in ("offline", "enhanced", "onnx"):
            raise ValueError(f"unknown backend {backend_name!r}")

        new_cfg = self.cfg.model_copy(deep=True)
        new_cfg.perception.backend = backend_name
        checks = validate(new_cfg)
        errors = [c for c in checks if c.severity == "error"]
        warnings = [c for c in checks if c.severity == "warn"]
        if errors:
            detail = "; ".join(f"{c.name}: {c.message}" for c in errors)
            raise ValueError(f"preflight failed for {backend_name}: {detail}")
        if warnings and not self.accept_warnings:
            detail = "; ".join(f"{c.name}: {c.message}" for c in warnings)
            raise ValueError(
                f"preflight warnings for {backend_name}; set LYNX_ACCEPT_WARNINGS=1: {detail}"
            )

        new_backend = build_backend(new_cfg)
        try:
            new_backend.init(new_cfg)
        except Exception as exc:
            try:
                new_backend.release()
            finally:
                raise RuntimeError(
                    f"backend {backend_name!r} failed to initialize: {exc}"
                ) from exc

        self.stop()
        if self.thread is not None and self.thread.is_alive():
            new_backend.release()
            raise RuntimeError("old pipeline did not stop within 30 seconds")

        with self.lock:
            self.cfg = new_cfg
            self.metrics = Metrics()
            self.latest_frame = None
            self.latest_jpeg = None
            self.jpeg_seq += 1
        self.start(backend=new_backend)

    # -- presentation -----------------------------------------------------

    def start_broadcaster(self) -> None:
        if self._broadcast_thread is not None and self._broadcast_thread.is_alive():
            return
        self._broadcast_stop.clear()
        self._broadcast_thread = threading.Thread(
            target=self._broadcast_loop, name="lynx-broadcast", daemon=True
        )
        self._broadcast_thread.start()

    def stop_broadcaster(self) -> None:
        self._broadcast_stop.set()
        self._frame_event.set()
        if self._broadcast_thread is not None:
            self._broadcast_thread.join(timeout=2.0)

    def _broadcast_loop(self) -> None:
        while not self._broadcast_stop.is_set():
            if not self._frame_event.wait(0.5):
                continue
            self._frame_event.clear()
            with self.lock:
                image = self._pending_image
                self._pending_image = None
                frame = self.latest_frame
                viewers = self.viewers
            if image is None or frame is None or viewers <= 0:
                continue
            try:
                ok, buf = cv2.imencode(
                    ".jpg",
                    annotate(image, frame),
                    [int(cv2.IMWRITE_JPEG_QUALITY), 80],
                )
            except Exception as exc:
                with self.lock:
                    self.last_error = f"encode failed: {exc}"
                continue
            if not ok:
                continue
            jpeg = base64.b64encode(buf.tobytes()).decode("ascii")
            with self.lock:
                self.latest_jpeg = jpeg
                self.jpeg_seq += 1

    def add_viewer(self) -> None:
        with self.lock:
            self.viewers += 1

    def remove_viewer(self) -> None:
        with self.lock:
            self.viewers = max(0, self.viewers - 1)

    def state(self) -> dict:
        with self.lock:
            running = self.thread is not None and self.thread.is_alive()
            return {
                "backend": self.backend,
                "running": running,
                "has_frame": self.latest_frame is not None,
                "error": self.last_error,
                "latency_threshold_ms": self.cfg.safety.max_detection_latency_ms,
            }

    def metrics_snapshot(self) -> dict:
        with self.lock:
            return self.metrics.snapshot()


service = PerceptionService(CONFIG_PATH)


@asynccontextmanager
async def lifespan(app: FastAPI):
    service.start_broadcaster()
    service.start()
    try:
        yield
    finally:
        service.stop()
        service.stop_broadcaster()


app = FastAPI(title="Lynx Perception SDK Demo", lifespan=lifespan)

# The VS Code webview has a vscode-webview:// origin and calls /api/switch with
# fetch, so the demo server must answer CORS preflight for local webview origins.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(vscode-webview://.*|https?://(127\.0\.0\.1|localhost)(:\d+)?)$",
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/")
async def index():
    html = DASHBOARD_PATH.read_text(encoding="utf-8").replace("__ORIGIN__", "")
    return HTMLResponse(html)


@app.get("/api/state")
async def state():
    return service.state()


@app.get("/api/metrics")
async def metrics():
    return service.metrics_snapshot()


class SwitchRequest(BaseModel):
    backend: str  # offline | enhanced | onnx


@app.post("/api/switch")
async def switch(req: SwitchRequest):
    try:
        await asyncio.to_thread(service.switch, req.backend)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"backend": service.backend}


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    service.add_viewer()
    last_key = None
    try:
        while True:
            with service.lock:
                frame = service.latest_frame
                jpeg = service.latest_jpeg
                jpeg_seq = service.jpeg_seq
            key = (frame.seq if frame is not None else None, jpeg_seq)
            if key != last_key:
                await websocket.send_json(
                    {
                        "frame": frame.model_dump() if frame is not None else None,
                        "image": jpeg,
                    }
                )
                last_key = key
            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        pass
    finally:
        service.remove_viewer()
