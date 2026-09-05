"""Dependency-free HTTP server for the jsonantt studio frontend."""

from __future__ import annotations

import json
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from .api import MODES, FORMATS, TABLE_MODES, render_document

STATIC_ROOT = Path(__file__).resolve().with_name("web")

_EXPORT_CONTENT_TYPES = {
    "png": "image/png",
    "svg": "image/svg+xml",
    "csv": "text/csv",
}

# HTTP names map directly to the shared Python/Pyodide API's options.
_QUERY_OPTIONS = {
    'mode': 'mode', 'format': 'format', 'dpi': 'dpi',
    'render_depth': 'renderDepth', 'table_filter': 'tableFilter',
    'burn_field': 'burn.field', 'burn_period': 'burn.period',
    'burn_group': 'burn.group', 'burn_factor': 'burn.factor', 'burn_display': 'burn.display',
    'date_line': 'dateLine', 'date_line_color': 'dateLineColor',
    **{key: f'valueFormat.{key}' for key in
       ('value_scale', 'value_prefix', 'value_suffix', 'value_decimals', 'value_fields')},
}

# Fixed, hardcoded output filenames for every valid (mode, format) combination.
# Using a literal allow-list (rather than interpolating the request's mode/format
# strings directly) keeps the on-disk export path and the Content-Disposition
# header free of any request-controlled data.
_EXPORT_FILENAMES = {
    (mode, fmt): f"{mode}.{fmt}"
    for mode in MODES
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
        if path in {'/api/files', '/api/project', '/api/history'}:
            origin = self.headers.get('Origin')
            if (origin and urlsplit(origin).netloc != self.headers.get('Host')) or self.headers.get('Sec-Fetch-Site') == 'cross-site':
                return self._send_json_error('Local file APIs require a same-origin request.', 403)
            # Prevent DNS rebinding to a loopback-bound development server.
            host = urlsplit('//'+self.headers.get('Host', '')).hostname
            if self.server.server_address[0] in {'127.0.0.1', '::1'} and host not in {'localhost', '127.0.0.1', '::1'}:
                return self._send_json_error('Invalid host for local file access.', 403)
        if path == "/healthz":
            payload = json.dumps({"status": "ok", "version": __version__, "capabilities": ["burn-preview", "chart-preview", "local-files", "git-history"],
                                  'project_path': str(self.server.project_path) if self.server.project_path else None})
            return self._send_text(payload, "application/json; charset=utf-8")
        if path == '/api':
            payload = {'version': __version__, 'endpoints': {
                'POST /api/export': 'Chart JSON to file bytes; comparison modes take {planned, actual}.',
                'POST /api/preview': 'Chart JSON to SVG; single-document modes include selection targets; comparison is read-only.',
                'POST /api/format': 'JSON to canonical two-space-indented JSON.',
                'POST /api/compose': 'Append task trees from uploaded JSON files into a portable document.',
                'GET /api/history': 'Attached file history; ?revision=SHA returns that JSON version.',
                'GET /api/files?path=directory': 'Browse local directories and JSON files.',
                'GET /api/project?path=file.json': 'Read a local chart with its resolved full path.',
            }, 'modes': MODES, 'formats': FORMATS, 'csv_modes': TABLE_MODES,
                'preview_modes': MODES,
                'query_parameters': list(_QUERY_OPTIONS),
                'settings': 'All chart, task, arrow and style settings belong in the JSON body.'}
            return self._send_text(json.dumps(payload), 'application/json; charset=utf-8')
        if path == '/api/history':
            from .history import file_history, revision_source
            query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
            project = (query.get('path') or [getattr(self.server, 'project_path', None)])[0]
            if project is None:
                return self._send_json_error('Open a file with jsonantt serve project.json to use Git history.', 404)
            try:
                if set(query) - {'revision', 'path'} or any(len(values) != 1 for values in query.values()):
                    raise ValueError('Use only path and an optional revision parameter')
                if Path(project).suffix.lower() != '.json':
                    raise ValueError('Choose a JSON file')
                if 'revision' in query:
                    source = revision_source(project, query['revision'][0])
                    from .parser import parse_chart
                    parse_chart(json.loads(source))
                    return self._send_text(source, 'application/json; charset=utf-8')
                _, entries = file_history(project)
                return self._send_text(json.dumps({'file': Path(project).name, 'revisions': entries, 'limit': 200}), 'application/json; charset=utf-8')
            except Exception as exc:  # noqa: BLE001
                return self._send_json_error(str(exc), 400)
        if path in {'/api/files', '/api/project'}:
            try:
                query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                if set(query) - {'path'} or any(len(values) != 1 for values in query.values()):
                    raise ValueError('Use only a path parameter')
                default = Path(self.server.project_path).parent if self.server.project_path else Path.cwd()
                target = Path((query.get('path') or [str(default)])[0]).expanduser().resolve()
                if path == '/api/project':
                    if target.suffix.lower() != '.json' or not target.is_file():
                        raise ValueError('Choose an existing JSON file')
                    source = target.read_text(encoding='utf-8')
                    from .parser import parse_chart
                    parse_chart(json.loads(source))
                    result = {'path': str(target), 'source': source}
                else:
                    entries = sorted((entry for entry in target.iterdir() if not entry.name.startswith('.') and (entry.is_dir() or entry.suffix.lower() == '.json')),
                                     key=lambda item: (not item.is_dir(), item.name.casefold()))
                    result = {'path': str(target), 'parent': str(target.parent),
                              'entries': [{'name': item.name, 'path': str(item), 'directory': item.is_dir()} for item in entries[:1000]],
                              'truncated': len(entries) > 1000}
                return self._send_text(json.dumps(result), 'application/json; charset=utf-8')
            except Exception as exc:  # noqa: BLE001
                return self._send_json_error(str(exc), 400)
        if path == "/__project.json" and getattr(self.server, "project_json", None) is not None:
            return self._send_text(self.server.project_json, "application/json; charset=utf-8")
        return super().do_GET()

    def do_POST(self):  # noqa: N802 - required by BaseHTTPRequestHandler
        split = urlsplit(self.path)
        if split.path == "/api/format":
            return self._handle_format()
        if split.path == '/api/compose':
            from .composition import compose_document
            try:
                length = int(self.headers.get('Content-Length') or 0)
                payload = json.loads(self.rfile.read(max(0, length)).decode('utf-8'))
                result = compose_document(**payload)
                return self._send_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', 'application/json; charset=utf-8')
            except Exception as exc:  # noqa: BLE001
                return self._send_json_error(str(exc), 400)
        if split.path == "/api/export":
            return self._handle_export(parse_qs(split.query, keep_blank_values=True))
        if split.path == "/api/preview":
            return self._handle_export(parse_qs(split.query, keep_blank_values=True), preview=True)
        self.send_error(404, "Not Found")

    def _handle_export(self, query, preview=False) -> None:
        """Render the request body (a chart JSON document) via the CLI's
        matplotlib-based renderer and return the resulting file bytes.

        This is the *only* export path the studio uses: it calls the same
        ``jsonantt.renderer`` functions used by ``jsonantt`` on the command
        line, so studio exports are byte-for-byte what the CLI would produce.
        """
        unknown = set(query) - set(_QUERY_OPTIONS)
        if unknown:
            return self._send_json_error(f'unknown query parameters: {sorted(unknown)}', 400)
        if any(len(values) != 1 for values in query.values()):
            return self._send_json_error('query parameters must not be repeated', 400)
        mode = (query.get("mode") or ["gantt"])[0]
        fmt = (query.get("format") or ["png"])[0].lower()
        if preview:
            fmt = 'svg'
        if mode not in MODES:
            return self._send_json_error(f"unknown export mode: {mode!r}", 400)
        if fmt not in _EXPORT_CONTENT_TYPES:
            return self._send_json_error(f"unknown export format: {fmt!r}", 400)
        if fmt == "csv" and mode not in TABLE_MODES:
            return self._send_json_error(
                ".csv export is only supported for table output", 400
            )
        filename = _EXPORT_FILENAMES[(mode, fmt)]
        table_filter = (query.get("table_filter") or ["all"])[0]
        options = {'mode': mode, 'format': fmt, 'interactive': preview}
        for key, values in query.items():
            target = _QUERY_OPTIONS[key]
            if target in {'mode', 'format'}:
                continue
            value = values[0]
            if key == 'value_fields':
                value = [part.strip() for part in value.split(',') if part.strip()]
            if key == 'value_decimals':
                try:
                    value = int(value)
                except ValueError:
                    return self._send_json_error('value_decimals must be an integer', 400)
            if '.' in target:
                group, field = target.split('.')
                options.setdefault(group, {})[field] = value
            else:
                options[target] = value

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        body = self.rfile.read(max(0, length))
        try:
            data = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, KeyError) as exc:
            return self._send_json_error(f"invalid chart JSON: {exc}", 400)

        try:
            payload = render_document(data, options)
        except Exception as exc:  # noqa: BLE001
            return self._send_json_error(f'failed to render export: {exc}', 400)

        self.send_response(200)
        self.send_header("Content-Type", _EXPORT_CONTENT_TYPES[fmt])
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(payload)))
        if mode in {"table", "compare-table"}:
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
    project_path = None


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
        server.project_path = Path(json_path).resolve()
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
