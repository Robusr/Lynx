/** Runs scripts/validate_json.py and maps its JSON output to editor diagnostics. */

import * as vscode from "vscode";
import * as path from "path";
import { execFile } from "child_process";

interface Check {
  name: string;
  severity: "error" | "warn" | "pass";
  message: string;
}

export interface ValidateResult {
  ok: boolean;
  error?: string;
  checks?: Check[];
}

/** Execute the SDK's JSON validator and return its structured output. */
export function runValidate(root: string, python: string, configPath: string): Promise<ValidateResult> {
  return new Promise((resolve) => {
    const script = path.join(root, "scripts", "validate_json.py");
    execFile(python, [script, configPath], { cwd: root, timeout: 15000 }, (err, stdout) => {
      if (err) {
        resolve({ ok: false, error: `validate_json.py failed: ${err.message}` });
        return;
      }
      try {
        resolve(JSON.parse(stdout.trim()) as ValidateResult);
      } catch {
        resolve({ ok: false, error: "Could not parse validate_json.py output." });
      }
    });
  });
}

/** Convert validator output to editor diagnostics. The JSON has no line numbers,
 *  so every item anchors to the first line (structural errors are file-wide). */
export function toDiagnostics(result: ValidateResult, doc: vscode.TextDocument): vscode.Diagnostic[] {
  const firstLine = new vscode.Range(0, 0, 0, doc.lineAt(0).text.length);
  if (!result.ok) {
    return [
      new vscode.Diagnostic(firstLine, result.error ?? "Validation failed.", vscode.DiagnosticSeverity.Error),
    ];
  }
  const severityMap: Record<string, vscode.DiagnosticSeverity> = {
    error: vscode.DiagnosticSeverity.Error,
    warn: vscode.DiagnosticSeverity.Warning,
    pass: vscode.DiagnosticSeverity.Information,
  };
  return (result.checks ?? []).map((c) => {
    const d = new vscode.Diagnostic(
      firstLine,
      `${c.name}: ${c.message}`,
      severityMap[c.severity] ?? vscode.DiagnosticSeverity.Information,
    );
    d.source = "lynx";
    return d;
  });
}
