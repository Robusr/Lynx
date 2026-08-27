"""Start the demo server.

Usage:
    python scripts/run.py                      # uses config/robot.demo.yaml
    python scripts/run.py path/to/robot.yaml
    LYNX_CONFIG=path/to/robot.yaml python scripts/run.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn

from sdk.config import load_config
from sdk.validate import summarize, validate


def main() -> None:
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
        "LYNX_CONFIG", str(Path(__file__).resolve().parents[1] / "config" / "robot.demo.yaml")
    )
    cfg = load_config(cfg_path)
    print(summarize(validate(cfg)))
    print(f"\nStarting demo server (backend={cfg.perception.backend}) → http://127.0.0.1:8000")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
