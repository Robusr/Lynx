/** Manages the Python demo server as a child process. */

import * as vscode from "vscode";
import * as net from "net";
import * as fs from "fs";
import * as path from "path";
import { spawn, ChildProcess } from "child_process";

export class LynxSession {
  private proc: ChildProcess | null = null;
  private _port = 0;
  private _running = false;

  get port(): number {
    return this._port;
  }

  get running(): boolean {
    return this._running;
  }

  get origin(): string {
    return `http://127.0.0.1:${this._port}`;
  }

  /** Resolve the Lynx repo root: explicit setting, else the workspace folder
   *  that actually contains the SDK entrypoint (multi-root safe). */
  static resolveRoot(): vscode.Uri | undefined {
    const configured = vscode.workspace.getConfiguration("lynx").get<string>("workspacePath", "");
    if (configured) {
      return vscode.Uri.file(configured);
    }
    const folders = vscode.workspace.workspaceFolders ?? [];
    const lynx = folders.find((f) => fs.existsSync(path.join(f.uri.fsPath, "scripts", "run.py")));
    return (lynx ?? folders[0])?.uri;
  }

  static isLynxWorkspace(root: vscode.Uri | undefined): boolean {
    if (!root) {
      return false;
    }
    return fs.existsSync(path.join(root.fsPath, "scripts", "run.py"));
  }

  async start(): Promise<void> {
    if (this._running) {
      return;
    }
    const rootUri = LynxSession.resolveRoot();
    if (!rootUri) {
      throw new Error("No workspace folder. Open the Lynx repo (or set lynx.workspacePath).");
    }
    const root = rootUri.fsPath;

    this._port = await findFreePort(this.preferredPort());
    const python = this.pythonPath(root);

    const env = {
      ...process.env,
      LYNX_HOST: "127.0.0.1",
      LYNX_PORT: String(this._port),
    };
    this.proc = spawn(python, ["scripts/run.py"], { cwd: root, env, stdio: "ignore" });
    this.proc.once("error", (err) => {
      this._running = false;
      this.proc = null;
      void vscode.window.showErrorMessage(`Lynx failed to launch: ${err.message}`);
    });
    this.proc.once("exit", () => {
      this._running = false;
      this.proc = null;
    });
    this._running = true;
  }

  stop(): void {
    if (this.proc) {
      this.proc.kill();
      this.proc = null;
    }
    this._running = false;
  }

  dispose(): void {
    this.stop();
  }

  private preferredPort(): number {
    return vscode.workspace.getConfiguration("lynx").get<number>("port", 8123);
  }

  private pythonPath(root: string): string {
    const cfg = vscode.workspace.getConfiguration("lynx").get<string>("pythonPath", "");
    if (cfg) {
      return cfg;
    }
    const py = vscode.workspace.getConfiguration("python").get<string>("defaultInterpreterPath", "");
    if (py) {
      return py;
    }
    return path.join(root, ".venv", "bin", "python");
  }
}

function findFreePort(start: number): Promise<number> {
  return (async () => {
    for (let p = start; p < start + 100; p++) {
      if (await isPortFree(p)) {
        return p;
      }
    }
    throw new Error(`No free port in range ${start}–${start + 100}`);
  })();
}

function isPortFree(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once("error", () => resolve(false));
    server.listen(port, "127.0.0.1", () => server.close(() => resolve(true)));
  });
}
