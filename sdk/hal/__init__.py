"""Hardware abstraction layer — plugin seams for sensors, inference, and middleware."""
from sdk.hal.base import BackendInfo, HealthReport, MiddlewareConfig, ModelConfig
from sdk.hal.middleware import IMiddlewareAdapter, JsonLineMiddlewareAdapter
from sdk.hal.sensor import ISensorAdapter, ReplaySensorAdapter

__all__ = [
    "BackendInfo",
    "HealthReport",
    "MiddlewareConfig",
    "ModelConfig",
    "IMiddlewareAdapter",
    "JsonLineMiddlewareAdapter",
    "ISensorAdapter",
    "ReplaySensorAdapter",
]
