"""Preflight validator tests: semantic checks beyond pydantic structure."""
from sdk.config import (
    PerceptionConfig,
    RobotConfig,
    SafetyConfig,
    SensorConfig,
    VehicleConfig,
)
from sdk.validate import validate


def _make_cfg() -> RobotConfig:
    return RobotConfig(
        vehicle=VehicleConfig(name="demo", max_speed_ms=5.0),
        sensors=[
            SensorConfig(
                name="front_cam",
                type="camera",
                interface="usb",
                mount={"x": 0, "y": 0, "z": 1.4, "roll": 0, "pitch": 0, "yaw": 0},
            )
        ],
        perception=PerceptionConfig(backend="offline", roi={"forward_m": 60, "lateral_m": 15}),
        safety=SafetyConfig(min_obstacle_height_m=0.05, max_detection_latency_ms=100),
    )


def test_valid_config_has_no_errors():
    checks = validate(_make_cfg())
    assert not any(c.severity == "error" for c in checks)


def test_missing_extrinsics_is_error():
    cfg = _make_cfg()
    cfg.sensors[0].mount = {}
    checks = validate(cfg)
    assert any(c.name == "extrinsics" and c.severity == "error" for c in checks)


def test_zero_roi_forward_is_error():
    cfg = _make_cfg()
    cfg.perception.roi["forward_m"] = 0
    checks = validate(cfg)
    assert any(c.name == "fov" and c.severity == "error" for c in checks)


def test_zero_max_speed_is_error():
    cfg = _make_cfg()
    cfg.vehicle.max_speed_ms = 0
    checks = validate(cfg)
    assert any(c.name == "safety" and c.severity == "error" for c in checks)
