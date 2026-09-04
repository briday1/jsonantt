"""Tests for the packaged jsonantt studio web app and its local server."""
from __future__ import annotations

import json
import threading
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from jsonantt import server


# ---------------------------------------------------------------------------
# Packaged assets
# ---------------------------------------------------------------------------

class TestStaticAssets:
    def test_static_root_contains_entry_point(self):
        assert server.STATIC_ROOT.joinpath("index.html").is_file()

    @pytest.mark.parametrize(
        "name",
        ["styles.css", "app.mjs", "model.mjs", "gantt.mjs", "graph.mjs", "demo-charts.mjs"],
    )
    def test_expected_assets_are_packaged(self, name):
        assert server.STATIC_ROOT.joinpath(name).is_file()

    def test_index_wires_canvas_tabs(self):
        markup = server.STATIC_ROOT.joinpath("index.html").read_text(encoding="utf-8")
        assert 'data-canvas-tab="gantt"' in markup
        assert 'data-canvas-tab="graph"' in markup
        assert 'id="canvas-inspector"' in markup


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

@pytest.fixture()
def running_server():
    httpd = server.create_server("127.0.0.1", 0, quiet=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


class TestStudioServer:
    def test_healthz_reports_version(self, running_server):
        with urlopen(f"{running_server}/healthz") as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["status"] == "ok"
        assert payload["version"]

    def test_index_is_served(self, running_server):
        with urlopen(f"{running_server}/index.html") as response:
            body = response.read().decode("utf-8")
        assert "jsonantt studio" in body

    def test_modules_use_javascript_content_type(self, running_server):
        with urlopen(f"{running_server}/app.mjs") as response:
            assert response.headers["Content-Type"].startswith("text/javascript")

    def test_project_json_is_served_when_configured(self):
        httpd = server.create_server("127.0.0.1", 0, quiet=True)
        httpd.project_json = '{"title": "Attached"}'
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{httpd.server_address[1]}/__project.json"
            with urlopen(url) as response:
                assert json.loads(response.read().decode("utf-8"))["title"] == "Attached"
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)

    def test_project_json_is_absent_by_default(self, running_server):
        with pytest.raises(HTTPError) as excinfo:
            urlopen(f"{running_server}/__project.json")
        assert excinfo.value.code == 404
