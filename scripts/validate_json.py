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
from sdk.validate import to_report, validate


def main() -> None:
    argv = sys.argv[1:]
    out_path = None
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 < len(argv):
            out_path = argv[i + 1]
            del argv[i:i + 2]
    cfg_path = argv[0] if argv else "config/robot.demo.yaml"
    try:
        cfg = load_config(cfg_path)
    except Exception as exc:  # structural (pydantic) or IO error
        print(json.dumps({"ok": False, "error": str(exc)}))
        return
    report = to_report(validate(cfg))
    print(json.dumps(report, ensure_ascii=False))
    if out_path:
        Path(out_path).write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
