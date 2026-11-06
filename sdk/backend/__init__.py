"""Inference backends plus the factory registry used by the pipeline.

Third-party backends register with `register_backend(name, factory)` and become
selectable from `perception.backend` without editing the pipeline.
"""
from __future__ import annotations

from typing import Callable, Dict

from sdk.backend.base import IBackend, IInferenceBackend
from sdk.backend.enhanced import EnhancedBackend
from sdk.backend.offline import OfflineBackend
from sdk.backend.onnx import OnnxBackend
from sdk.config import RobotConfig

BackendFactory = Callable[[RobotConfig], IBackend]

_FACTORIES: Dict[str, BackendFactory] = {}


def register_backend(name: str, factory: BackendFactory) -> None:
    """Register or replace a backend factory."""
    _FACTORIES[name] = factory


def backend_factory(name: str) -> BackendFactory:
    try:
        return _FACTORIES[name]
    except KeyError as exc:
        known = ", ".join(sorted(_FACTORIES))
        raise KeyError(f"unknown backend {name!r}; registered: {known}") from exc


def inference_device(cfg: RobotConfig) -> str:
    """Map the configured execution provider to an ultralytics device string."""
    return {
        "onnx_cpu": "cpu",
        "onnx_cuda": "cuda",
        "tensorrt": "cuda",
        "onnx_acl": "cpu",
        "onnx_coreml": "cpu",
    }.get(cfg.domain_controller.inference_backend, "cpu")


def _offline(cfg: RobotConfig) -> IBackend:
    return OfflineBackend(conf=cfg.perception.conf, device=inference_device(cfg))


def _enhanced(cfg: RobotConfig) -> IBackend:
    return EnhancedBackend(
        conf=cfg.perception.conf,
        device=inference_device(cfg),
        small_target_enhance=cfg.perception.small_target_enhance,
    )


def _onnx(cfg: RobotConfig) -> IBackend:
    return OnnxBackend(conf=cfg.perception.conf)


register_backend("offline", _offline)
register_backend("enhanced", _enhanced)
register_backend("onnx", _onnx)


def build_backend(cfg: RobotConfig) -> IBackend:
    """Construct the backend selected by `perception.backend`."""
    return backend_factory(cfg.perception.backend)(cfg)


__all__ = [
    "BackendFactory",
    "IBackend",
    "IInferenceBackend",
    "OfflineBackend",
    "EnhancedBackend",
    "OnnxBackend",
    "backend_factory",
    "build_backend",
    "inference_device",
    "register_backend",
]
