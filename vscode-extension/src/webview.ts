/** Hosts the SDK dashboard inside a VS Code webview panel. */

import * as vscode from "vscode";
import * as fs from "fs";
import * as path from "path";

export class DashboardPanel {
  private static current: DashboardPanel | undefined;
  private readonly panel: vscode.WebviewPanel;

  private constructor(panel: vscode.WebviewPanel, extensionPath: string, origin: string) {
    this.panel = panel;
    this.panel.webview.html = buildHtml(extensionPath, origin);
    this.panel.onDidDispose(() => {
      if (DashboardPanel.current === this) {
        DashboardPanel.current = undefined;
      }
    });
  }

  static show(extensionPath: string, origin: string): void {
    if (DashboardPanel.current) {
      DashboardPanel.current.setOrigin(extensionPath, origin);
      DashboardPanel.current.panel.reveal();
      return;
    }
    const panel = vscode.window.createWebviewPanel(
      "lynx.dashboard",
      "Lynx Dashboard",
      vscode.ViewColumn.One,
      { enableScripts: true, retainContextWhenHidden: true },
    );
    DashboardPanel.current = new DashboardPanel(panel, extensionPath, origin);
  }

  private setOrigin(extensionPath: string, origin: string): void {
    this.panel.webview.html = buildHtml(extensionPath, origin);
  }
}

function buildHtml(extensionPath: string, origin: string): string {
  const htmlPath = path.join(extensionPath, "media", "dashboard.html");
  const html = fs.readFileSync(htmlPath, "utf-8");
  return html.replaceAll("__ORIGIN__", origin).replaceAll("__NONCE__", nonce());
}

function nonce(): string {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  return Array.from({ length: 32 }, () => chars[Math.floor(Math.random() * chars.length)]).join("");
}
