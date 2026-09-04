"""Dependency-free HTTP server for the jsonantt studio frontend."""

from __future__ import annotations

import json
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

STATIC_ROOT = Path(__file__).resolve().with_name("web")


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
            payload = json.dumps({"status": "ok", "version": __version__})
            return self._send_text(payload, "application/json; charset=utf-8")
        if path == "/__project.json" and getattr(self.server, "project_json", None) is not None:
            return self._send_text(self.server.project_json, "application/json; charset=utf-8")
        return super().do_GET()

    def do_POST(self):  # noqa: N802 - required by BaseHTTPRequestHandler
        path = urlsplit(self.path).path
        if path == "/api/format":
            return self._handle_format()
        self.send_error(404, "Not Found")

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
