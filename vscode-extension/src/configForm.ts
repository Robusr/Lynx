/** Schema-driven visual form editor for the robot config (webview panel). */

import * as vscode from "vscode";
import * as fs from "fs";
import * as path from "path";
import { spawn } from "child_process";
import { LynxSession } from "./session";
import { nonce } from "./webview";

interface JsonResult {
  ok: boolean;
  error?: string;
  config?: Record<string, unknown>;
  checks?: Array<{ name: string; severity: string; message: string }>;
  ai_lock?: string[];
}

interface PanelContext {
  root: string;
  python: string;
  configPath: string;
}

export class ConfigPanel {
  private static current: ConfigPanel | undefined;
  private readonly panel: vscode.WebviewPanel;
  private readonly root: string;
  private readonly python: string;
  private readonly configPath: string;
  private readonly onSaved: () => void;

  private constructor(panel: vscode.WebviewPanel, ctx: PanelContext, onSaved: () => void) {
    this.panel = panel;
    this.root = ctx.root;
    this.python = ctx.python;
    this.configPath = ctx.configPath;
    this.onSaved = onSaved;
    this.panel.webview.onDidReceiveMessage((msg) => this.onMessage(msg));
    this.panel.onDidDispose(() => {
      if (ConfigPanel.current === this) {
        ConfigPanel.current = undefined;
      }
    });
  }

  static get isOpen(): boolean {
    return ConfigPanel.current !== undefined;
  }

  /** Re-read the config from disk and push it to the form (e.g. after a manual YAML save). */
  static refresh(): void {
    void ConfigPanel.current?.reload();
  }

  static async show(extensionPath: string, onSaved: () => void): Promise<void> {
    if (ConfigPanel.current) {
      ConfigPanel.current.panel.reveal();
      return;
    }
    const rootUri = LynxSession.resolveRoot();
    if (!rootUri) {
      void vscode.window.showErrorMessage("No workspace folder. Open the Lynx repo first.");
      return;
    }
    const root = rootUri.fsPath;
    const python = LynxSession.resolvePython(root);
    const configPath = path.join(root, "config", "robot.demo.yaml");
    const schema = fs.readFileSync(
      path.join(extensionPath, "schemas", "robot_config.schema.json"),
      "utf-8",
    );
    const result = await runPythonJson(root, python, [
      path.join(root, "scripts", "config_io.py"),
      "get",
      configPath,
    ]);
    if (!result.ok || !result.config) {
      void vscode.window.showErrorMessage(`Lynx: could not load config — ${result.error ?? "unknown error"}`);
      return;
    }
    const panel = vscode.window.createWebviewPanel(
      "lynx.config",
      "Lynx Config",
      vscode.ViewColumn.One,
      { enableScripts: true, retainContextWhenHidden: true },
    );
    ConfigPanel.current = new ConfigPanel(panel, { root, python, configPath }, onSaved);
    panel.webview.html = buildHtml(extensionPath, schema, result.config, result.ai_lock ?? ["safety"]);
  }

  private async onMessage(msg: { type: string; json?: Record<string, unknown> }): Promise<void> {
    switch (msg.type) {
      case "validate":
        this.validate(msg.json);
        break;
      case "save":
        await this.save(msg.json);
        break;
      case "refresh":
        await this.reload();
        break;
    }
  }

  private validate(json?: Record<string, unknown>): void {
    if (!json) {
      return;
    }
    void runPythonJson(
      this.root,
      this.python,
      [path.join(this.root, "scripts", "config_io.py"), "check"],
      JSON.stringify(json),
    ).then((r) => this.panel.webview.postMessage({ type: "validation", result: r }));
  }

  private async save(json?: Record<string, unknown>): Promise<void> {
    if (!json) {
      return;
    }
    const r = await runPythonJson(
      this.root,
      this.python,
      [path.join(this.root, "scripts", "config_io.py"), "set", this.configPath],
      JSON.stringify(json),
    );
    this.panel.webview.postMessage({ type: "saved", ok: r.ok, error: r.error });
    if (r.ok) {
      this.onSaved();
    }
  }

  private async reload(): Promise<void> {
    const r = await runPythonJson(this.root, this.python, [
      path.join(this.root, "scripts", "config_io.py"),
      "get",
      this.configPath,
    ]);
    if (r.ok && r.config) {
      this.panel.webview.postMessage({ type: "refreshed", config: r.config });
    }
  }
}

/** Run a config_io.py subcommand and parse its single-line JSON reply. */
function runPythonJson(
  root: string,
  python: string,
  args: string[],
  input?: string,
): Promise<JsonResult> {
  return new Promise((resolve) => {
    const child = spawn(python, args, { cwd: root });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d: Buffer) => (stdout += d.toString()));
    child.stderr.on("data", (d: Buffer) => (stderr += d.toString()));
    child.on("error", (err) => resolve({ ok: false, error: `spawn failed: ${err.message}` }));
    child.on("close", () => {
      try {
        resolve(JSON.parse(stdout.trim()) as JsonResult);
      } catch {
        resolve({ ok: false, error: stderr.trim() || "no output from config_io.py" });
      }
    });
    if (child.stdin) {
      if (input !== undefined) {
        child.stdin.write(input);
      }
      child.stdin.end();
    }
  });
}

function buildHtml(
  extensionPath: string,
  schema: string,
  config: Record<string, unknown>,
  aiLock: string[],
): string {
  const html = fs.readFileSync(path.join(extensionPath, "media", "config-form.html"), "utf-8");
  return html
    .replaceAll("__NONCE__", nonce())
    .replace("__SCHEMA__", schema)
    .replace("__CONFIG__", JSON.stringify(config).replaceAll("</", "<\\/"))
    .replace("__AI_LOCK__", JSON.stringify(aiLock));
}
