"""Generate the VS Code webview dashboard from dashboard/index.html.

`dashboard/index.html` is the single source of truth. The webview variant needs
two mechanical additions: a CSP header with a nonce placeholder and a nonce on
the inline script tag. `--check` is the CI drift guard.

Usage:
    python scripts/sync_dashboard.py [--check]
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "dashboard" / "index.html"
TARGET = REPO / "vscode-extension" / "media" / "dashboard.html"

CSP = (
    "default-src 'none'; img-src data: blob: http: https:; "
    "style-src 'unsafe-inline'; script-src 'nonce-__NONCE__'; "
    "connect-src http: https: ws: wss:;"
)


def build(text: str) -> str:
    marker = '<meta charset="utf-8" />'
    if marker not in text:
        raise SystemExit(f"{SOURCE}: missing {marker!r}")
    text = text.replace(
        marker,
        marker + f'\n  <meta http-equiv="Content-Security-Policy" content="{CSP}" />',
        1,
    )
    if "<script>" not in text:
        raise SystemExit(f"{SOURCE}: missing inline <script> tag")
    return text.replace("<script>", '<script nonce="__NONCE__">', 1)


def main() -> None:
    check = "--check" in sys.argv[1:]
    generated = build(SOURCE.read_text(encoding="utf-8"))
    if check:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else None
        if current != generated:
            print(f"dashboard drift: {TARGET} is out of date", file=sys.stderr)
            raise SystemExit(1)
        print("dashboard is in sync.")
        return
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(generated, encoding="utf-8")
    print(f"wrote {TARGET}")


if __name__ == "__main__":
    main()
