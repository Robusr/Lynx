"""Standardized perception data model.

This is the **product contract** — the single data schema every backend emits and
every downstream consumer reads. It mirrors the design in the technical architecture
doc (PerceptionFrame / Object / TrafficSign), aligned with ASAM OpenLABEL object
taxonomy and ISO 23150 field semantics.

Field provenance (see 02-technical-architecture.md §4):

- `type` (coarse enum) and `sub_type` (open text) are derived from `cls_name`
  when not set explicitly, so backends keep emitting COCO names while the
  contract exposes the stable OpenLABEL taxonomy.
- `source` is a `SourceMask` bitmask (camera|lidar|radar) — a fused object
  carries several bits at once, matching the doc's `SourceMask source`.
- `attributes` is the `@ai-extend` hook: integrators add keys without changing
  the core model.

Keep this file dependency-light (pydantic only) so it can be the reference for a
later C++/proto hardening. Fields that need their own perception modules first
(lanes, freespace, traffic_lights, ego_motion, sensor_status) are intentionally
absent for now.
"""
from __future__ import annotations

from enum import Enum, IntFlag
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, model_validator


class ObjectType(str, Enum):
    """Coarse object taxonomy, ASAM OpenLABEL-aligned (the doc's `Object.type`)."""

    PEDESTRIAN = "pedestrian"
    BICYCLE = "bicycle"
    VEHICLE = "vehicle"
    TRUCK = "truck"
    CONE = "cone"
    BARRIER = "barrier"
    TRAFFIC_SIGN = "traffic_sign"
    TRAFFIC_LIGHT = "traffic_light"
    UNKNOWN = "unknown"


class SignType(str, Enum):
    """Traffic sign / signal taxonomy (the doc's `TrafficSign.type`)."""

    STOP = "stop"
    SPEED_LIMIT = "speed_limit"
    YIELD = "yield"
    NO_ENTRY = "no_entry"
    TRAFFIC_LIGHT = "traffic_light"
    UNKNOWN = "unknown"


class SourceMask(IntFlag):
    """Sensor provenance bitmask — a fused object carries several bits at once."""

    CAMERA = 1
    LIDAR = 2
    RADAR = 4


# COCO class name -> coarse object type. Only the base set is mapped; anything
# else (open text) falls through to UNKNOWN and is carried by `sub_type`.
_CLS_NAME_TO_TYPE = {
    "person": ObjectType.PEDESTRIAN,
    "bicycle": ObjectType.BICYCLE,
    "car": ObjectType.VEHICLE,
    "motorcycle": ObjectType.VEHICLE,
    "bus": ObjectType.VEHICLE,
    "train": ObjectType.VEHICLE,
    "truck": ObjectType.TRUCK,
    "cone": ObjectType.CONE,
    "barrier": ObjectType.BARRIER,
    "stop sign": ObjectType.TRAFFIC_SIGN,
    "traffic light": ObjectType.TRAFFIC_LIGHT,
}

_SIGN_NAME_TO_TYPE = {
    "stop sign": SignType.STOP,
    "speed_limit": SignType.SPEED_LIMIT,
    "yield": SignType.YIELD,
    "no_entry": SignType.NO_ENTRY,
    "traffic light": SignType.TRAFFIC_LIGHT,
}


def coerce_object_type(cls_name: str) -> ObjectType:
    return _CLS_NAME_TO_TYPE.get(cls_name.lower(), ObjectType.UNKNOWN)


def coerce_sign_type(cls_name: str) -> SignType:
    return _SIGN_NAME_TO_TYPE.get(cls_name.lower(), SignType.UNKNOWN)


def source_label(mask: SourceMask) -> str:
    """Human-readable provenance for a `SourceMask` (metrics/telemetry)."""
    names = []
    if mask & SourceMask.CAMERA:
        names.append("camera")
    if mask & SourceMask.LIDAR:
        names.append("lidar")
    if mask & SourceMask.RADAR:
        names.append("radar")
    if len(names) > 1:
        return "fusion"
    return names[0] if names else "unknown"


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
    cls_name: str  # COCO / open text (the raw classifier label)
    type: ObjectType = ObjectType.UNKNOWN  # coarse taxonomy, derived from cls_name
    sub_type: Optional[str] = None  # open-text refinement, e.g. "forklift"
    bbox_2d: Optional[BBox2D] = None
    bbox_3d: Optional[BBox3D] = None
    confidence: float
    source: SourceMask = Field(
        default=SourceMask.CAMERA,
        description="SourceMask bitmask: 1=camera, 2=lidar, 4=radar (OR together for fusion).",
    )
    occlusion_ratio: float = 0.0  # 0..1
    small_target_score: float = 0.0  # enhanced-backend only; always 0 for offline
    pose_covariance: List[float] = Field(
        default_factory=list,
        description="6x6 pose covariance, row-major; empty when unknown.",
    )
    attributes: Dict[str, Any] = Field(
        default_factory=dict,
        description="@ai-extend custom attributes (free-form).",
    )

    @model_validator(mode="after")
    def _fill_derived(self) -> "Detection":
        if self.type is ObjectType.UNKNOWN and self.cls_name:
            self.type = coerce_object_type(self.cls_name)
        if self.sub_type is None:
            self.sub_type = self.cls_name
        return self


class Track(Detection):
    """A tracked detection with a persistent id and velocity."""

    track_id: int
    velocity: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # m/s in vehicle frame


class TrafficSign(BaseModel):
    """A detected traffic sign / light."""

    id: int = 0
    type: SignType = SignType.UNKNOWN  # derived from cls_name
    cls_name: str  # stop / speed_limit / yield / traffic_light / ...
    text: Optional[str] = None  # OCR text, e.g. the speed value
    bbox_2d: Optional[BBox2D] = None
    bbox_3d: Optional[BBox3D] = None
    confidence: float
    stamp_ns: int = 0  # observation timestamp (aligned to the master clock)

    @model_validator(mode="after")
    def _fill_type(self) -> "TrafficSign":
        if self.type is SignType.UNKNOWN and self.cls_name:
            self.type = coerce_sign_type(self.cls_name)
        return self


class PerceptionFrame(BaseModel):
    """The standardized output frame published once per detection cycle.

    `stamp_ns` + `frame_id` + `seq` map to the architecture doc's `Header`
    message (flattened here for the Python prototype).
    """

    stamp_ns: int
    frame_id: str
    seq: int = 0  # monotonic frame sequence (Header.seq)
    backend: str = "offline"  # offline | enhanced — rendered on the dashboard
    objects: List[Track] = Field(default_factory=list)
    traffic_signs: List[TrafficSign] = Field(default_factory=list)
    latency_ms: float = 0.0
