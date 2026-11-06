"""Contract-level assertions for the standardized output frame."""
from sdk.output.frame import PerceptionFrame


def test_frame_schema_exposes_version_and_warnings():
    schema = PerceptionFrame.model_json_schema()
    assert "schema_version" in schema["properties"]
    assert "warnings" in schema["properties"]
    assert "velocity_px" in schema["$defs"]["Track"]["properties"]


def test_frame_dump_is_json_ready():
    frame = PerceptionFrame(stamp_ns=1, frame_id="base_link", warnings=["degraded"])
    dumped = frame.model_dump(mode="json")
    assert dumped["schema_version"] == "1.0"
    assert dumped["warnings"] == ["degraded"]
