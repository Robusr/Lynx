"""Deployment preflight validation (the "on-board self-check").

Semantic checks that go beyond structural (pydantic) validation: time-sync
topology, extrinsics coverage, FOV, resource budget, safety bounds. Errors block
startup; warnings require explicit confirmation; passes are informational.

This is a demo-grade subset — the production validator grows along the same seams.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from sdk.config import RobotConfig


@dataclass
class Check:
    name: str
    severity: str  # "error" | "warn" | "pass"
    message: str


def validate(cfg: RobotConfig) -> List[Check]:
    return [
        _check_time_sync(cfg),
        _check_extrinsics(cfg),
        _check_fov(cfg),
        _check_resource(cfg),
        _check_safety(cfg),
    ]


def _check_time_sync(cfg: RobotConfig) -> Check:
    sensors = cfg.sensors
    if not sensors:
        return Check("time_sync", "warn", "no sensors declared")
    sources = {s.sync_source for s in sensors}
    if len(sources) > 1 and "software" in sources:
        return Check(
            "time_sync", "warn", f"mixed sync sources {sources}; ensure a single master clock"
        )
    return Check("time_sync", "pass", f"sync sources: {sorted(sources)}")


def _check_extrinsics(cfg: RobotConfig) -> Check:
    missing = [s.name for s in cfg.sensors if not s.mount]
    if missing:
        return Check("extrinsics", "error", f"sensors missing mount (extrinsics): {missing}")
    return Check("extrinsics", "pass", f"{len(cfg.sensors)} sensor(s) with mount defined")


def _check_fov(cfg: RobotConfig) -> Check:
    roi = cfg.perception.roi
    forward = roi.get("forward_m", 0.0)
    if forward <= 0:
        return Check("fov", "error", "perception.roi.forward_m must be > 0")
    return Check("fov", "pass", f"ROI forward {forward}m, lateral {roi.get('lateral_m', 0)}m")


# Coarse budget heuristic (not a profiled number): the enhanced backend runs
# YOLO11x plus a second ROI pass, so it is heavy. OfflineBackend's docstring
# documents it as the fleet/fallback backend for exactly this reason — embedded
# controllers are unlikely to hold enhanced at demo latency. A full version maps
# measured FLOPs/VRAM against the controller budget.
_HEAVY_BACKENDS = {"enhanced"}
_EMBEDDED_CONTROLLERS = {"jetson_orin_nano", "rk3588"}


def _check_resource(cfg: RobotConfig) -> Check:
    backend = cfg.perception.backend
    controller = cfg.domain_controller.model
    if backend in _HEAVY_BACKENDS and controller in _EMBEDDED_CONTROLLERS:
        return Check(
            "resource",
            "warn",
            f"backend={backend} (YOLO11x + ROI) on {controller} may exceed the "
            f"compute budget; prefer offline/onnx",
        )
    return Check(
        "resource",
        "pass",
        f"backend={backend}, controller={controller}, "
        f"inference={cfg.domain_controller.inference_backend}",
    )


def _check_safety(cfg: RobotConfig) -> Check:
    issues = []
    if cfg.vehicle.max_speed_ms <= 0:
        issues.append("vehicle.max_speed_ms <= 0")
    if cfg.safety.max_detection_latency_ms <= 0:
        issues.append("safety.max_detection_latency_ms <= 0")
    if issues:
        return Check("safety", "error", "; ".join(issues))
    return Check("safety", "pass", "safety parameters within bounds")


def summarize(checks: List[Check]) -> str:
    errors = [c for c in checks if c.severity == "error"]
    warns = [c for c in checks if c.severity == "warn"]
    lines = []
    for c in checks:
        icon = {"error": "✗", "warn": "!", "pass": "✓"}[c.severity]
        lines.append(f"  [{icon}] {c.name:<12} {c.message}")
    header = f"preflight: {len(errors)} error(s), {len(warns)} warning(s)"
    return header + "\n" + "\n".join(lines)
