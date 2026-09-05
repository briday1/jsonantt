"""Dependency-free HTTP server for the jsonantt studio frontend."""

from __future__ import annotations

import json
import tempfile
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

STATIC_ROOT = Path(__file__).resolve().with_name("web")
_RENDER_LOCK = threading.RLock()  # Matplotlib is shared by preview/export threads.

_EXPORT_CONTENT_TYPES = {
    "png": "image/png",
    "svg": "image/svg+xml",
    "csv": "text/csv",
}

# Fixed, hardcoded output filenames for every valid (mode, format) combination.
# Using a literal allow-list (rather than interpolating the request's mode/format
# strings directly) keeps the on-disk export path and the Content-Disposition
# header free of any request-controlled data.
_EXPORT_FILENAMES = {
    (mode, fmt): f"{mode}.{fmt}"
    for mode in ("gantt", "table", "burn", "burndown", "burnup", "burn-table")
    for fmt in ("png", "svg", "csv")
}


class StudioRequestHandler(SimpleHTTPRequestHandler):
    """Serve the packaged studio assets plus a small health endpoint."""

    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".mjs": "text/javascript"}

    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=str(directory or STATIC_ROOT), **kwargs)

    @property
    def server_version(self) -> str:  # pragma: no cover - trivial
        from . import __version__

        return f"jsonantt/{__version__}"

    def do_GET(self):  # noqa: N802 - required by BaseHTTPRequestHandler
        from . import __version__

        path = urlsplit(self.path).path
        if path == "/healthz":
            payload = json.dumps({"status": "ok", "version": __version__, "capabilities": ["burn-preview", "chart-preview"]})
            return self._send_text(payload, "application/json; charset=utf-8")
        if path == "/__project.json" and getattr(self.server, "project_json", None) is not None:
            return self._send_text(self.server.project_json, "application/json; charset=utf-8")
        return super().do_GET()

    def do_POST(self):  # noqa: N802 - required by BaseHTTPRequestHandler
        split = urlsplit(self.path)
        if split.path == "/api/format":
            return self._handle_format()
        if split.path == "/api/export":
            return self._handle_export(parse_qs(split.query))
        if split.path == "/api/preview":
            return self._handle_export(parse_qs(split.query), preview=True)
        self.send_error(404, "Not Found")

    def _handle_export(self, query, preview=False) -> None:
        """Render the request body (a chart JSON document) via the CLI's
        matplotlib-based renderer and return the resulting file bytes.

        This is the *only* export path the studio uses: it calls the same
        ``jsonantt.renderer`` functions used by ``jsonantt`` on the command
        line, so studio exports are byte-for-byte what the CLI would produce.
        """
        from .parser import parse_chart
        from .renderer import render_burn_chart, render_burn_table, render_chart, render_table

        mode = (query.get("mode") or ["gantt"])[0]
        fmt = (query.get("format") or ["png"])[0].lower()
        if preview:
            fmt = 'svg'
        try:
            dpi = int((query.get("dpi") or ["150"])[0])
        except ValueError:
            dpi = 150

        if mode not in {"gantt", "table", "burn", "burndown", "burnup", "burn-table"}:
            return self._send_json_error(f"unknown export mode: {mode!r}", 400)
        if fmt not in _EXPORT_CONTENT_TYPES:
            return self._send_json_error(f"unknown export format: {fmt!r}", 400)
        if fmt == "csv" and mode not in {"table", "burn-table"}:
            return self._send_json_error(
                ".csv export is only supported for table output", 400
            )
        filename = _EXPORT_FILENAMES[(mode, fmt)]
        table_filter = (query.get("table_filter") or ["all"])[0]
        if table_filter not in {"all", "milestones", "tasks"}:
            return self._send_json_error("unknown table filter", 400)
        try:
            render_depth = int(query["render_depth"][0]) if query.get("render_depth") else None
            if render_depth is not None and render_depth < 0:
                raise ValueError
        except ValueError:
            return self._send_json_error("render depth must be a non-negative integer", 400)
        burn_options = {
            "field": (query.get("burn_field") or ["cost"])[0],
            "period": (query.get("burn_period") or ["month"])[0],
            "group_by": (query.get("burn_group") or ["0"])[0],
            "display_factor": (query.get("burn_factor") or ["1"])[0],
        }

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        body = self.rfile.read(max(0, length))
        try:
            data = json.loads(body.decode("utf-8"))
            config = parse_chart(data)
        except (ValueError, UnicodeDecodeError, KeyError) as exc:
            return self._send_json_error(f"invalid chart JSON: {exc}", 400)

        with _RENDER_LOCK, tempfile.TemporaryDirectory() as tmp_dir:
            output_path = str(Path(tmp_dir) / filename)
            try:
                if mode == "table":
                    render_table(config, output_path, dpi=dpi, render_depth=render_depth,
                                 milestones_only=table_filter == "milestones",
                                 no_milestones=table_filter == "tasks", interactive=preview)
                elif mode in {"burn", "burndown", "burnup"}:
                    render_burn_chart(config, output_path, dpi=dpi, **burn_options, interactive=preview,
                                      display={"burndown": "remaining", "burnup": "cumulative"}.get(mode, (query.get("burn_display") or ["spend"])[0]))
                elif mode == "burn-table":
                    render_burn_table(config, output_path, dpi=dpi, **burn_options, interactive=preview)
                else:
                    render_chart(config, output_path, dpi=dpi, render_depth=render_depth, interactive=preview)
            except Exception as exc:  # noqa: BLE001
                return self._send_json_error(f"failed to render export: {exc}", 400)

            payload = Path(output_path).read_bytes()

        self.send_response(200)
        self.send_header("Content-Type", _EXPORT_CONTENT_TYPES[fmt])
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(payload)))
        if mode == "table":
            self.send_header("X-Jsonantt-Table-Filter", table_filter)
        self.end_headers()
        self.wfile.write(payload)

    def _send_json_error(self, message: str, status: int) -> None:
        payload = json.dumps({"error": message})
        self._send_text(payload, "application/json; charset=utf-8", status=status)

    def _handle_format(self) -> None:
        """Format the request body with the canonical (CLI-identical) formatter."""
        from .formatter import format_json_text

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        body = self.rfile.read(max(0, length))
        try:
            formatted = format_json_text(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            payload = json.dumps({"error": str(exc)})
            return self._send_text(payload, "application/json; charset=utf-8", status=400)
        self._send_text(formatted, "application/json; charset=utf-8")

    def _send_text(self, value: str, content_type: str, status: int = 200) -> None:
        payload = value.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def log_message(self, format, *args):  # noqa: A002 - signature fixed by base class
        if not getattr(self.server, "quiet", False):
            super().log_message(format, *args)


class StudioServer(ThreadingHTTPServer):
    """Threaded development server with clean process shutdown."""

    allow_reuse_address = True
    daemon_threads = True
    quiet = False
    project_json = None


def create_server(host: str = "127.0.0.1", port: int = 4174, *, quiet: bool = False) -> StudioServer:
    """Create a configured server without starting its blocking loop."""
    if not STATIC_ROOT.joinpath("index.html").is_file():
        raise RuntimeError(f"Packaged web assets are missing from {STATIC_ROOT}.")
    server = StudioServer((host, port), StudioRequestHandler)
    server.quiet = quiet
    return server


def serve(
    host: str = "127.0.0.1",
    port: int = 4174,
    *,
    open_browser: bool = True,
    quiet: bool = False,
    json_path: str = None,
) -> str:
    """Run the studio until interrupted and return the bound URL."""
    from . import __version__

    server = create_server(host, port, quiet=quiet)
    query = ""
    if json_path:
        server.project_json = Path(json_path).read_text(encoding="utf-8")
        query = "?project=1"
    actual_port = server.server_address[1]
    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{browser_host}:{actual_port}/{query}"
    print(f"jsonantt {__version__}: {url}")
    print("Press Ctrl+C to stop.")

    if open_browser:
        threading.Timer(0.25, webbrowser.open, args=(url,)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping jsonantt studio.")
    finally:
        server.server_close()
    return url
