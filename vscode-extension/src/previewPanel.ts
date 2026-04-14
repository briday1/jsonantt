/**
 * previewPanel.ts – manages the jsonantt WebviewPanel lifecycle.
 *
 * Only one preview panel is allowed at a time (singleton via `PreviewPanel.current`).
 * The panel tracks a single VS Code TextDocument and re-renders it on demand.
 */
import * as path from "path";
import * as fs from "fs";
import * as vscode from "vscode";
import { renderChart, RenderOptions } from "./renderer";

export class PreviewPanel {
  /** The single active instance, if any. */
  public static current: PreviewPanel | undefined;

  private readonly _panel: vscode.WebviewPanel;
  private readonly _context: vscode.ExtensionContext;
  private _document: vscode.TextDocument;
  private _disposables: vscode.Disposable[] = [];
  private _options: RenderOptions;

  // ---------------------------------------------------------------------------
  // Public static API
  // ---------------------------------------------------------------------------

  /** Create a new panel or reveal the existing one, then render immediately. */
  public static createOrShow(
    context: vscode.ExtensionContext,
    document: vscode.TextDocument
  ): void {
    const column = vscode.ViewColumn.Beside;

    if (PreviewPanel.current) {
      PreviewPanel.current._panel.reveal(column);
      PreviewPanel.current.trackDocument(document);
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      "jsonanttPreview",
      "jsonantt Preview",
      column,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [
          vscode.Uri.file(path.join(context.extensionPath, "src", "webview")),
          vscode.Uri.file(path.join(context.extensionPath, "out", "webview")),
        ],
      }
    );

