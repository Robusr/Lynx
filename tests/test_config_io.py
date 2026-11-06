"""Config editor I/O tests: comment preservation, atomic writes, @ai-lock guard."""
from pathlib import Path

import pytest

from scripts import config_io
from sdk.config import load_config

YAML_TEXT = """# keep me
schema_version: "1.0"
vehicle:
  name: demo
sensors:
  - name: cam
    type: camera
    interface: usb
    mount: {x: 0, y: 0, z: 1, roll: 0, pitch: 0, yaw: 0}
safety:
  min_braking_distance_m: 1.0
"""


def _write(tmp_path: Path) -> Path:
    path = tmp_path / "robot.yaml"
    path.write_text(YAML_TEXT, encoding="utf-8")
    return path


def test_dump_preserves_comments(tmp_path):
    path = _write(tmp_path)
    cfg = load_config(str(path))
    text = config_io._dump_yaml(path, cfg)
    assert "# keep me" in text
    assert "schema_version" in text


def test_ai_lock_rejects_safety_changes(tmp_path):
    path = _write(tmp_path)
    cfg = load_config(str(path))
    cfg.safety.min_braking_distance_m = 2.0
    with pytest.raises(config_io.AiLockError):
        config_io._guard_ai_lock(path, cfg)


def test_atomic_write_replaces_file(tmp_path):
    path = tmp_path / "robot.yaml"
    config_io._atomic_write(path, "hello\n")
    assert path.read_text(encoding="utf-8") == "hello\n"
    assert not list(tmp_path.glob("robot.yaml.*"))
