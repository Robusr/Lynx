"""Configuration schema + loader for the single-source-of-truth manifest.

`robot.demo.yaml` is the only hand-written deployment file; everything else is
generated or validated from it (see sdk.validate). Pydantic gives structural
validation for free, and this model doubles as the JSON-Schema source for editor
IntelliSense (scripts/export_schema.py): `Literal[...]` becomes an enum dropdown,
`Field(description=...)` becomes hover docs, and `extra="forbid"` flags typos.

Relative paths in the manifest are resolved against the manifest's own directory
via `RobotConfig.resolve()`, so the SDK can be started from any working directory.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator


class _Config(BaseModel):
    """Shared base: forbid undeclared keys so YAML typos fail loudly."""

    model_config = ConfigDict(extra="forbid")


class MountConfig(_Config):
    """Sensor extrinsics relative to the vehicle frame."""

    x: float = Field(default=0.0, description="Forward offset from the vehicle frame in m.")
    y: float = Field(default=0.0, description="Left offset from the vehicle frame in m.")
    z: float = Field(default=0.0, description="Up offset from the vehicle frame in m.")
    roll: float = Field(default=0.0, description="Roll in rad.")
    pitch: float = Field(default=0.0, description="Pitch in rad.")
    yaw: float = Field(default=0.0, description="Yaw in rad; 0 points forward.")


class DimensionsConfig(_Config):
    """Vehicle envelope in metres."""

    l: float = Field(default=2.4, gt=0.0, description="Length in m.")  # noqa: E741
    w: float = Field(default=1.3, gt=0.0, description="Width in m.")
    h: float = Field(default=1.9, gt=0.0, description="Height in m.")


class ROIConfig(_Config):
    """Region of interest around the ego vehicle."""

    forward_m: float = Field(default=60.0, gt=0.0, description="Forward range in m; must be > 0.")
    lateral_m: float = Field(default=15.0, gt=0.0, description="Half-width in m; must be > 0.")


class VehicleConfig(_Config):
    name: str = Field(description="Vehicle identifier, e.g. 'demo_factory_truck'.")
    type: Literal["diff_drive", "ackermann", "skid_steer", "omni"] = Field(
        default="ackermann", description="Kinematic model."
    )
    max_speed_ms: float = Field(default=5.0, description="Speed ceiling in m/s; safety checks reject <= 0.")
    wheelbase_m: float = Field(default=1.8, description="Wheelbase in m (geometry; no runtime consumer yet).")
    track_width_m: float = Field(default=1.4, description="Track width in m (geometry; no runtime consumer yet).")
    dimensions: DimensionsConfig = Field(
        default_factory=DimensionsConfig,
        description="Vehicle envelope l/w/h in m (geometry; no runtime consumer yet).",
    )


class DomainControllerConfig(_Config):
    vendor: Literal["nvidia", "horizon", "ti", "qualcomm", "blacksesame", "rockchip"] = Field(
        default="nvidia", description="Chip vendor (drives resource/consistency checks)."
    )
    model: Literal["laptop", "jetson_orin_nano", "rk3588"] = Field(
        default="laptop", description="Onboard compute target (drives resource-budget checks)."
    )
    compute_tops: float = Field(default=0.0, ge=0.0, description="INT8 TOPS, advisory for the resource budget (0 = unspecified).")
    inference_backend: Literal["onnx_cpu", "onnx_cuda", "tensorrt", "onnx_acl", "onnx_coreml"] = Field(
        default="onnx_cpu", description="Inference execution provider for the ONNX backend."
    )
    os: str = Field(default="ubuntu_22.04", description="Controller OS image.")
    middleware: Literal["ros2_humble", "ros2_iron", "dds_rti", "some_ip", "custom"] = Field(
        default="custom", description="Middleware transport (feeds IMiddlewareAdapter)."
    )


class SensorConfig(_Config):
    name: str = Field(description="Sensor name (must be unique).")
    type: Literal["camera", "lidar", "radar", "imu", "gnss"] = Field(description="Sensor modality.")
    model: str = Field(default="", description="Sensor model / driver identifier.")
    interface: Literal["gige", "ethernet", "can", "usb"] = Field(
        default="ethernet", description="Physical interface (drives the interface-contract check)."
    )
    topic: str = Field(default="", description="Data topic (middleware-dependent).")
    mount: Optional[MountConfig] = Field(
        default=None,
        description="Extrinsics relative to the vehicle frame; required by the preflight gate.",
    )
    fps: float = Field(default=20.0, gt=0.0, description="Native sensor rate (Hz).")
    sync_source: Literal["pps", "gptp", "ntp", "software"] = Field(
        default="software", description="Time-sync source; a single master clock is required."
    )


PipelineModule = Literal["detection", "tracking", "traffic_sign"]
DEFAULT_MODULES: List[PipelineModule] = ["detection", "tracking", "traffic_sign"]


class PerceptionConfig(_Config):
    backend: Literal["offline", "enhanced", "onnx"] = Field(
        default="offline",
        description="Detection backend: offline (YOLO11s) | enhanced (YOLO11x + ROI) | onnx (ONNX Runtime).",
    )
    conf: float = Field(default=0.4, ge=0.0, le=1.0, description="Detection confidence threshold (full-frame pass).")
    modules: List[PipelineModule] = Field(
        default_factory=lambda: list(DEFAULT_MODULES),
        min_length=1,
        description="Enabled pipeline modules; 'detection' is required.",
    )
    roi: ROIConfig = Field(
        default_factory=ROIConfig,
        description="Region of interest around the ego vehicle (meters).",
    )
    small_target_enhance: bool = Field(
        default=True,
        description="Small-target ROI re-inference pass (enhanced backend only; ignored by offline/onnx).",
    )


class OutputConfig(_Config):
    frame_id: str = Field(default="base_link", description="Coordinate frame for published objects.")
    rate_hz: float = Field(default=10.0, gt=0.0, description="Perception loop rate (Hz).")


class SafetyConfig(_Config):
    min_braking_distance_m: float = Field(default=1.0, description="Minimum braking distance (m); must be > 0.")
    min_obstacle_height_m: float = Field(default=0.05, description="Minimum obstacle height to consider (m).")
    max_detection_latency_ms: float = Field(default=100.0, description="Latency ceiling (ms); violations flagged per frame.")
    redundant_fov_required: bool = Field(default=True, description="Require redundant forward FOV coverage.")


class DataConfig(_Config):
    frames_dir: str = Field(default="data/frames", description="Directory of replay frames (demo/CI source).")
    index_path: Optional[str] = Field(default=None, description="Frame index CSV; optional.")


class CalibrationConfig(_Config):
    """Calibration artifacts (intrinsics/extrinsics/time-offset) for CalibStore.

    Paths are contract fields; the CalibStore loader (and ISensorAdapter.init's
    `calib` argument) is a later milestone. The preflight gate verifies that any
    declared file exists, so a manifest cannot silently reference missing data.
    """
    camera_intrinsics: Optional[str] = Field(default=None, description="Per-camera intrinsic calibration file.")
    extrinsics: Optional[str] = Field(default=None, description="Sensor extrinsics file (merged with mount).")
    lidar_camera_extrinsic: Optional[str] = Field(default=None, description="Lidar↔camera extrinsic file.")
    time_offset_ms: Dict[str, float] = Field(
        default_factory=dict, description="Per-sensor time offset in ms (sync compensation)."
    )


class RobotConfig(_Config):
    schema_version: str = Field(default="1.0", description="Manifest schema version.")
    vehicle: VehicleConfig = Field(description="Vehicle description.")
    domain_controller: DomainControllerConfig = Field(default_factory=DomainControllerConfig, description="Onboard compute.")
    sensors: List[SensorConfig] = Field(default_factory=list, description="Sensor suite (camera/lidar/...).")
    perception: PerceptionConfig = Field(default_factory=PerceptionConfig, description="Perception configuration.")
    output: OutputConfig = Field(default_factory=OutputConfig, description="Output / publish configuration.")
    calibration: CalibrationConfig = Field(default_factory=CalibrationConfig, description="Calibration artifacts.")
    safety: SafetyConfig = Field(default_factory=SafetyConfig, description="Safety bounds.")
    data: DataConfig = Field(default_factory=DataConfig, description="Replay data source.")

    _base_dir: Path = PrivateAttr(default_factory=Path.cwd)

    def resolve(self, path: Optional[str]) -> Optional[str]:
        """Resolve a manifest-relative path against the manifest directory."""
        if not path:
            return path
        candidate = Path(path)
        if candidate.is_absolute():
            return str(candidate)
        return str((self._base_dir / candidate).resolve())

    @model_validator(mode="after")
    def _validate_manifest(self) -> "RobotConfig":
        if not self.schema_version.startswith("1."):
            raise ValueError(
                f"unsupported schema_version {self.schema_version!r}; this SDK supports 1.x"
            )
        names = [s.name for s in self.sensors]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"duplicate sensor name(s): {duplicates}")
        if "detection" not in self.perception.modules:
            raise ValueError("perception.modules must include 'detection'")
        return self


def load_config(path: str) -> RobotConfig:
    """Load and structurally validate a manifest YAML file."""
    config_path = Path(path).resolve()
    with config_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    cfg = RobotConfig.model_validate(raw)
    cfg._base_dir = config_path.parent
    return cfg
