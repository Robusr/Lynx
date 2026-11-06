"""Export JSON Schemas for the standardized output + config data models.

`PerceptionFrame` is the product contract (aligned with ASAM OpenLABEL /
ISO 23150). Pydantic's `model_json_schema()` is the single source of truth, so
downstream integrators can code against a stable, language-neutral contract
without depending on the Python runtime.

The generated config schema is also copied into the VS Code extension. `--check`
regenerates in memory and exits non-zero on drift, which is what CI runs.

Usage:
    python scripts/export_schema.py [out_dir]
    python scripts/export_schema.py --check
Defaults:
    out_dir = docs/schema
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from sdk.config import RobotConfig
from sdk.output.frame import PerceptionFrame

EXT_SCHEMA_DIR = REPO / "vscode-extension" / "schemas"


def _artifacts() -> dict:
    return {
        "perception_frame.schema.json": PerceptionFrame.model_json_schema(),
        "robot_config.schema.json": RobotConfig.model_json_schema(),
    }


def _render(schema: dict) -> str:
    return json.dumps(schema, indent=2, ensure_ascii=False)


def main() -> None:
    check = "--check" in sys.argv[1:]
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    docs_dir = Path(args[0]) if args else REPO / "docs" / "schema"

    drift = []
    for name, schema in _artifacts().items():
        rendered = _render(schema)
        targets = [docs_dir / name]
        if name == "robot_config.schema.json":
            targets.append(EXT_SCHEMA_DIR / name)
        for path in targets:
            if check:
                current = path.read_text(encoding="utf-8") if path.exists() else None
                if current != rendered:
                    drift.append(str(path))
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding="utf-8")
            print(f"wrote {path}")

    if check:
        if drift:
            print("schema drift detected:\n  " + "\n  ".join(drift), file=sys.stderr)
            raise SystemExit(1)
        print("schemas are in sync.")
        return
    print("schemas are JSON Schema (OpenAPI-compatible); regenerate after model changes.")


if __name__ == "__main__":
    main()
