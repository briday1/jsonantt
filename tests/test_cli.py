"""Tests for the ``jsonantt`` CLI (render/export) and ``fmt`` subcommand."""
from __future__ import annotations

import json
import subprocess
import sys
import pytest

from jsonantt.cli import main
from jsonantt.formatter import format_json_data


SAMPLE_CHART = {
    "title": "T",
    "dateformat": "%Y-%m-%d",
    "tasks": [{"name": "A", "start": "2024-01-01", "duration": "2w"}],
}


class TestRenderCommand:
    """Exports must be produced by the CLI's matplotlib rendering path."""

    def _write_chart(self, tmp_path):
        chart_path = tmp_path / "chart.json"
        chart_path.write_text(json.dumps(SAMPLE_CHART), encoding="utf-8")
        return chart_path

    def test_chart_exports_to_png_with_dpi(self, tmp_path):
        chart_path = self._write_chart(tmp_path)
        output = tmp_path / "chart.png"
        assert main([str(chart_path), str(output), "--dpi", "75"]) == 0
        assert output.is_file()
        assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    def test_chart_exports_to_svg(self, tmp_path):
        chart_path = self._write_chart(tmp_path)
        output = tmp_path / "chart.svg"
        assert main([str(chart_path), str(output)]) == 0
        assert output.is_file()
        assert output.read_text(encoding="utf-8").startswith("<?xml")

    @pytest.mark.parametrize('flags', [
        ['--burndown'], ['--burnup'], ['--burn', '--burn-display', 'remaining'],
    ])
    def test_burn_date_line(self, tmp_path, flags):
        chart_path = tmp_path / 'budget.json'
        chart_path.write_text(json.dumps({'tasks': [
            {'name': 'A', 'start': '2026-01-01', 'end': '2026-06-01', 'cost': 100},
        ]}))
        output = tmp_path / 'budget.svg'
        assert main([str(chart_path), str(output), *flags,
                     '--date-line', '2026-02-15', '--date-line-color', '#123abc']) == 0
        assert 'chart-date-marker' in output.read_text()
        assert '#123abc' in output.read_text()

    def test_table_exports_to_png_with_dpi(self, tmp_path):
        chart_path = self._write_chart(tmp_path)
        output = tmp_path / "table.png"
        assert main(["-t", str(chart_path), str(output), "--dpi", "75"]) == 0
        assert output.is_file()
        assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    def test_table_exports_to_svg(self, tmp_path):
        chart_path = self._write_chart(tmp_path)
        output = tmp_path / "table.svg"
        assert main(["-t", str(chart_path), str(output)]) == 0
        assert output.is_file()
        assert output.read_text(encoding="utf-8").startswith("<?xml")

    def test_table_exports_to_csv(self, tmp_path):
        chart_path = self._write_chart(tmp_path)
        output = tmp_path / "table.csv"
        assert main(["-t", str(chart_path), str(output)]) == 0
        assert output.is_file()
        assert output.read_text(encoding="utf-8").startswith("Task,Name")

    def test_csv_output_rejected_for_gantt_chart(self, tmp_path, capsys):
        chart_path = self._write_chart(tmp_path)
        output = tmp_path / "chart.csv"
        assert main([str(chart_path), str(output)]) == 1
        err = capsys.readouterr().err
        assert ".csv output is only supported for --table or --burn-table" in err
        assert not output.exists()

    def test_unsupported_extension_reports_friendly_error(self, tmp_path, capsys):
        chart_path = self._write_chart(tmp_path)
        output = tmp_path / "chart.txt"
        assert main([str(chart_path), str(output)]) == 1
        err = capsys.readouterr().err
        assert "unsupported output format" in err
        assert not output.exists()


class TestFmtCommand:
    def test_formats_in_place(self, tmp_path, capsys):
        target = tmp_path / "chart.json"
        target.write_text('{"title":"T","tasks":[{"name":"A"}]}', encoding="utf-8")
        assert main(["fmt", str(target)]) == 0
        assert target.read_text(encoding="utf-8") == format_json_data({"title": "T", "tasks": [{"name": "A"}]})
        assert "Formatted" in capsys.readouterr().out

    def test_output_flag_writes_new_file(self, tmp_path):
        source = tmp_path / "in.json"
        output = tmp_path / "out.json"
        source.write_text('{"a":1}', encoding="utf-8")
        assert main(["fmt", str(source), "-o", str(output)]) == 0
        assert output.read_text(encoding="utf-8") == '{\n  "a": 1\n}\n'
        # the input file is untouched when -o is used
        assert source.read_text(encoding="utf-8") == '{"a":1}'

    def test_missing_file_reports_error(self, capsys):
        assert main(["fmt", "does-not-exist.json"]) == 1
        assert "not found" in capsys.readouterr().err

    def test_invalid_json_reports_error(self, tmp_path, capsys):
        target = tmp_path / "broken.json"
        target.write_text("{oops", encoding="utf-8")
        assert main(["fmt", str(target)]) == 1
        assert "failed to format" in capsys.readouterr().err

    def test_stdin_stdout_roundtrip(self):
        proc = subprocess.run(
            [sys.executable, "-m", "jsonantt.cli", "fmt"],
            input='{"b":2,"a":1}',
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0
        assert proc.stdout == '{\n  "b": 2,\n  "a": 1\n}\n'

    def test_fmt_output_matches_studio_endpoint_style(self, tmp_path):
        """The CLI formatter and the studio formatter share one implementation."""
        payload = {"title": "café", "tasks": [{"name": "A", "start": "2026-01-01"}]}
        target = tmp_path / "chart.json"
        target.write_text(json.dumps(payload), encoding="utf-8")
        assert main(["fmt", str(target)]) == 0
        assert target.read_text(encoding="utf-8") == format_json_data(payload)
