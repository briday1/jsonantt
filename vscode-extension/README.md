# jsonantt VS Code Extension

Live-preview [jsonantt](https://jsonantt.readthedocs.io/) Gantt charts, task
tables, and burn charts directly inside VS Code — no terminal required.

---

## Features

- **Live preview pane** — opens beside the active JSON editor.
- **Multiple chart types** — Gantt chart, task table, burn chart, burn table.
- **Toolbar controls** — render depth, burn field/period/group, date line,
  compare mode, milestone filters.
- **Auto-preview modes** — re-render on every keystroke (debounced), on save,
  or manually via the Refresh button.
- **Export** — save the rendered SVG to disk from inside VS Code.

---

## Requirements

`jsonantt` must be installed in the Python environment that VS Code is using.
The extension automatically picks up the interpreter selected in the VS Code
Python extension (the one shown in the status bar), so installing into a virtual
environment just works:

```bash
pip install jsonantt
```

If you need to override which Python is used, set `jsonantt.pythonPath` to the
full path of a Python executable — for example
`/home/you/.venv/bin/python` or `C:\Users\you\.venv\Scripts\python.exe`.
Leave it blank (the default) to let the extension use VS Code's selected
interpreter automatically.

---

## Getting Started

1. Open a `.json` file that describes a jsonantt chart (see the
   [examples](https://jsonantt.readthedocs.io/en/latest/examples.html)).
2. Click the **graph icon** (⊞) in the editor title bar, or open the Command
   Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`) and run
   **jsonantt: Open jsonantt Preview**.
3. The preview pane opens beside your editor.  Edit the JSON and the chart
   updates automatically (based on the `jsonantt.autoPreview` setting).

---

## Extension Settings

| Setting | Type | Default | Description |
|---|---|---|---|
| `jsonantt.pythonPath` | string | `""` | Path to the Python executable with jsonantt installed. |
| `jsonantt.autoPreview` | `"onType"` \| `"onSave"` \| `"manual"` | `"onSave"` | When to re-render. |
| `jsonantt.defaultChartType` | `"chart"` \| `"table"` \| `"burn"` \| `"burn-table"` | `"chart"` | Chart type shown when the preview opens. |
| `jsonantt.defaultDpi` | number | `150` | Image DPI for raster output. |

---

## Development

```bash
cd vscode-extension
npm install
npm run compile
```

To launch a development host with the extension loaded, open the
`vscode-extension/` folder in VS Code and press **F5**.

To package the extension as a `.vsix` file:

```bash
npm run package
```

---

## Repository Layout

```
vscode-extension/
  package.json          Extension manifest
  tsconfig.json
  src/
    extension.ts        Activation, command registration, document listeners
    previewPanel.ts     WebviewPanel lifecycle and postMessage bridge
    renderer.ts         Spawns the jsonantt CLI, returns SVG data
    webview/
      panel.css         Webview styles (VS Code CSS variables)
      panel.js          Webview-side JS (toolbar, postMessage)
```
