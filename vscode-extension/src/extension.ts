import * as vscode from "vscode";
import { LynxSession } from "./session";
import { LynxClient } from "./client";
import { DashboardPanel } from "./webview";

export function activate(context: vscode.ExtensionContext): void {
  const session = new LynxSession();
  context.subscriptions.push({ dispose: () => session.dispose() });

  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  status.command = "lynx.toggle";
  status.hide();
  context.subscriptions.push(status);

  let pollTimer: ReturnType<typeof setInterval> | undefined;

  const setRunning = (running: boolean) => {
    void vscode.commands.executeCommand("setContext", "lynx.running", running);
    if (!running) {
      status.text = "$(play) Lynx: start";
      status.tooltip = "Start the Lynx demo";
      return;
    }
    status.text = `$(radio-tower) Lynx: ${session.origin}`;
    status.tooltip = `Lynx demo running on ${session.origin}`;
  };

  const startPolling = () => {
    if (pollTimer) {
      clearInterval(pollTimer);
    }
    pollTimer = setInterval(async () => {
      if (!session.running) {
        return;
      }
      try {
        const m = await new LynxClient(session.origin).metrics();
        const lat = m.latency_ms?.avg ?? 0;
        status.text = `$(radio-tower) Lynx: ${m.backend} · ${lat.toFixed(0)}ms · ${m.fps.toFixed(1)}fps`;
      } catch {
        // server still warming up — keep the previous text
      }
    }, 2000);
  };

  const start = async () => {
    if (session.running) {
      return;
    }
    try {
      status.text = "$(sync~spin) Lynx: starting…";
      await session.start();
      setRunning(true);
      DashboardPanel.show(context.extensionPath, session.origin);
      startPolling();
      void vscode.window.showInformationMessage(`Lynx demo running on ${session.origin}`);
    } catch (e) {
      setRunning(false);
      void vscode.window.showErrorMessage(`Lynx failed to start: ${(e as Error).message}`);
    }
  };

  const stop = () => {
    session.stop();
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = undefined;
    }
    setRunning(false);
  };

  const switchBackend = async () => {
    if (!session.running) {
      await start();
      return;
    }
    const pick = await vscode.window.showQuickPick(["offline", "enhanced", "onnx"], {
      title: "Lynx backend",
      placeHolder: "Choose a backend",
    });
    if (!pick) {
      return;
    }
    try {
      await new LynxClient(session.origin).switchBackend(pick);
      void vscode.window.showInformationMessage(`Lynx backend → ${pick}`);
    } catch (e) {
      void vscode.window.showErrorMessage(`Switch failed: ${(e as Error).message}`);
    }
  };

  const openConfig = async () => {
    const rootUri = LynxSession.resolveRoot();
    if (!rootUri) {
      return;
    }
    const uri = vscode.Uri.joinPath(rootUri, "config", "robot.demo.yaml");
    const doc = await vscode.workspace.openTextDocument(uri);
    await vscode.window.showTextDocument(doc);
  };

  const refresh = () => {
    // Show the status-bar item only when the workspace is the Lynx repo
    // (or lynx.workspacePath points at it). Re-runs when folders change, so
    // opening the repo after the host has started still activates the UI.
    if (LynxSession.isLynxWorkspace(LynxSession.resolveRoot())) {
      status.show();
      setRunning(session.running);
    } else {
      status.hide();
      stop();
    }
  };

  context.subscriptions.push(
    vscode.workspace.onDidChangeWorkspaceFolders(refresh),
    vscode.commands.registerCommand("lynx.start", start),
    vscode.commands.registerCommand("lynx.stop", stop),
    vscode.commands.registerCommand("lynx.toggle", () => (session.running ? stop() : start())),
    vscode.commands.registerCommand("lynx.switchBackend", switchBackend),
    vscode.commands.registerCommand("lynx.openConfig", openConfig),
    vscode.commands.registerCommand("lynx.showDashboard", async () => {
      if (!session.running) {
        await start();
      }
      DashboardPanel.show(context.extensionPath, session.origin);
    }),
  );

  refresh();
}

export function deactivate(): void {}