    PreviewPanel.current = new PreviewPanel(panel, context, document);
  }

  // ---------------------------------------------------------------------------
  // Constructor
  // ---------------------------------------------------------------------------

  private constructor(
    panel: vscode.WebviewPanel,
    context: vscode.ExtensionContext,
    document: vscode.TextDocument
  ) {
    this._panel = panel;
    this._context = context;
    this._document = document;

    const cfg = vscode.workspace.getConfiguration("jsonantt");
    this._options = {
      chartType: (cfg.get<string>("defaultChartType", "chart") as RenderOptions["chartType"]),
      renderDepth: 0,
      burnField: "cost",
      burnPeriod: "month",
      burnGroup: "0",
      burnDisplayFactor: "1",
      dateLine: "",
      dateLineColor: "#C00000",
      dpi: cfg.get<number>("defaultDpi", 150),
      comparePath: "",
      milestonesOnly: false,
      noMilestones: false,
    };

    this._panel.webview.html = this._getHtml();
    this._panel.title = `jsonantt: ${path.basename(document.fileName)}`;

    // Handle messages from the webview.
    this._panel.webview.onDidReceiveMessage(
      (message: WebviewMessage) => this._handleMessage(message),
      null,
      this._disposables
    );

    // Dispose when the panel is closed.
    this._panel.onDidDispose(() => this.dispose(), null, this._disposables);

    // Trigger initial render.
    this.render();
  }

  // ---------------------------------------------------------------------------
  // Public instance API
  // ---------------------------------------------------------------------------

  public isTrackingDocument(doc: vscode.TextDocument): boolean {
    return this._document.uri.toString() === doc.uri.toString();
  }

  public trackDocument(document: vscode.TextDocument): void {
    this._document = document;
    this._panel.title = `jsonantt: ${path.basename(document.fileName)}`;
    this.render();
  }

  /** Trigger a render using the current options and document content. */
  public async render(): Promise<void> {
    this._postMessage({ type: "rendering" });

    const jsonText = this._document.getText();
    const result = await renderChart(jsonText, this._options);

    if (result.ok && result.svgData) {
      this._postMessage({ type: "rendered", svgData: result.svgData });
    } else {
      this._postMessage({ type: "error", error: result.error ?? "Unknown error" });
    }
  }

  public dispose(): void {
    PreviewPanel.current = undefined;
    this._panel.dispose();
    for (const d of this._disposables) {
      d.dispose();
    }
    this._disposables = [];
  }

  // ---------------------------------------------------------------------------
  // Private helpers
  // ---------------------------------------------------------------------------

  private _postMessage(message: HostMessage): void {
    this._panel.webview.postMessage(message);
  }

  private _handleMessage(message: WebviewMessage): void {
    switch (message.type) {
      case "updateOptions":
        this._options = { ...this._options, ...message.options };
        this.render();
        break;
      case "refresh":
        this.render();
        break;
      case "export": {
        const defaultUri = vscode.Uri.file(
          this._document.uri.fsPath.replace(/\.json$/i, ".svg")
        );
        vscode.window
          .showSaveDialog({
            defaultUri,
            filters: { "SVG Images": ["svg"], "PNG Images": ["png"] },
          })
          .then((uri) => {
            if (!uri) return;
            // Re-render directly to the chosen output path via a separate options copy.
            const exportOpts = { ...this._options };
            const isSvg = uri.fsPath.toLowerCase().endsWith(".svg");
            void this._renderToFile(uri.fsPath, isSvg, exportOpts);
          });
        break;
      }
      case "pickCompare": {
        vscode.window
          .showOpenDialog({
            canSelectFiles: true,
            canSelectFolders: false,
            canSelectMany: false,
            filters: { "JSON Files": ["json"] },
            openLabel: "Select baseline JSON",
          })
          .then((uris) => {
            if (!uris || uris.length === 0) return;
            this._options.comparePath = uris[0].fsPath;
            this._postMessage({ type: "comparePathSet", filePath: uris[0].fsPath });
            this.render();
          });
        break;
      }
      case "installJsonantt": {
        const terminal = vscode.window.createTerminal("Install jsonantt");
        terminal.show();
        terminal.sendText("pip install jsonantt");
        break;
      }
    }
  }

  private async _renderToFile(
    outputPath: string,
    _isSvg: boolean,
    opts: RenderOptions
  ): Promise<void> {
    const { renderChart: rc } = await import("./renderer");
    const result = await rc(this._document.getText(), opts);
    if (result.ok && result.svgData) {
      fs.writeFileSync(outputPath, result.svgData, "utf8");
      vscode.window.showInformationMessage(`Chart exported to ${outputPath}`);
    } else {
      vscode.window.showErrorMessage(
        `Export failed: ${result.error ?? "Unknown error"}`
      );
    }
  }

  private _getHtml(): string {
    const webview = this._panel.webview;

    // Resolve webview-safe URIs for the static assets.
    // We ship the assets under src/webview/ (dev) and copy them to out/webview/ via compile.
    const assetBase = vscode.Uri.file(
      path.join(this._context.extensionPath, "src", "webview")
    );
    const jsUri = webview.asWebviewUri(
      vscode.Uri.file(path.join(assetBase.fsPath, "panel.js"))
    );
    const cssUri = webview.asWebviewUri(
      vscode.Uri.file(path.join(assetBase.fsPath, "panel.css"))
    );

    // Content-Security-Policy nonce for inline scripts.
    const nonce = getNonce();

    return /* html */ `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Content-Security-Policy"
        content="default-src 'none';
                 img-src ${webview.cspSource} data: blob:;
                 style-src ${webview.cspSource} 'unsafe-inline';
                 script-src 'nonce-${nonce}' ${webview.cspSource};">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>jsonantt Preview</title>
  <link rel="stylesheet" href="${cssUri}">
</head>
<body>
  <!-- ── Toolbar ─────────────────────────────────────── -->
  <div id="toolbar">
    <div class="toolbar-row">
      <label for="chartType">Chart type</label>
      <select id="chartType">
        <option value="chart">Gantt Chart</option>
        <option value="table">Task Table</option>
        <option value="burn">Burn Chart</option>
        <option value="burn-table">Burn Table</option>
      </select>

      <label for="renderDepth">Depth</label>
      <input id="renderDepth" type="number" min="0" max="10" value="0" title="0 = all levels">

      <button id="refreshBtn" title="Refresh preview">↺ Refresh</button>
      <button id="exportBtn" title="Export chart image">⬇ Export…</button>
    </div>

    <!-- Burn options (shown for burn / burn-table) -->
    <div class="toolbar-row" id="burnRow" hidden>
      <label for="burnField">Field</label>
      <input id="burnField" type="text" value="cost" style="width:80px">

      <label for="burnPeriod">Period</label>
      <select id="burnPeriod">
        <option value="day">Day</option>
        <option value="week">Week</option>
        <option value="month" selected>Month</option>
        <option value="quarter">Quarter</option>
        <option value="year">Year</option>
      </select>

      <label for="burnGroup">Group</label>
      <input id="burnGroup" type="text" value="0" style="width:60px" title="total, leaf, or depth integer">

      <label for="burnDisplayFactor">Factor</label>
      <input id="burnDisplayFactor" type="text" value="1" style="width:60px" title="Display-only multiplier">
    </div>

    <!-- Gantt-only options -->
    <div class="toolbar-row" id="ganttRow">
      <label for="dateLine">Date line</label>
      <input id="dateLine" type="text" placeholder="YYYY-MM-DD or today" style="width:140px">

      <label for="dateLineColor">Color</label>
      <input id="dateLineColor" type="color" value="#C00000">

      <label for="compareFile">Compare</label>
      <button id="pickCompareBtn" title="Pick baseline JSON for compare mode">📂 Pick…</button>
      <span id="compareLabel" class="muted" style="max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"></span>
    </div>

    <!-- Table milestone options -->
    <div class="toolbar-row" id="milestoneRow" hidden>
      <label>Milestones</label>
      <label><input id="msAll" type="radio" name="ms" value="all" checked> All</label>
      <label><input id="msOnly" type="radio" name="ms" value="only"> Only</label>
      <label><input id="msNone" type="radio" name="ms" value="none"> None</label>
    </div>
  </div>

  <!-- ── Status bar ──────────────────────────────────── -->
  <div id="statusBar">
    <span id="statusText">Ready</span>
  </div>

  <!-- ── Chart output ───────────────────────────────── -->
  <div id="previewArea">
    <div id="svgContainer"></div>
    <div id="errorBox" hidden>
      <pre id="errorText"></pre>
      <button id="installBtn" hidden>Install jsonantt (pip)</button>
    </div>
  </div>

  <script nonce="${nonce}" src="${jsUri}"></script>
</body>
</html>`;
  }
}

// ---------------------------------------------------------------------------
// Types for the postMessage protocol
// ---------------------------------------------------------------------------

type WebviewMessage =
  | { type: "updateOptions"; options: Partial<RenderOptions> }
  | { type: "refresh" }
  | { type: "export" }
  | { type: "pickCompare" }
  | { type: "installJsonantt" };

type HostMessage =
  | { type: "rendering" }
  | { type: "rendered"; svgData: string }
  | { type: "error"; error: string }
  | { type: "comparePathSet"; filePath: string };

function getNonce(): string {
  let text = "";
  const possible =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  for (let i = 0; i < 32; i++) {
    text += possible.charAt(Math.floor(Math.random() * possible.length));
  }
  return text;
}
