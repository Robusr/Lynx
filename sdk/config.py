"""Configuration schema + loader for the single-source-of-truth manifest.

`robot.demo.yaml` is the only hand-written deployment file; everything else is
generated or validated from it (see sdk.validate). Pydantic gives structural
validation for free, and this model doubles as the JSON-Schema source for editor
IntelliSense (scripts/export_schema.py): `Literal[...]` becomes an enum dropdown,
`Field(description=...)` becomes hover docs, and `extra="forbid"` flags typos.
"""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field


class _Config(BaseModel):
    """Shared base: forbid undeclared keys so YAML typos fail loudly."""

    model_config = ConfigDict(extra="forbid")


class VehicleConfig(_Config):
    name: str = Field(description="Vehicle identifier, e.g. 'demo_factory_truck'.")
    type: str = Field(default="ackermann", description="Kinematic model (ackermann, differential, ...).")
    max_speed_ms: float = Field(default=5.0, description="Speed ceiling in m/s; safety checks reject <= 0.")


class DomainControllerConfig(_Config):
    model: Literal["laptop", "jetson_orin_nano", "rk3588"] = Field(
        default="laptop", description="Onboard compute target (drives resource-budget checks)."
    )
    inference_backend: Literal["onnx_cpu", "onnx_cuda", "tensorrt", "onnx_acl", "onnx_coreml"] = Field(
        default="onnx_cpu", description="Inference execution provider for the ONNX backend."
    )


class SensorConfig(_Config):
    name: str = Field(description="Sensor name (must be unique).")
    type: Literal["camera", "lidar", "radar", "imu", "gnss"] = Field(description="Sensor modality.")
    model: str = Field(default="", description="Sensor model / driver identifier.")
    topic: str = Field(default="", description="Data topic (middleware-dependent).")
    mount: Dict[str, float] = Field(
        default_factory=lambda: {"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
        description="Extrinsics relative to the vehicle frame (x/y/z in m, roll/pitch/yaw in rad).",
    )
    fps: float = Field(default=20.0, description="Native sensor rate (Hz).")
    sync_source: Literal["pps", "gptp", "ntp", "software"] = Field(
        default="software", description="Time-sync source; a single master clock is required."
    )


class PerceptionConfig(_Config):
    backend: Literal["offline", "enhanced", "onnx"] = Field(
        default="offline",
        description="Detection backend: offline (YOLO11s) | enhanced (YOLO11x + ROI) | onnx (ONNX Runtime).",
    )
    conf: float = Field(default=0.4, description="Detection confidence threshold (full-frame pass).")
    modules: List[str] = Field(
        default_factory=lambda: ["detection", "tracking", "traffic_sign"],
        description="Enabled pipeline modules.",
    )
    roi: Dict[str, float] = Field(
        default_factory=lambda: {"forward_m": 60.0, "lateral_m": 15.0},
        description="Region of interest around the ego vehicle (meters).",
    )
    small_target_enhance: bool = Field(default=False, description="Small-target re-inference (enhanced backend).")


class OutputConfig(_Config):
    frame_id: str = Field(default="base_link", description="Coordinate frame for published objects.")
    rate_hz: float = Field(default=10.0, description="Perception loop rate (Hz).")


class SafetyConfig(_Config):
    min_obstacle_height_m: float = Field(default=0.05, description="Minimum obstacle height to consider (m).")
    max_detection_latency_ms: float = Field(default=100.0, description="Latency ceiling (ms); violations flagged.")


class DataConfig(_Config):
    frames_dir: str = Field(default="data/frames", description="Directory of replay frames (demo/CI source).")
    index_path: Optional[str] = Field(default=None, description="Frame index CSV; optional.")


class RobotConfig(_Config):
    schema_version: str = Field(default="1.0", description="Manifest schema version.")
    vehicle: VehicleConfig = Field(description="Vehicle description.")
    domain_controller: DomainControllerConfig = Field(default_factory=DomainControllerConfig, description="Onboard compute.")
    sensors: List[SensorConfig] = Field(default_factory=list, description="Sensor suite (camera/lidar/...).")
    perception: PerceptionConfig = Field(default_factory=PerceptionConfig, description="Perception configuration.")
    output: OutputConfig = Field(default_factory=OutputConfig, description="Output / publish configuration.")
    safety: SafetyConfig = Field(default_factory=SafetyConfig, description="Safety bounds.")
    data: DataConfig = Field(default_factory=DataConfig, description="Replay data source.")


def load_config(path: str) -> RobotConfig:
    """Load and structurally validate a manifest YAML file."""
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return RobotConfig.model_validate(raw)
