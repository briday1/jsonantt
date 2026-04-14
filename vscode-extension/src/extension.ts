/**
 * extension.ts – entry point for the jsonantt VS Code extension.
 *
 * Registers the "jsonantt.preview" command, wires document-change listeners,
 * and delegates panel lifecycle to PreviewPanel.
 */
import * as vscode from "vscode";
import { PreviewPanel } from "./previewPanel";

export function activate(context: vscode.ExtensionContext): void {
  // Command: open (or focus) the preview for the active JSON editor.
  const openPreviewCmd = vscode.commands.registerCommand(
    "jsonantt.preview",
    () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor || editor.document.languageId !== "json") {
        vscode.window.showWarningMessage(
          "jsonantt: Open a JSON file in the active editor first."
        );
        return;
      }
      PreviewPanel.createOrShow(context, editor.document);
    }
  );
  context.subscriptions.push(openPreviewCmd);

  // Re-render on save.
  const onSave = vscode.workspace.onDidSaveTextDocument((doc) => {
    if (PreviewPanel.current && PreviewPanel.current.isTrackingDocument(doc)) {
      const cfg = vscode.workspace.getConfiguration("jsonantt");
      const mode = cfg.get<string>("autoPreview", "onSave");
      if (mode === "onSave" || mode === "onType") {
        PreviewPanel.current.render();
      }
    }
  });
  context.subscriptions.push(onSave);

  // Re-render while typing (debounced).
  let debounceTimer: ReturnType<typeof setTimeout> | undefined;
  const onChange = vscode.workspace.onDidChangeTextDocument((e) => {
    if (PreviewPanel.current && PreviewPanel.current.isTrackingDocument(e.document)) {
      const cfg = vscode.workspace.getConfiguration("jsonantt");
      if (cfg.get<string>("autoPreview", "onSave") === "onType") {
        if (debounceTimer) {
          clearTimeout(debounceTimer);
        }
        debounceTimer = setTimeout(() => {
          PreviewPanel.current?.render();
        }, 500);
      }
    }
  });
  context.subscriptions.push(onChange);

  // When the active editor changes, update the tracked document if the panel is open.
  const onEditorChange = vscode.window.onDidChangeActiveTextEditor((editor) => {
    if (
      PreviewPanel.current &&
      editor &&
      editor.document.languageId === "json"
    ) {
      PreviewPanel.current.trackDocument(editor.document);
    }
  });
  context.subscriptions.push(onEditorChange);
}

export function deactivate(): void {
  // Nothing to clean up – PreviewPanel registers its own disposable.
}
