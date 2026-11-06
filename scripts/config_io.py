"""Read/write the robot config as JSON for the VS Code form editor.

The form never parses or emits YAML itself — that stays in Python where the
pydantic model (the single source of truth) lives. Each subcommand prints one
line of JSON to stdout:

    python config_io.py get <path>   -> {"ok": true, "config": {...}}
    python config_io.py check        -> reads JSON on stdin -> {"ok": true, "checks": [...]}
    python config_io.py set <path>   -> reads JSON on stdin -> writes YAML -> {"ok": true}

`set` preserves existing YAML comments when `ruamel.yaml` is available and writes
atomically, so an interrupted save cannot truncate the manifest.
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

from sdk.config import RobotConfig, load_config
from sdk.validate import validate

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "robot.demo.yaml"

# Top-level config sections marked `@ai-lock` — tooling (form / CLI) treats them
# as read-only; only a human editing the YAML may change them. This list is the
# single source of truth and is mirrored by the form's read-only rendering.
AI_LOCK_SECTIONS = ["safety"]


class AiLockError(Exception):
    """Tooling attempted to change an @ai-lock (read-only) section."""


def _print(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False))


def _resolve_path(argv: list) -> Path:
    return Path(argv[2]) if len(argv) > 2 else DEFAULT_CONFIG


def cmd_get(path: Path) -> None:
    try:
        cfg = load_config(str(path))
        _print({"ok": True, "config": cfg.model_dump(), "ai_lock": AI_LOCK_SECTIONS})
    except Exception as exc:  # IO or structural (pydantic) error
        _print({"ok": False, "error": str(exc)})


def cmd_check() -> None:
    try:
        obj = json.load(sys.stdin)
        cfg = RobotConfig.model_validate(obj)
        checks = [{"name": c.name, "severity": c.severity, "message": c.message} for c in validate(cfg)]
        _print({"ok": True, "checks": checks})
    except Exception as exc:
        _print({"ok": False, "error": str(exc)})


def cmd_set(path: Path) -> None:
    try:
        obj = json.load(sys.stdin)
        cfg = RobotConfig.model_validate(obj)
        _guard_ai_lock(path, cfg)
        _atomic_write(path, _dump_yaml(path, cfg))
        _print({"ok": True})
    except AiLockError as exc:
        _print({"ok": False, "error": str(exc)})
    except Exception as exc:
        _print({"ok": False, "error": str(exc)})


def _guard_ai_lock(path: Path, cfg: RobotConfig) -> None:
    """Reject writes that change an @ai-lock section.

    The baseline is whatever is currently on disk (not the code defaults) — a
    human may have hand-tuned the safety block, and the form must preserve it.
    If there is no valid baseline (e.g. first write), there is nothing to protect.
    """
    try:
        current = load_config(str(path))
    except Exception:
        return
    changed = [
        name
        for name in AI_LOCK_SECTIONS
        if getattr(current, name).model_dump() != getattr(cfg, name).model_dump()
    ]
    if changed:
        raise AiLockError(
            "@ai-lock section(s) are read-only via tooling: "
            + ", ".join(changed)
            + ". Edit the YAML directly to change them."
        )


def _merge(existing, incoming) -> None:
    """Recursively update a ruamel CommentedMap in place, preserving comments."""
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(existing.get(key), dict):
            _merge(existing[key], value)
        else:
            existing[key] = value
    for key in list(existing.keys()):
        if key not in incoming:
            del existing[key]


def _dump_yaml(path: Path, cfg: RobotConfig) -> str:
    data = cfg.model_dump(mode="json")
    try:
        from ruamel.yaml import YAML
    except ImportError:  # pragma: no cover - ruamel is a declared dependency
        body = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        for name in AI_LOCK_SECTIONS:
            body = body.replace(
                f"{name}:",
                f"# @ai-lock — validator treats these as read-only\n{name}:",
                1,
            )
        return '# robot config — edited via "Lynx: Edit Config (Form)"\n' + body

    rt = YAML(typ="rt")
    rt.preserve_quotes = True
    rt.indent(mapping=2, sequence=4, offset=2)
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            existing = rt.load(f) or {}
    else:
        existing = {}
    if not existing:
        existing = data
        existing = {"schema_version": data["schema_version"], **data}
    else:
        _merge(existing, data)
    stream = io.StringIO()
    rt.dump(existing, stream)
    text = stream.getvalue()
    if not text.startswith("#"):
        text = '# robot config — edited via "Lynx: Edit Config (Form)"\n' + text
    return text


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def main() -> None:
    if len(sys.argv) < 2:
        _print({"ok": False, "error": "usage: config_io.py get <path> | check | set <path>"})
        return
    cmd = sys.argv[1]
    if cmd == "get":
        cmd_get(_resolve_path(sys.argv))
    elif cmd == "check":
        cmd_check()
    elif cmd == "set":
        cmd_set(_resolve_path(sys.argv))
    else:
        _print({"ok": False, "error": f"unknown subcommand: {cmd}"})


if __name__ == "__main__":
    main()
