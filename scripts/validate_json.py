"""Print validate() results as JSON for tooling (the VS Code extension).

Usage:
    python scripts/validate_json.py [path/to/robot.yaml]

Prints one line of JSON:
    {"ok": true, "checks": [{"name": ..., "severity": ..., "message": ...}]}
or, when the manifest fails to load/structurally validate:
    {"ok": false, "error": "..."}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sdk.config import load_config
from sdk.validate import validate


def main() -> None:
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "config/robot.demo.yaml"
    try:
        cfg = load_config(cfg_path)
    except Exception as exc:  # structural (pydantic) or IO error
        print(json.dumps({"ok": False, "error": str(exc)}))
        return
    checks = [{"name": c.name, "severity": c.severity, "message": c.message} for c in validate(cfg)]
    print(json.dumps({"ok": True, "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main()
