"""Configuration schema + loader for the single-source-of-truth manifest.

`robot.demo.yaml` is the only hand-written deployment file; everything else is
generated or validated from it (see sdk.validate). Pydantic gives structural
validation for free.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import yaml
from pydantic import BaseModel, Field


class VehicleConfig(BaseModel):
    name: str
    type: str = "ackermann"
    max_speed_ms: float = 5.0


class DomainControllerConfig(BaseModel):
    model: str = "laptop"
    inference_backend: str = "onnx_cpu"  # onnx_cpu | onnx_cuda | tensorrt | onnx_acl | onnx_coreml


class SensorConfig(BaseModel):
    name: str
    type: str  # camera | lidar | radar | imu | gnss
    model: str = ""
    topic: str = ""
    mount: Dict[str, float] = Field(
        default_factory=lambda: {"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0}
    )
    fps: float = 20.0
    sync_source: str = "software"  # pps | gptp | ntp | software


class PerceptionConfig(BaseModel):
    backend: str = "offline"  # offline | enhanced | onnx
    conf: float = 0.4  # detection confidence threshold (primary/full-frame pass)
    modules: List[str] = Field(default_factory=lambda: ["detection", "tracking", "traffic_sign"])
    roi: Dict[str, float] = Field(
        default_factory=lambda: {"forward_m": 60.0, "lateral_m": 15.0}
    )
    small_target_enhance: bool = False


class OutputConfig(BaseModel):
    frame_id: str = "base_link"
    rate_hz: float = 10.0


class SafetyConfig(BaseModel):
    min_obstacle_height_m: float = 0.05
    max_detection_latency_ms: float = 100.0


class DataConfig(BaseModel):
    frames_dir: str = "data/frames"
    index_path: Optional[str] = None


class RobotConfig(BaseModel):
    schema_version: str = "1.0"
    vehicle: VehicleConfig
    domain_controller: DomainControllerConfig = Field(default_factory=DomainControllerConfig)
    sensors: List[SensorConfig] = Field(default_factory=list)
    perception: PerceptionConfig = Field(default_factory=PerceptionConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    data: DataConfig = Field(default_factory=DataConfig)


def load_config(path: str) -> RobotConfig:
    """Load and structurally validate a manifest YAML file."""
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return RobotConfig.model_validate(raw)
