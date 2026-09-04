"""Tests for the ``jsonantt fmt`` CLI subcommand."""
from __future__ import annotations

import json
import subprocess
import sys

from jsonantt.cli import main
from jsonantt.formatter import format_json_data


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
