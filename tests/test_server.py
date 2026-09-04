"""Tests for the packaged jsonantt studio web app and its local server."""
from __future__ import annotations

import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from jsonantt import server
from jsonantt.formatter import format_json_data


# ---------------------------------------------------------------------------
# Packaged assets
# ---------------------------------------------------------------------------

class TestStaticAssets:
    def test_static_root_contains_entry_point(self):
        assert server.STATIC_ROOT.joinpath("index.html").is_file()

    @pytest.mark.parametrize(
        "name",
        [
            "styles.css",
            "app.mjs",
            "model.mjs",
            "gantt.mjs",
            "table.mjs",
            "settings.mjs",
            "datepicker.mjs",
            "format.mjs",
            "highlight.mjs",
            "demo-charts.mjs",
            "export.mjs",
        ],
    )
    def test_expected_assets_are_packaged(self, name):
        assert server.STATIC_ROOT.joinpath(name).is_file()

    def test_index_wires_canvas_tabs(self):
        markup = server.STATIC_ROOT.joinpath("index.html").read_text(encoding="utf-8")
        assert 'data-canvas-tab="gantt"' in markup
        assert 'data-canvas-tab="table"' in markup
        assert 'data-canvas-tab="graph"' not in markup
        assert 'id="canvas-inspector"' in markup

    def test_index_has_no_style_source_tab(self):
        markup = server.STATIC_ROOT.joinpath("index.html").read_text(encoding="utf-8")
        assert "data-source-tab" not in markup

    def test_index_wires_chart_settings_and_highlighting(self):
        markup = server.STATIC_ROOT.joinpath("index.html").read_text(encoding="utf-8")
        assert 'id="chart-settings"' in markup
        assert 'id="settings-dialog"' in markup
        assert 'id="highlight-layer"' in markup

    def test_app_wires_table_settings_format_and_highlight_modules(self):
        source = server.STATIC_ROOT.joinpath("app.mjs").read_text(encoding="utf-8")
        for module in ("table.mjs", "settings.mjs", "format.mjs", "highlight.mjs", "datepicker.mjs"):
            assert module in source

    def test_styles_cover_table_settings_highlight_and_datepicker(self):
        css = server.STATIC_ROOT.joinpath("styles.css").read_text(encoding="utf-8")
        for selector in (".studio-table", ".settings-content", ".highlight-layer", ".tok-key", ".date-picker"):
            assert selector in css


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


class TestExportEndpoint:
    """Studio exports must be produced by the same matplotlib renderer as the CLI."""

    SAMPLE_CHART = json.dumps(
        {
            "title": "T",
            "dateformat": "%Y-%m-%d",
            "tasks": [{"name": "A", "start": "2024-01-01", "duration": "2w"}],
        }
    )

    def _post(self, base_url, mode, fmt, dpi=None):
        query = f"mode={mode}&format={fmt}"
        if dpi is not None:
            query += f"&dpi={dpi}"
        request = Request(
            f"{base_url}/api/export?{query}",
            data=self.SAMPLE_CHART.encode("utf-8"),
            method="POST",
        )
        return urlopen(request)

    def test_gantt_png_export_matches_cli_renderer(self, running_server, tmp_path):
        from jsonantt.cli import main

        with self._post(running_server, "gantt", "png", dpi=80) as response:
            assert response.headers["Content-Type"] == "image/png"
            via_endpoint = response.read()

        chart_path = tmp_path / "chart.json"
        chart_path.write_text(self.SAMPLE_CHART, encoding="utf-8")
        cli_output = tmp_path / "chart.png"
        assert main([str(chart_path), str(cli_output), "--dpi", "80"]) == 0
        assert via_endpoint == cli_output.read_bytes()

    def test_gantt_svg_export(self, running_server):
        with self._post(running_server, "gantt", "svg") as response:
            assert response.headers["Content-Type"] == "image/svg+xml"
            body = response.read()
        assert body.startswith(b"<?xml")

    def test_table_png_export(self, running_server):
        with self._post(running_server, "table", "png") as response:
            assert response.headers["Content-Type"] == "image/png"
            body = response.read()
        assert body.startswith(b"\x89PNG\r\n\x1a\n")

    def test_table_svg_export(self, running_server):
        with self._post(running_server, "table", "svg") as response:
            assert response.headers["Content-Type"] == "image/svg+xml"
            assert response.read().startswith(b"<?xml")

    def test_table_csv_export(self, running_server):
        with self._post(running_server, "table", "csv") as response:
            assert response.headers["Content-Type"] == "text/csv"
            body = response.read().decode("utf-8")
        assert body.startswith("Task,Name")

    def test_csv_export_rejected_for_gantt_mode(self, running_server):
        with pytest.raises(HTTPError) as excinfo:
            self._post(running_server, "gantt", "csv")
        assert excinfo.value.code == 400
        payload = json.loads(excinfo.value.read().decode("utf-8"))
        assert "csv" in payload["error"]

    def test_unknown_mode_is_rejected(self, running_server):
        with pytest.raises(HTTPError) as excinfo:
            self._post(running_server, "bogus", "png")
        assert excinfo.value.code == 400

    def test_unknown_format_is_rejected(self, running_server):
        with pytest.raises(HTTPError) as excinfo:
            self._post(running_server, "gantt", "bogus")
        assert excinfo.value.code == 400

    def test_invalid_json_body_is_rejected(self, running_server):
        request = Request(
            f"{running_server}/api/export?mode=gantt&format=png",
            data=b"{oops",
            method="POST",
        )
        with pytest.raises(HTTPError) as excinfo:
            urlopen(request)
        assert excinfo.value.code == 400


class TestFormatEndpoint:
    def _post(self, base_url, text):
        request = Request(
            f"{base_url}/api/format",
            data=text.encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return urlopen(request)

    def test_format_matches_cli_formatter(self, running_server):
        raw = '{"title":"caf\\u00e9","tasks":[{"name":"A","start":"2026-01-01"}]}'
        with self._post(running_server, raw) as response:
            assert response.headers["Content-Type"].startswith("application/json")
            body = response.read().decode("utf-8")
        assert body == format_json_data(json.loads(raw))

    def test_format_is_byte_identical_to_cli(self, running_server, tmp_path):
        """Studio endpoint output must be byte-for-byte identical to `jsonantt fmt`."""
        from jsonantt.cli import main

        raw = '{"b": [1, {"x": 2}], "a": "v"}'
        with self._post(running_server, raw) as response:
            via_endpoint = response.read().decode("utf-8")

        target = tmp_path / "chart.json"
        target.write_text(raw, encoding="utf-8")
        assert main(["fmt", str(target)]) == 0
        assert via_endpoint == target.read_text(encoding="utf-8")

    def test_format_rejects_invalid_json(self, running_server):
        with pytest.raises(HTTPError) as excinfo:
            self._post(running_server, "{oops")
        assert excinfo.value.code == 400
        payload = json.loads(excinfo.value.read().decode("utf-8"))
        assert "error" in payload

    def test_unknown_post_path_is_404(self, running_server):
        request = Request(f"{running_server}/api/unknown", data=b"{}", method="POST")
        with pytest.raises(HTTPError) as excinfo:
            urlopen(request)
        assert excinfo.value.code == 404
