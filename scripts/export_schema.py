"""Export JSON Schemas for the standardized output + config data models.

`PerceptionFrame` is the product contract (aligned with ASAM OpenLABEL /
ISO 23150). Pydantic's `model_json_schema()` is the single source of truth, so
downstream integrators can code against a stable, language-neutral contract
without depending on the Python runtime.

Usage:
    python scripts/export_schema.py [out_dir]
Defaults:
    out_dir = docs/schema
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sdk.config import RobotConfig
from sdk.output.frame import PerceptionFrame


def main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/schema")
    out_dir.mkdir(parents=True, exist_ok=True)

    artifacts = {
        "perception_frame.schema.json": PerceptionFrame.model_json_schema(),
        "robot_config.schema.json": RobotConfig.model_json_schema(),
    }
    for name, schema in artifacts.items():
        path = out_dir / name
        path.write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {path}")

    print("schemas are JSON Schema (OpenAPI-compatible); regenerate after model changes.")


if __name__ == "__main__":
    main()
