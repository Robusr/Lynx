"""Hardware abstraction layer — plugin seams for sensors, inference, and middleware."""
from sdk.hal.base import BackendInfo, HealthReport, MiddlewareConfig, ModelConfig
from sdk.hal.middleware import (
    IMiddlewareAdapter,
    JsonLineMiddlewareAdapter,
    build_middleware,
    register_middleware,
)
from sdk.hal.sensor import (
    ISensorAdapter,
    ReplaySensorAdapter,
    build_sensor_adapter,
    register_sensor_adapter,
)

__all__ = [
    "BackendInfo",
    "HealthReport",
    "MiddlewareConfig",
    "ModelConfig",
    "IMiddlewareAdapter",
    "JsonLineMiddlewareAdapter",
    "ISensorAdapter",
    "ReplaySensorAdapter",
    "build_middleware",
    "build_sensor_adapter",
    "register_middleware",
    "register_sensor_adapter",
]
