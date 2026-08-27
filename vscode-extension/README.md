# Lynx for VS Code

Run and demo the [Lynx perception-fusion SDK](../) from inside VS Code. The
extension is a thin shell over the SDK's existing FastAPI demo server — it
spawns `scripts/run.py`, then drives it over HTTP/WebSocket and renders the
dashboard in a webview panel.

## Setup

```bash
cd vscode-extension
npm install
npm run compile
```

Then press **F5** (Run Extension). The Extension Development Host opens empty;
**open the Lynx repo as a folder there** (`File → Open Folder…` → the repo root).
The extension activates via `workspaceContains:scripts/run.py` when that folder
is opened, and a `▶ Lynx: start` item appears in the status bar.

## What you get

| Feature | Command | Detail |
|---|---|---|
| Dashboard | `Lynx: Show Dashboard` | camera overlay + bird's-eye view + objects, in a webview panel |
| Start / Stop | `Lynx: Start Demo` / `Lynx: Stop` | spawns/kills `scripts/run.py` on a free port (default 8123) |
| Switch backend | `Lynx: Switch Backend` | QuickPick over offline / enhanced / onnx → `POST /api/switch` |
| Status bar | click the `🐆 Lynx` item | start/stop toggle; live `backend · avg-latency · fps` |
| Open config | `Lynx: Open Config` | opens `config/robot.demo.yaml` |

## Configuration

- `lynx.workspacePath` — absolute path to the Lynx repo (blank → auto-detect: the workspace folder containing `scripts/run.py`, else the first folder).
- `lynx.pythonPath` — Python interpreter (blank → VS Code Python setting, then `<repo>/.venv/bin/python`).
- `lynx.port` — preferred server port (default 8123; a free port is picked automatically).

## YAML validation

`robot*.yaml` is associated with `schemas/robot_config.schema.json` (a copy of
`docs/schema/robot_config.schema.json`). This requires the
[YAML extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml)
(redhat.vscode-yaml) to be installed.

Regenerate the schema after config model changes:
`cd .. && python scripts/export_schema.py docs/schema` then copy the result here.

## Notes

- The extension assumes the SDK's Python env and models (`yolo11s.pt`/`.onnx`)
  already exist in the repo. It does not bundle them.
- `media/dashboard.html` is derived from `../dashboard/index.html` and adapted
  for the webview (CSP nonce + injected server origin); keep them in sync when
  the dashboard changes.
