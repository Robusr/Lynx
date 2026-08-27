"""Shared contract types for the HAL plugin seams.

Mirrors the C++ structs in 02-technical-architecture.md §3 so the Python demo
and the eventual C++ SDK keep identical shapes. These are passive dataclasses —
runtime plumbing, not the serialized product contract (that is
sdk.output.frame). HealthReport/BackendInfo feed @ai-telemetry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class HealthReport:
    """Sensor/backend health snapshot for @ai-telemetry."""

    status: str = "ok"  # "ok" | "degraded" | "error"
    message: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BackendInfo:
    """IInferenceBackend.info() — backend name, model, device, telemetry."""

    name: str
    model: str = ""
    device: str = ""
    version: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)  # latency/vram placeholders


@dataclass
class ModelConfig:
    """Model deployment spec — doc's ModelConfig (paths, precision, backend)."""

    weights: str = ""
    precision: str = "fp32"  # fp32 | fp16 | int8
    backend: str = ""  # e.g. "onnx_cpu", "tensorrt"


@dataclass
class MiddlewareConfig:
    """Publish/subscribe transport spec — doc's MiddlewareConfig."""

    middleware: str = "custom"  # ros2_humble | ros2_iron | dds_rti | some_ip | custom
    topic: str = ""
