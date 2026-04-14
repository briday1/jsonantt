/**
 * renderer.ts – spawns the jsonantt CLI in a child process and returns SVG bytes.
 *
 * Resolution order for the jsonantt executable:
 *   1. Bundled PyInstaller binary shipped inside the .vsix  (bin/<platform>-<arch>/jsonantt[.exe])
 *   2. jsonantt.pythonPath setting  →  <pythonPath> -m jsonantt
 *   3. "jsonantt" binary on PATH
 *   4. "python3 -m jsonantt" on PATH
 *   5. "python -m jsonantt" on PATH
 */
import * as cp from "child_process";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import * as vscode from "vscode";

export interface RenderOptions {
  chartType: "chart" | "table" | "burn" | "burn-table";
  renderDepth: number;
  burnField: string;
  burnPeriod: string;
  burnGroup: string;
  burnDisplayFactor: string;
  dateLine: string;
  dateLineColor: string;
  dpi: number;
  comparePath: string;
  milestonesOnly: boolean;
  noMilestones: boolean;
}

export interface RenderResult {
  ok: boolean;
  svgData?: string;
  error?: string;
}

/**
 * Render the JSON content using the jsonantt CLI, returning the SVG as a string.
 *
 * @param jsonText       Raw JSON text from the editor buffer.
 * @param opts           Chart options selected in the webview.
 * @param extensionPath  Absolute path to the installed extension directory.
 */
export async function renderChart(
  jsonText: string,
  opts: RenderOptions,
  extensionPath: string
): Promise<RenderResult> {
  // Write the editor buffer to a temp input file.
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "jsonantt-"));
  const inputPath = path.join(tmpDir, "input.json");
  const outputPath = path.join(tmpDir, "output.svg");

  try {
    fs.writeFileSync(inputPath, jsonText, "utf8");

    const args = buildArgs(inputPath, outputPath, opts);
    const { cmd, cmdArgs } = resolveCommand(args, extensionPath);

    await spawnCommand(cmd, cmdArgs);

    const svgData = fs.readFileSync(outputPath, "utf8");
    return { ok: true, svgData };
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return { ok: false, error: msg };
  } finally {
    try {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    } catch {
      // Best-effort cleanup.
    }
  }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function buildArgs(
  inputPath: string,
  outputPath: string,
  opts: RenderOptions
): string[] {
  const args: string[] = [inputPath, outputPath];

  // Chart type flags.
  if (opts.chartType === "table") {
    args.push("--table");
  } else if (opts.chartType === "burn") {
    args.push("--burn");
  } else if (opts.chartType === "burn-table") {
    args.push("--burn-table");
  }

  // Render depth (0 = all).
  if (opts.renderDepth > 0) {
    args.push("-r", String(opts.renderDepth));
  }

  // Burn options.
  if (opts.chartType === "burn" || opts.chartType === "burn-table") {
    if (opts.burnField) {
      args.push("--burn-field", opts.burnField);
    }
    if (opts.burnPeriod) {
      args.push("--burn-period", opts.burnPeriod);
    }
    if (opts.burnGroup) {
      args.push("--burn-group", opts.burnGroup);
    }
    if (opts.burnDisplayFactor && opts.burnDisplayFactor !== "1") {
      args.push("--burn-display-factor", opts.burnDisplayFactor);
    }
  }

  // Date line (Gantt chart only).
  if (opts.dateLine && opts.chartType === "chart") {
    args.push("--date-line", opts.dateLine);
    if (opts.dateLineColor) {
      args.push("--date-line-color", opts.dateLineColor);
    }
  }

  // DPI (only meaningful for raster; SVG ignores it but the CLI accepts it).
  args.push("--dpi", String(opts.dpi));

  // Compare mode.
  if (opts.comparePath && opts.chartType === "chart") {
    args.push("--compare", opts.comparePath);
  }

  // Milestone filters (table only).
  if (opts.chartType === "table") {
    if (opts.milestonesOnly) {
      args.push("--milestones-only");
    } else if (opts.noMilestones) {
      args.push("--no-milestones");
    }
  }

  return args;
}

interface ResolvedCommand {
  cmd: string;
  cmdArgs: string[];
}

/**
 * Resolve which executable to use, returning the command and full argument list.
 * The first element of `jsonanttArgs` is the jsonantt input file path.
 */
function resolveCommand(jsonanttArgs: string[], extensionPath: string): ResolvedCommand {
  // 1. Bundled binary shipped inside the .vsix – no user install needed.
  const bundledBin = getBundledBinaryPath(extensionPath);
  if (bundledBin && fs.existsSync(bundledBin)) {
    return { cmd: bundledBin, cmdArgs: jsonanttArgs };
  }

  const cfg = vscode.workspace.getConfiguration("jsonantt");
  const pythonPath = cfg.get<string>("pythonPath", "").trim();

  if (pythonPath) {
    return { cmd: pythonPath, cmdArgs: ["-m", "jsonantt", ...jsonanttArgs] };
  }

  // Try the standalone "jsonantt" binary first (fastest).
  if (commandExistsSync("jsonantt")) {
    return { cmd: "jsonantt", cmdArgs: jsonanttArgs };
  }

  // Fall back to python module invocation.
  const python = commandExistsSync("python3") ? "python3" : "python";
  return { cmd: python, cmdArgs: ["-m", "jsonantt", ...jsonanttArgs] };
}

/**
 * Return the path to the platform-specific bundled binary, or null if the
 * current platform/arch combination is not recognised.
 *
 * Binaries live at:
 *   <extensionPath>/bin/<process.platform>-<process.arch>/jsonantt[.exe]
 *
 * e.g.  bin/linux-x64/jsonantt
 *       bin/darwin-arm64/jsonantt
 *       bin/win32-x64/jsonantt.exe
 */
function getBundledBinaryPath(extensionPath: string): string | null {
  const platformKey = `${process.platform}-${process.arch}`;
  const exeName = process.platform === "win32" ? "jsonantt.exe" : "jsonantt";
  return path.join(extensionPath, "bin", platformKey, exeName);
}

/** Synchronously check whether a command exists on PATH. */
function commandExistsSync(cmd: string): boolean {
  try {
    const which = process.platform === "win32" ? "where" : "which";
    cp.execFileSync(which, [cmd], { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

/** Spawn a command and resolve/reject based on exit code and stderr. */
function spawnCommand(cmd: string, args: string[]): Promise<void> {
  return new Promise((resolve, reject) => {
    const proc = cp.spawn(cmd, args, { shell: false });
    const stderrChunks: Buffer[] = [];

    proc.stderr.on("data", (chunk: Buffer) => stderrChunks.push(chunk));

    proc.on("error", (err) => {
      const hint =
        err.message.includes("ENOENT") || err.message.includes("not found")
          ? "\n\nHint: Install jsonantt with `pip install jsonantt` or set the " +
            '"jsonantt.pythonPath" setting to your Python executable.'
          : "";
      reject(new Error(`Failed to start jsonantt: ${err.message}${hint}`));
    });

    proc.on("close", (code) => {
      if (code === 0) {
        resolve();
      } else {
        const stderr = Buffer.concat(stderrChunks).toString("utf8").trim();
        reject(new Error(stderr || `jsonantt exited with code ${code}`));
      }
    });
  });
}
