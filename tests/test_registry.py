"""Plugin registry tests: backend lookup, middleware construction, NDJSON publish."""
import pytest

from sdk.backend import backend_factory
from sdk.hal.base import MiddlewareConfig
from sdk.hal.middleware import build_middleware
from sdk.output.frame import PerceptionFrame


def test_unknown_backend_lists_registered_names():
    with pytest.raises(KeyError, match="registered"):
        backend_factory("does-not-exist")


def test_unknown_middleware_is_explicit():
    with pytest.raises(NotImplementedError, match="registered"):
        build_middleware("ros2_humble", MiddlewareConfig(middleware="ros2_humble"))


def test_jsonline_middleware_publishes_one_json_object(capsys):
    adapter = build_middleware("custom", MiddlewareConfig(middleware="custom", topic="perception"))
    frame = PerceptionFrame(stamp_ns=1, frame_id="base_link", seq=7)
    assert adapter.publish(frame) is True
    line = capsys.readouterr().out.strip()
    assert line.startswith("{")
    assert '"stamp_ns": 1' in line
    assert '"seq": 7' in line
