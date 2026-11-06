"""Start the demo server.

Usage:
    python scripts/run.py                      # uses config/robot.demo.yaml
    python scripts/run.py path/to/robot.yaml
    python scripts/run.py --accept-warnings
    LYNX_CONFIG=path/to/robot.yaml python scripts/run.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import uvicorn

from sdk.config import load_config
from sdk.validate import summarize, validate


def main() -> None:
    accept_warnings = "--accept-warnings" in sys.argv[1:]
    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    cfg_path = positional[0] if positional else os.environ.get(
        "LYNX_CONFIG", str(REPO / "config" / "robot.demo.yaml")
    )
    cfg = load_config(cfg_path)
    checks = validate(cfg)
    print(summarize(checks))
    if any(c.severity == "error" for c in checks):
        raise SystemExit("preflight failed — fix the manifest before starting.")
    if any(c.severity == "warn" for c in checks) and not accept_warnings:
        raise SystemExit(
            "preflight produced warnings; pass --accept-warnings or set "
            "LYNX_ACCEPT_WARNINGS=1 to start anyway."
        )

    os.environ["LYNX_CONFIG"] = str(Path(cfg_path).resolve())
    os.environ["LYNX_ACCEPT_WARNINGS"] = "1" if accept_warnings else "0"
    host = os.environ.get("LYNX_HOST", "127.0.0.1")
    port = int(os.environ.get("LYNX_PORT", "8000"))
    print(f"\nStarting demo server (backend={cfg.perception.backend}) → http://{host}:{port}")
    uvicorn.run("server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
