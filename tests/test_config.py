"""Manifest model tests: bounds, uniqueness, schema version, path resolution."""
from pathlib import Path

import pytest
from pydantic import ValidationError

from sdk.config import RobotConfig, load_config

REPO = Path(__file__).resolve().parents[1]


def _raw() -> dict:
    return {
        "schema_version": "1.0",
        "vehicle": {"name": "demo"},
        "sensors": [
            {
                "name": "cam",
                "type": "camera",
                "interface": "usb",
                "mount": {"x": 0, "y": 0, "z": 1, "roll": 0, "pitch": 0, "yaw": 0},
            }
        ],
        "perception": {
            "modules": ["detection"],
            "roi": {"forward_m": 10, "lateral_m": 5},
        },
        "safety": {"redundant_fov_required": False},
    }


def test_demo_config_loads_and_resolves_paths():
    cfg = load_config(str(REPO / "config" / "robot.demo.yaml"))
    assert cfg.data.frames_dir == "../data/frames"
    assert cfg.resolve(cfg.data.frames_dir) == str((REPO / "data" / "frames").resolve())
    assert cfg.perception.roi.forward_m == 60
    assert cfg.sensors[0].mount is not None


def test_manifest_relative_path_resolution(tmp_path: Path):
    path = tmp_path / "robot.yaml"
    raw = _raw()
    raw["data"] = {"frames_dir": "frames"}
    path.write_text(__import__("yaml").safe_dump(raw), encoding="utf-8")
    cfg = load_config(str(path))
    assert cfg.resolve(cfg.data.frames_dir) == str((tmp_path / "frames").resolve())


def test_unknown_key_is_rejected():
    raw = _raw()
    raw["typo"] = 1
    with pytest.raises(ValidationError):
        RobotConfig.model_validate(raw)


def test_duplicate_sensor_names_are_rejected():
    raw = _raw()
    raw["sensors"].append(dict(raw["sensors"][0]))
    with pytest.raises(ValidationError):
        RobotConfig.model_validate(raw)


def test_modules_must_include_detection():
    raw = _raw()
    raw["perception"]["modules"] = ["tracking"]
    with pytest.raises(ValidationError):
        RobotConfig.model_validate(raw)


def test_confidence_must_be_within_unit_interval():
    raw = _raw()
    raw["perception"]["conf"] = 1.5
    with pytest.raises(ValidationError):
        RobotConfig.model_validate(raw)


def test_mount_is_optional_at_the_model_level():
    raw = _raw()
    del raw["sensors"][0]["mount"]
    cfg = RobotConfig.model_validate(raw)
    assert cfg.sensors[0].mount is None


def test_schema_version_must_be_one_x():
    raw = _raw()
    raw["schema_version"] = "2.0"
    with pytest.raises(ValidationError):
        RobotConfig.model_validate(raw)
