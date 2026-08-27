# Lynx — 低速封闭园区无人车感知融合算法 SDK

Hardware-agnostic perception-fusion SDK for low-speed autonomous vehicles in
enclosed parks (厂区 / 港口 / 园区 / 校园). One SDK, two backends, one
standardized output.

This repository is the **walking skeleton**: a vertical slice through every
layer of the product, designed to be hardened into the real SDK rather than
thrown away after the roadshow.

## What it does

- Reads a single config manifest (`config/robot.demo.yaml`) — the only
  hand-written deployment file; everything else is generated or validated from it.
- Runs the perception loop: **preflight → backend → tracking → standardized output**.
- Streams results to a browser dashboard over WebSocket (camera overlay + BEV).
- Switches between the two backends at runtime with one HTTP call.

```
config ──▶ sdk.config ──▶ sdk.validate ──▶ sdk.backend ──▶ sdk.fusion ──▶ sdk.output
 (YAML)      (pydantic)     (semantic)      (offline/       (tracker)      (PerceptionFrame)
                                             enhanced)                      → FastAPI → dashboard
```

## Repo layout

```
config/robot.demo.yaml   single source of truth manifest
sdk/                     the SDK (no FastAPI/UI here)
  config.py              schema + loader
  validate.py            deployment preflight checks
  geometry.py            IoU / NMS / merge (dependency-light)
  output/frame.py        PerceptionFrame — the product contract
  backend/               IBackend + offline + enhanced (+ lazy YOLO glue)
  input/replay_reader.py replay data source
  fusion/tracker.py      SORT-lite tracker
  pipeline.py            run(): config → validate → detect → track → emit
server.py                FastAPI + WebSocket demo
dashboard/index.html     single-page dashboard
scripts/                 run / smoke / make_demo_data / make_index / frames_to_video / export_models / export_schema
docs/schema/             generated JSON Schema (PerceptionFrame + config)
tests/                   contract + validator tests
```

## Quickstart

```bash
# 1. Python 3.11/3.12 virtualenv (ultralytics/onnxruntime need it)
python3.12 -m venv .venv && source .venv/bin/activate

# 2. Core deps (data model / config / validation / server — no ML)
pip install -r requirements.txt

# 3. (Optional, for inference) ML deps + models
pip install -r requirements-ml.txt
python scripts/export_models.py yolo11s.pt          # or just download yolo11s.pt

# 4. Generate synthetic demo frames (no camera needed) — or drop your own
#    images into data/frames/ and index them instead
python scripts/make_demo_data.py 240 data/frames
# python scripts/make_index.py data/frames data/index.csv   # only for your own frames

# 4b. (Optional) export the JSON Schema contract for downstream integrators
python scripts/export_schema.py docs/schema

# 5. Run
python scripts/run.py
# → http://127.0.0.1:8000
# LYNX_PORT=8001 python scripts/run.py   # if 8000 is taken
```

To exercise the SDK headlessly (no ML needed) while you collect frames:

```bash
python -m pytest tests/         # contract + validator tests
python - <<'PY'                 # preflight only
from sdk.config import load_config
from sdk.validate import validate, summarize
print(summarize(validate(load_config("config/robot.demo.yaml"))))
PY
```

## Configuration

Edit `config/robot.demo.yaml`. The keys map 1:1 to `sdk/config.py`. Backend is a
config-level switch:

```yaml
perception:
  backend: "offline"   # offline | enhanced
```

- **offline** — single YOLO11s pass, CPU-friendly. The deployed fleet default.
- **enhanced** — YOLO11x full-frame + ROI re-inference (distant band upscale +
  merge) for small/distant targets. The AI large-model edition.

## Architecture notes

- **One interface, two backends** — `sdk.backend.base.IBackend` is the plugin
  seam; third-party / hardware-specific backends drop in without touching the
  pipeline.
- **Single source of truth** — config manifest drives validation, backend
  selection, output frame, and the dashboard.
- **Standardized output** — `PerceptionFrame` aligns with ASAM OpenLABEL /
  ISO 23150 conventions (2D + 3D boxes, track ids, velocity, occlusion,
  small-target score, traffic signs).
- **Hardware-agnostic inference** — ONNX Runtime with pluggable execution
  providers (CPU / CUDA / TensorRT / ARM ACL); the SDK code path never changes.
- **@ai-* annotations** in the config mark safety-critical, read-only blocks so
  AI agents (and future tooling) don't silently rewrite them.

## Demo caveats (not shipped in the SDK)

The dashboard's bird's-eye view estimates depth with the pinhole heuristic
`depth ≈ focal / bbox_height`. That lives only in `dashboard/index.html`; the
SDK itself emits 2D/3D boxes and never fabricates metric depth.

## Milestones

M0 scaffold → M1 offline loop → M2 enhanced + ROI re-inference → M3 dashboard →
M4 hardening (metrics, tests, packaging). See `05-demo-plan.md` in the product
docs for the full plan.
