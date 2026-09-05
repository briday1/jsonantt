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
    def test_milestone_svg_does_not_inherit_chart_background(self):
        import re
        css = server.STATIC_ROOT.joinpath('styles.css').read_text()
        # Chart framing must never apply to SVGs nested inside table rows.
        assert '#canvas > svg {' in css
        assert not re.search(r'#canvas\s+svg\s*\{', css)
        marker_rule = re.search(r'\.table-milestone-marker\s*\{([^}]+)\}', css).group(1)
        assert 'background: transparent' in marker_rule
        assert 'box-shadow: none' in marker_rule

    def test_static_root_contains_entry_point(self):
        assert server.STATIC_ROOT.joinpath("index.html").is_file()

    @pytest.mark.parametrize(
        "name",
        [
            "styles.css",
            "app.mjs",
            "model.mjs",
            "settings.mjs",
            "style-options.mjs",
            "value-format.mjs",
            "inspector-drag.mjs",
            "datepicker.mjs",
            "format.mjs",
            "highlight.mjs",
            "demo-charts.mjs",
            "export.mjs",
            "burn.mjs",
            "preview.mjs",
            "python-client.mjs",
            "python-runtime.mjs",
            "python-worker.mjs",
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
        inspector = markup.split('id="canvas-inspector"', 1)[1].split('</section>', 1)[0]
        assert inspector.index('id="delete-selection"') > inspector.index('id="inspector-content"')
        assert inspector.index('id="close-inspector"') > inspector.index('id="inspector-content"')

    def test_index_has_no_style_source_tab(self):
        markup = server.STATIC_ROOT.joinpath("index.html").read_text(encoding="utf-8")
        assert "data-source-tab" not in markup

    def test_index_wires_chart_settings_and_highlighting(self):
        markup = server.STATIC_ROOT.joinpath("index.html").read_text(encoding="utf-8")
        assert 'id="chart-settings"' in markup
        assert 'id="settings-dialog"' in markup
        assert 'id="highlight-layer"' in markup
        assert 'id="export-dialog"' in markup
        assert 'id="export-dpi"' in markup

    def test_demos_are_url_driven_not_a_toolbar_menu(self):
        markup = server.STATIC_ROOT.joinpath("index.html").read_text(encoding="utf-8")
        source = server.STATIC_ROOT.joinpath("app.mjs").read_text(encoding="utf-8")
        demos = server.STATIC_ROOT.joinpath("demo-charts.mjs").read_text(encoding="utf-8")
        assert 'examples-popover' not in markup
        assert "params.get('demo')" in source
        assert 'description:' in demos
        assert '1: STARTER, 2: MILESTONE_DEMO, 3: COST_DEMO' in demos

    def test_app_wires_table_settings_format_and_highlight_modules(self):
        source = server.STATIC_ROOT.joinpath("app.mjs").read_text(encoding="utf-8")
        for module in ("preview.mjs", "settings.mjs", "format.mjs", "highlight.mjs", "datepicker.mjs"):
            assert module in source
        assert 'applyDuration' in source
        assert 'commitSynchronized' in source

    def test_chart_display_options_live_in_chart_settings(self):
        markup = server.STATIC_ROOT.joinpath("index.html").read_text(encoding="utf-8")
        settings = server.STATIC_ROOT.joinpath("style-options.mjs").read_text(encoding="utf-8")
        assert 'id="toggle-arrows"' not in markup
        assert 'id="toggle-today"' not in markup
        assert 'Show dependency arrows' in settings
        assert "Show today's date" in settings

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
        assert 'burn-preview' in payload['capabilities']
        assert 'chart-preview' in payload['capabilities']

    @pytest.mark.parametrize('mode', ['burn', 'burndown', 'burnup', 'burn-table'])
    def test_interactive_burn_preview_endpoint(self, running_server, mode):
        from tests.test_burn_preview import SOURCE
        request = Request(f'{running_server}/api/preview?mode={mode}&burn_period=quarter&burn_group=leaf',
                          data=json.dumps(SOURCE).encode(), headers={'Content-Type': 'application/json'})
        with urlopen(request) as response:
            assert response.headers['Content-Type'].startswith('image/svg+xml')
            svg = response.read().decode()
        assert 'studio-series-1.1--' in svg
        assert 'studio-series-2--' in svg
        assert '<image' not in svg
        if mode == 'burnup':
            assert 'studio-series-1.1--budget' in svg

    @pytest.mark.parametrize('mode,query,expected,excluded', [
        ('gantt', '', 'studio-arrow-0--shape-', ''),
        ('gantt', '&render_depth=1', 'studio-task-1.2--rolled-', 'studio-arrow-0--'),
        ('table', '', 'studio-task-1.1--cell-', ''),
        ('table', '&table_filter=milestones', 'studio-task-1.2--cell-', 'studio-task-1.1--'),
        ('table', '&table_filter=tasks', 'studio-task-1.1--cell-', 'studio-task-1.2--'),
    ])
    def test_gantt_table_preview_endpoint(self, running_server, mode, query, expected, excluded):
        from tests.test_burn_preview import CHART_SOURCE
        request = Request(f'{running_server}/api/preview?mode={mode}{query}', data=json.dumps(CHART_SOURCE).encode())
        with urlopen(request) as response:
            assert response.headers['Content-Type'].startswith('image/svg+xml')
            svg = response.read().decode()
            if mode == 'table':
                assert response.headers['X-Jsonantt-Table-Filter']
        assert expected in svg
        assert not excluded or excluded not in svg
        assert '<image' not in svg

    def test_preview_rejects_unknown_mode(self, running_server):
        request = Request(f'{running_server}/api/preview?mode=unknown', data=b'{}')
        with pytest.raises(HTTPError) as error:
            urlopen(request)
        assert error.value.code == 400

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

    def test_gantt_svg_export_includes_colored_dependency_arrow_and_head(self, running_server):
        source = json.dumps({
            "tasks": [
                {"id": "a", "name": "A", "start": "2026-01-01", "end": "2026-02-01"},
                {"id": "b", "name": "B", "start": "2026-02-15", "end": "2026-03-01"},
            ],
            "arrows": [{"from": "a", "to": "b", "color": "#12AB34"}],
        })
        request = Request(
            f"{running_server}/api/export?mode=gantt&format=svg",
            data=source.encode("utf-8"),
            method="POST",
        )
        with urlopen(request) as response:
            body = response.read().decode("utf-8").lower()
        # Matplotlib emits the curve and arrowhead separately with the same color.
        assert body.count("#12ab34") >= 2

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


class TestCanvasViewExports:
    SOURCE = {
        'tasks': [
            {'name': 'Work', 'start': '2026-01-01', 'end': '2026-03-01', 'cost': 600, 'effort': 30},
            {'name': 'Gate', 'milestone': True, 'date': '2026-03-15', 'cost': 60, 'effort': 3},
        ],
    }

    @pytest.mark.parametrize('filter_name,names', [
        ('all', ['Work', 'Gate']), ('milestones', ['Gate']), ('tasks', ['Work']),
    ])
    def test_table_csv_uses_canvas_filter(self, running_server, filter_name, names):
        import csv
        import io
        request = Request(f'{running_server}/api/export?mode=table&format=csv&table_filter={filter_name}',
                          data=json.dumps(self.SOURCE).encode(), method='POST')
        with urlopen(request) as response:
            assert response.headers['X-Jsonantt-Table-Filter'] == filter_name
            rows = list(csv.DictReader(io.StringIO(response.read().decode())))
        assert [row['Name'] for row in rows] == names

    @pytest.mark.parametrize('filter_name,flag', [
        ('all', None), ('milestones', '--milestones-only'), ('tasks', '--no-milestones'),
    ])
    def test_table_png_filter_matches_cli(self, running_server, tmp_path, filter_name, flag):
        from jsonantt.cli import main
        request = Request(f'{running_server}/api/export?mode=table&format=png&dpi=80&table_filter={filter_name}',
                          data=json.dumps(self.SOURCE).encode(), method='POST')
        with urlopen(request) as response:
            assert response.headers['X-Jsonantt-Table-Filter'] == filter_name
            actual = response.read()
        source = tmp_path / 'source.json'
        source.write_text(json.dumps(self.SOURCE))
        target = tmp_path / 'expected.png'
        args = [str(source), str(target), '--table', '--dpi', '80']
        if flag:
            args.append(flag)
        assert main(args) == 0
        assert actual == target.read_bytes()

    @pytest.mark.parametrize('filter_name,names,absent', [
        ('all', ['Work', 'Gate'], []), ('milestones', ['Gate'], ['Work']), ('tasks', ['Work'], ['Gate']),
    ])
    def test_table_svg_filter(self, running_server, filter_name, names, absent):
        request = Request(f'{running_server}/api/export?mode=table&format=svg&table_filter={filter_name}',
                          data=json.dumps(self.SOURCE).encode(), method='POST')
        with urlopen(request) as response:
            svg = response.read().decode()
        for name in names:
            assert f'<!-- {name} -->' in svg
        for name in absent:
            assert f'<!-- {name} -->' not in svg

    def test_table_export_honors_canvas_depth(self, running_server):
        source = {'tasks': [{'name': 'Parent', 'tasks': self.SOURCE['tasks']}]}
        request = Request(f'{running_server}/api/export?mode=table&format=csv&render_depth=1',
                          data=json.dumps(source).encode(), method='POST')
        with urlopen(request) as response:
            csv = response.read().decode()
        assert 'Parent' in csv
        assert 'Work' not in csv
        assert 'Gate' not in csv

    @pytest.mark.parametrize('depth', ['-1', '1.5', 'invalid'])
    def test_invalid_export_depth(self, running_server, depth):
        request = Request(f'{running_server}/api/export?mode=table&format=png&render_depth={depth}',
                          data=json.dumps(self.SOURCE).encode(), method='POST')
        with pytest.raises(HTTPError) as excinfo:
            urlopen(request)
        assert excinfo.value.code == 400

    def test_burn_csv_forwards_field_period_group_and_scale(self, running_server, tmp_path):
        from jsonantt.parser import parse_chart
        from jsonantt.renderer import render_burn_table
        request = Request(f'{running_server}/api/export?mode=burn-table&format=csv&burn_field=effort&burn_period=quarter&burn_group=total&burn_factor=2',
                          data=json.dumps(self.SOURCE).encode(), method='POST')
        with urlopen(request) as response:
            actual = response.read()
        target = tmp_path / 'expected.csv'
        render_burn_table(parse_chart(self.SOURCE), str(target), field='effort', period='quarter', group_by='total', display_factor=2)
        assert actual == target.read_bytes()

    @pytest.mark.parametrize('display', ['spend', 'remaining', 'cumulative'])
    def test_burn_png_matches_cli(self, running_server, tmp_path, display):
        from jsonantt.cli import main
        request = Request(f'{running_server}/api/export?mode=burn&format=png&dpi=80&burn_field=effort&burn_period=quarter&burn_group=total&burn_factor=2&burn_display={display}',
                          data=json.dumps(self.SOURCE).encode(), method='POST')
        with urlopen(request) as response:
            actual = response.read()
        source = tmp_path / 'chart.json'
        source.write_text(json.dumps(self.SOURCE))
        target = tmp_path / 'chart.png'
        assert main([str(source), str(target), '--burn', '--dpi', '80', '--burn-field', 'effort', '--burn-period', 'quarter', '--burn-group', 'total', '--burn-display-factor', '2', '--burn-display', display]) == 0
        assert actual == target.read_bytes()

    @pytest.mark.parametrize('mode', ['burndown', 'burnup'])
    @pytest.mark.parametrize('format', ['png', 'svg'])
    def test_separate_burn_views_export(self, running_server, tmp_path, mode, format):
        from jsonantt.cli import main
        request = Request(f'{running_server}/api/export?mode={mode}&format={format}&dpi=80&burn_period=quarter&burn_group=total',
                          data=json.dumps(self.SOURCE).encode(), method='POST')
        with urlopen(request) as response:
            assert f'{mode}.{format}' in response.headers['Content-Disposition']
            actual = response.read()
        if format == 'svg':
            assert mode.capitalize().encode() in actual
        else:
            source = tmp_path / 'chart.json'
            source.write_text(json.dumps(self.SOURCE))
            target = tmp_path / 'chart.png'
            assert main([str(source), str(target), f'--{mode}', '--dpi', '80', '--burn-period', 'quarter', '--burn-group', 'total']) == 0
            assert actual == target.read_bytes()


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
