"""Standardized perception data model.

This is the **product contract** — the single data schema every backend emits and
every downstream consumer reads. It mirrors the design in the technical architecture
doc (PerceptionFrame / Object / TrafficSign), aligned with ASAM OpenLABEL object
taxonomy and ISO 23150 field semantics.

Keep this file dependency-light (pydantic only) so it can be the reference for a
later C++/proto hardening.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from pydantic import BaseModel, Field


class BBox2D(BaseModel):
    """Axis-aligned 2D box in image pixels (top-left origin)."""

    x: float
    y: float
    w: float
    h: float


class BBox3D(BaseModel):
    """3D box in the vehicle frame (right-handed: forward-x, left-y, up-z)."""

    x: float
    y: float
    z: float
    l: float
    w: float
    h: float
    yaw: float


class Detection(BaseModel):
    """A single raw detection before tracking (no track id)."""

    cls_id: int
    cls_name: str  # person / car / truck / cone / stop sign / ... (open text allowed)
    bbox_2d: Optional[BBox2D] = None
    bbox_3d: Optional[BBox3D] = None
    confidence: float
    source: str = "camera"  # camera | lidar | fusion
    occlusion_ratio: float = 0.0  # 0..1
    small_target_score: float = 0.0  # enhanced-backend only; always 0 for offline


class Track(Detection):
    """A tracked detection with a persistent id and velocity."""

    track_id: int
    velocity: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # m/s in vehicle frame


class TrafficSign(BaseModel):
    """A detected traffic sign / light."""

    cls_name: str  # stop / speed_limit / yield / traffic_light / ...
    text: Optional[str] = None  # OCR text, e.g. the speed value
    bbox_2d: Optional[BBox2D] = None
    confidence: float


class PerceptionFrame(BaseModel):
    """The standardized output frame published once per detection cycle."""

    stamp_ns: int
    frame_id: str
    backend: str = "offline"  # offline | enhanced — rendered on the dashboard
    objects: List[Track] = Field(default_factory=list)
    traffic_signs: List[TrafficSign] = Field(default_factory=list)
    latency_ms: float = 0.0
