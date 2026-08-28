<h1 align="center">Lynx</h1>

<p align="center">
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/License-Apache_2.0-blue.svg"></a>
  <a href="https://www.python.org/"><img alt="Python" src="https://img.shields.io/badge/Python-3.11%2B-3776AB.svg?logo=python&logoColor=white"></a>
  <a href="pyproject.toml"><img alt="Version" src="https://img.shields.io/badge/Version-0.1.0-lightgrey.svg"></a>
  <a href="https://docs.pydantic.dev/"><img alt="Pydantic" src="https://img.shields.io/badge/Pydantic-2.x-E92063.svg?logo=pydantic&logoColor=white"></a>
</p>

<p align="center">
  <a href="README.md">English</a> | <a href="README.zh-CN.md">简体中文</a>
</p>

<p align="center">
  <em>Hardware-agnostic perception-fusion SDK for low-speed autonomous vehicles in
  enclosed sites (factories, ports, campuses, and parks). One SDK, three inference
  backends, one standardized output.</em>
</p>

This repository is the **walking skeleton**: a vertical slice through every layer
of the product, built to be hardened into the production SDK rather than thrown
away after the demo.

## Table of contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Repository layout](#repository-layout)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Data model](#data-model)
- [Backends](#backends)
- [Hardware abstraction layer](#hardware-abstraction-layer)
- [Validation gate](#validation-gate)
- [Demo server](#demo-server)
- [VS Code extension](#vs-code-extension)
- [Development](#development)
- [License](#license)
- [Documentation](#documentation)

## Overview

Lynx turns raw sensor frames into a standardized `PerceptionFrame` (detected and
tracked objects plus traffic signs) behind a hardware-agnostic plugin interface.
The core pipeline never changes when a sensor, a domain controller, or a
middleware transport is swapped — only an adapter plugin is added.

- A single config manifest is the **single source of truth**; every artifact
  (JSON Schema, validation report, backend selection, output frame) is generated
  or validated from it.
- The output data model aligns with ASAM OpenLABEL / ISO 23150 conventions.
- Deployment safety is enforced by a **preflight gate** of seven semantic checks.

## Features

- **Hardware-agnostic HAL** — `ISensorAdapter`, `IInferenceBackend`, and
  `IMiddlewareAdapter` plugin seams with demo implementations.
- **Single source of truth** — one Pydantic model (`sdk/config.py`) drives the
  JSON Schema, the config form, the validator, and runtime behavior.
- **Preflight validation gate** — seven deployment checks (time-sync, extrinsics,
  interface contract, bandwidth, FOV, resource, safety).
- **Three inference backends** — offline (YOLO11s), enhanced (YOLO11x + ROI
  re-inference), and ONNX Runtime (pluggable execution providers).
- **Standardized output** — `PerceptionFrame` with `ObjectType` / `SignType` /
  `SourceMask` enums, derived fields, 2D/3D boxes, tracks, and traffic signs.
- **Camera-to-LiDAR late fusion** — IoU association between projected 3D boxes and
  camera 2D boxes.
- **In-process telemetry** — latency percentiles, throughput, and per-source counts.
- **FastAPI demo server** and a schema-driven **VS Code extension**.

## Architecture

<p align="center">
  <img src="docs/architecture.png" alt="Lynx architecture" width="520">
</p>

The two ends of the pipeline are plugin seams:

- `ISensorAdapter` (`sdk/hal/sensor.py`) feeds time-aligned `FrameBatch` objects
  into the pipeline. The demo ships `ReplaySensorAdapter`, which plays recorded
  frames back like a live camera driver.
- `IMiddlewareAdapter` (`sdk/hal/middleware.py`) publishes each `PerceptionFrame`
  to any transport. The demo ships `JsonLineMiddlewareAdapter` (NDJSON).

## Repository layout

```
config/robot.demo.yaml     single source of truth manifest
sdk/                       the SDK (no FastAPI or UI here)
  config.py                schema + loader
  validate.py              deployment preflight checks (7) + to_report()
  geometry.py              IoU / NMS / merge
  output/frame.py          PerceptionFrame and the product data model
  backend/                 IBackend + offline + enhanced + onnx
  input/replay_reader.py   FrameBatch + replay data source
  hal/                     ISensorAdapter / IMiddlewareAdapter + demo adapters
  fusion/                  tracker, camera-lidar late fusion, synthetic lidar
  camera.py                pinhole model (3D <-> 2D bridge for fusion)
  metrics.py               in-process telemetry
  pipeline.py              run(): config -> validate -> detect -> track -> fuse -> emit
server.py                  FastAPI + WebSocket demo
dashboard/index.html       single-page dashboard
vscode-extension/          VS Code extension (config form + dashboard)
scripts/                   run / smoke / benchmark / config_io / export_* / make_demo_data ...
docs/schema/               generated JSON Schema (config + PerceptionFrame)
docs/architecture.png      pipeline architecture diagram
docs/images/               screenshots (config editor, dashboard, demo)
tests/                     contract + validator tests
```

## Quick start

Requires Python 3.11+ (ML backends recommend 3.11/3.12).

```bash
# 1. virtualenv
python3.12 -m venv .venv && source .venv/bin/activate

# 2. core deps (data model / config / validation / server)
pip install -r requirements.txt

# 3. ML deps (optional, for inference)
pip install -r requirements-ml.txt

# 4. demo frames (synthetic, no camera required)
python scripts/make_demo_data.py 240 data/frames

# 5. run
python scripts/run.py
# -> http://127.0.0.1:8000
```

Headless smoke test (no server, no UI):

```bash
python scripts/smoke.py config/robot.demo.yaml 5          # 5 frames
python scripts/smoke.py config/robot.demo.yaml 5 --jsonl  # publish NDJSON
```

Run the tests:

```bash
python -m pytest tests/
```

## Configuration

`config/robot.demo.yaml` is the only hand-written deployment file. Its keys map
1:1 to `sdk/config.py`, and it is the source of the JSON Schema that powers
editor IntelliSense and the VS Code config form.

```yaml
vehicle:                    # kinematic model + envelope
  name: "demo_factory_truck"
  type: "ackermann"         # diff_drive | ackermann | skid_steer | omni
  max_speed_ms: 5.0
  wheelbase_m: 1.8
  track_width_m: 1.4
  dimensions: { l: 2.4, w: 1.3, h: 1.9 }

domain_controller:          # onboard compute target
  vendor: "nvidia"
  model: "laptop"           # laptop | jetson_orin_nano | rk3588
  compute_tops: 0
  inference_backend: "onnx_cpu"
  os: "ubuntu_22.04"
  middleware: "custom"      # ros2_humble | ros2_iron | dds_rti | some_ip | custom

sensors:                    # one entry per sensor
  - name: "front_cam"
    type: "camera"
    interface: "usb"        # gige | ethernet | can | usb
    topic: "cam/front"
    mount: { x: 0.0, y: 0.0, z: 1.4, roll: 0, pitch: 0, yaw: 0 }
    fps: 20
    sync_source: "software"

perception:
  backend: "offline"        # offline | enhanced | onnx
  conf: 0.4
  modules: [detection, tracking, traffic_sign]
  roi: { forward_m: 60, lateral_m: 15 }
  small_target_enhance: true

calibration:                # contract fields, loaded by CalibStore (later milestone)
  camera_intrinsics: null
  extrinsics: null
  lidar_camera_extrinsic: null
  time_offset_ms: {}

safety:                     # @ai-lock - read-only
  min_braking_distance_m: 1.0
  min_obstacle_height_m: 0.05
  max_detection_latency_ms: 100
  redundant_fov_required: true

data:                       # replay source for the demo
  frames_dir: "data/frames"
  index_path: "data/index.csv"
```

AI-annotation conventions in the manifest:

- `@ai-lock` marks read-only blocks (e.g. `safety`) that tooling must not
  silently rewrite.
- `@ai-extend` marks extensible custom attributes.
- `@ai-telemetry` marks fields feeding the telemetry stream.

## Data model

The product contract is `PerceptionFrame` in `sdk/output/frame.py`, exported as a
JSON Schema in `docs/schema/perception_frame.schema.json`.

| Type | Description |
|---|---|
| `PerceptionFrame` | `stamp_ns`, `frame_id`, `seq`, `backend`, `objects`, `traffic_signs`, `latency_ms` |
| `Track` | `Detection` plus `track_id` and 3-D `velocity` |
| `TrafficSign` | `type`, `cls_name`, `text`, `bbox_2d/3d`, `confidence`, `stamp_ns` |
| `Detection` | `cls_id`, `cls_name`, `type`, `sub_type`, `bbox_2d/3d`, `confidence`, `source`, `occlusion_ratio`, `small_target_score`, `pose_covariance`, `attributes` |
| `BBox2D` / `BBox3D` | image-plane (x, y, w, h) and world/vehicle (x, y, z, l, w, h, yaw) boxes |

Enums:

- `ObjectType` — `pedestrian`, `bicycle`, `vehicle`, `truck`, `cone`, `barrier`,
  `traffic_sign`, `traffic_light`, `unknown`.
- `SignType` — `stop`, `speed_limit`, `yield`, `no_entry`, `traffic_light`,
  `unknown`.
- `SourceMask` (`IntFlag`) — `CAMERA=1`, `LIDAR=2`, `RADAR=4`; fusion is the
  bitwise OR (e.g. `CAMERA | LIDAR = 3`). `source_label()` renders a human label.

Derived fields are filled automatically by Pydantic validators: `type` is derived
from `cls_name` (e.g. `person` -> `pedestrian`), and `sub_type` carries the fine
class. `pose_covariance` is a 6x6 row-major list (empty when unknown);
`attributes` holds `@ai-extend` custom data.

## Backends

All backends implement the same `IBackend` interface (`init`, `detect`, `info`,
`release`) and are selected with `perception.backend`.

| Backend | Model | Notes |
|---|---|---|
| `offline` | YOLO11s | Single full-frame pass, CPU-friendly. Deployed fleet default. |
| `enhanced` | YOLO11x + YOLO11s ROI | Full-frame pass plus a distant-band ROI re-inference for small targets (`small_target_enhance`). |
| `onnx` | YOLO11s ONNX | ONNX Runtime with a pluggable execution provider (`domain_controller.inference_backend`). |

The ONNX backend is the hardware-agnostic path: the same `.onnx` graph runs on
CPU, CUDA, TensorRT, ARM ACL, or CoreML without changing the SDK code path.

## Hardware abstraction layer

`sdk/hal/` defines the plugin seams that make the SDK hardware-agnostic.

- `ISensorAdapter` — `init`, `start`, `stop`, `grab`, `health`. Pull-mode is the
  default so streams stay deterministic and replayable. `ReplaySensorAdapter`
  plays recorded frames behind the same interface a live driver would.
- `IInferenceBackend` — the inference seam (aliased as `IBackend`). Exposes
  `info()` returning `BackendInfo` (name, model, device, telemetry).
- `IMiddlewareAdapter` — `init`, `publish`, `subscribe`, `stop`. Shields ROS2 /
  DDS / SOME-IP / private-bus differences. `JsonLineMiddlewareAdapter` publishes
  one JSON object per line.

## Validation gate

`sdk/validate.py` runs seven semantic checks before the pipeline starts, ordered
per the technical-architecture document. `to_report()` renders a JSON report and
`scripts/validate_json.py --out preflight_report.json` writes it to disk.

| Check | Purpose |
|---|---|
| `time_sync` | single master clock across sensors |
| `extrinsics` | every sensor declares a `mount` |
| `interface` | sensor type -> physical interface contract |
| `bandwidth` | aggregate per-type data rate vs. budget |
| `fov` | ROI is non-zero; redundant forward coverage when required |
| `resource` | backend vs. controller compute budget |
| `safety` | speed, latency, and braking-distance bounds |

## Demo server

`server.py` exposes a FastAPI application that runs the pipeline in a daemon
thread and streams the latest frame.

| Endpoint | Description |
|---|---|
| `GET /` | single-page dashboard |
| `WS /ws` | streams `{ frame, image }` (image is base64 JPEG) |
| `GET /api/state` | backend + liveness |
| `GET /api/metrics` | runtime telemetry |
| `POST /api/switch` | switch `offline` / `enhanced` / `onnx` at runtime |

## VS Code extension

`vscode-extension/` provides:

- **Config form** — a schema-driven webview form for editing the manifest, with
  live preflight validation and `@ai-lock` sections rendered read-only.
- **Dashboard** — a webview panel for live backend switching and status.

### Screenshots

<p align="center">
  <img src="docs/images/config-editor.png" alt="Config editor" width="300">
  <img src="docs/images/status-dashboard.png" alt="Status dashboard" width="480">
</p>

<p align="center">
  <img src="docs/images/dashboard-demo.gif" alt="Dashboard demo" width="540">
</p>

## Development

```bash
python scripts/export_schema.py docs/schema    # regenerate JSON Schema
python scripts/validate_json.py config/robot.demo.yaml --out preflight_report.json
python scripts/config_io.py get config/robot.demo.yaml       # config -> JSON
python scripts/config_io.py set config/robot.demo.yaml       # JSON -> config (stdin)
python -m pytest tests/                                      # 18 tests
```

The SDK is installable as `pip install -e .` with extras `.[ml]`, `.[server]`,
and `.[dev]`. `pyproject.toml` is the single packaging source. Commit messages
follow Conventional Commits and are written in English.

## License

Apache-2.0. See [LICENSE](LICENSE).
